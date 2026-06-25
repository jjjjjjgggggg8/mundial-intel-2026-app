"""Odds ingestion from The Odds API v4 with de-vig (power method)."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

try:
    from scipy.optimize import brentq
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging — create data/output/ before attaching the FileHandler.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
(_PROJECT_ROOT / "data" / "output").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            str(_PROJECT_ROOT / "data" / "output" / "odds_ingestion.log")
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_upcoming_odds(api_key: str, days_ahead: int = 3) -> dict:
    """Fetch upcoming WC-2026 odds from The Odds API v4.

    Uses bookmakers=bet365,winamax and markets=h2h,totals.
    "btts" is not a valid market key on The Odds API; an approximation can be
    derived in extract_fair_odds() if over/under 0.5 data is available.

    Credit cost: 2 markets × 1 bookmaker-set = 2 credits per call.
    Remaining credits are returned in each event dict (requests_remaining).
    """
    logger.info(f"Iniciando fetch de cuotas para {days_ahead} días adelante")

    url = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
    now_utc = datetime.utcnow()
    params = {
        "apiKey":           api_key,
        "bookmakers":       "bet365,winamax",
        "markets":          "h2h,totals",
        "oddsFormat":       "decimal",
        "commenceTimeFrom": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo":   (now_utc + timedelta(days=days_ahead)).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
        "dateFormat":       "iso",
    }

    response = _request_with_backoff(url, params)

    if response.status_code == 429:
        wait_s = 60
        print(f"⚠️  Rate limit alcanzado. Esperando {wait_s}s...")
        logger.warning(f"Rate limit alcanzado. Esperando {wait_s}s antes de reintentar...")
        time.sleep(wait_s)
        response = _request_with_backoff(url, params)
        if response.status_code == 429:
            raise RuntimeError(
                "Rate limit persiste tras reintento de 60s. "
                "Verifica tu cuota mensual en The Odds API."
            )

    if response.status_code in (401, 403):
        raise ValueError("API key inválida o sin permisos")
    if response.status_code == 404:
        raise ValueError("Sport key incorrecto o no disponible")
    if not response.ok:
        msg = response.text[:300]
        logger.error(
            f"Error HTTP {response.status_code} en fetch_upcoming_odds: {msg}"
        )
        response.raise_for_status()

    requests_remaining = response.headers.get("x-requests-remaining")
    fetched_at = datetime.utcnow().isoformat() + "Z"

    result: dict = {}
    for event in response.json():
        event_id = event["id"]
        bookmakers_data: dict = {}

        for bm in event.get("bookmakers", []):
            bm_key = bm["key"]
            markets: dict = {}
            for market in bm.get("markets", []):
                mkey = market["key"]
                outcomes = []
                for o in market.get("outcomes", []):
                    entry: dict = {"name": o["name"], "price": float(o["price"])}
                    if "point" in o:
                        entry["point"] = float(o["point"])
                    outcomes.append(entry)
                markets[mkey] = outcomes
            bookmakers_data[bm_key] = {
                "last_update": bm.get("last_update", ""),
                "markets": markets,
            }

        if "winamax" not in bookmakers_data:
            logger.warning(
                f"Winamax sin cuotas para partido {event_id} "
                f"({event.get('home_team')} vs {event.get('away_team')})"
            )

        result[event_id] = {
            "home_team":          event.get("home_team", ""),
            "away_team":          event.get("away_team", ""),
            "commence_time":      event.get("commence_time", ""),
            "bookmakers":         bookmakers_data,
            "requests_remaining": int(requests_remaining)
                                  if requests_remaining is not None else None,
            "fetched_at":         fetched_at,
        }

    return result


def extract_fair_odds(raw_odds: dict, method: str = "power") -> dict:
    """Remove the bookmaker overround using the power method (Clarke et al. 2017).

    Power method: find k > 1 such that Σ (π_i ^ k) = 1, then p_fair_i = π_i ^ k.
    Reference: Clarke et al. (2017), eq. (7).  Multiplicative normalisation
    (p_i = π_i / Σπ_j) is used as fallback when scipy is unavailable.
    """
    use_power = method == "power" and _SCIPY_AVAILABLE
    result: dict = {}

    for event_id, event in raw_odds.items():
        result[event_id] = {}
        for bm_key, bm_data in event.get("bookmakers", {}).items():
            result[event_id][bm_key] = {}
            for market_key, outcomes_list in bm_data.get("markets", {}).items():
                prices: dict[str, float] = {}
                for o in outcomes_list:
                    if market_key == "totals" and "point" in o:
                        label = f"{o['name']} {o['point']}"
                    else:
                        label = o["name"]
                    prices[label] = float(o["price"])

                implied: dict[str, float] = {
                    name: 1.0 / price for name, price in prices.items()
                }
                booksum = sum(implied.values())
                overround_pct = (booksum - 1.0) * 100.0

                k_val: Optional[float] = None
                actual_method = "multiplicative"
                fair: dict[str, float]

                if use_power:
                    try:
                        # Σ π_i^k = 1 has a solution k > 1 when booksum > 1.
                        f = lambda k: sum(p ** k for p in implied.values()) - 1.0
                        k_val = brentq(f, 1.0, 100.0)
                        fair = {name: p ** k_val for name, p in implied.items()}
                        actual_method = "power"
                    except Exception:
                        fair = {name: p / booksum for name, p in implied.items()}
                        k_val = None
                        actual_method = "multiplicative"
                else:
                    fair = {name: p / booksum for name, p in implied.items()}

                outcomes_result: dict = {
                    name: {
                        "price":        prices[name],
                        "prob_implied": implied[name],
                        "prob_fair":    fair[name],
                    }
                    for name in prices
                }

                result[event_id][bm_key][market_key] = {
                    "booksum":       booksum,
                    "overround_pct": overround_pct,
                    "method":        actual_method,
                    "k":             k_val,
                    "outcomes":      outcomes_result,
                }

    return result


def save_odds_snapshot(
    odds_dict: dict,
    path: str = "data/output/odds.json",
) -> None:
    """Merge new odds into the snapshot file, skipping events fetched <6h ago."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if out_path.exists():
        try:
            with out_path.open(encoding="utf-8") as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            existing = {}

    now = datetime.utcnow()
    merged: dict = {k: v for k, v in existing.items() if not k.startswith("_")}

    skipped_fresh = 0
    updated_count = 0

    for event_id, event_data in odds_dict.items():
        if event_id in merged:
            old_fetched = merged[event_id].get("fetched_at", "")
            if old_fetched:
                try:
                    old_dt = datetime.fromisoformat(old_fetched.rstrip("Z"))
                    age_hours = (now - old_dt).total_seconds() / 3600.0
                    if age_hours < 6.0:
                        logger.info(
                            f"Partido {event_id} omitido: "
                            f"snapshot tiene {age_hours:.1f}h (<6h)"
                        )
                        skipped_fresh += 1
                        continue
                except ValueError:
                    pass

        merged[event_id] = event_data
        updated_count += 1

    total_matches = len(merged)
    merged["_meta"] = {
        "last_updated":  now.isoformat() + "Z",
        "total_matches": total_matches,
        "skipped_fresh": skipped_fresh,
        "updated_count": updated_count,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _request_with_backoff(url: str, params: dict) -> requests.Response:
    wait = 1
    for attempt in range(1, 4):
        try:
            return requests.get(url, params=params, timeout=30)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            logger.error(f"Fallo de conexión (intento {attempt}/3): {e}")
            if attempt == 3:
                raise
            time.sleep(wait)
            wait *= 2
    raise RuntimeError("Retry logic exhausted")  # unreachable


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        raise SystemExit("ODDS_API_KEY no encontrada en el entorno/.env")

    raw = fetch_upcoming_odds(api_key)
    save_odds_snapshot(raw)

    new_matches = sum(
        1 for v in raw.values() if isinstance(v, dict) and "home_team" in v
    )
    last_remaining = next(
        (v.get("requests_remaining") for v in raw.values()
         if isinstance(v, dict) and v.get("requests_remaining") is not None),
        "N/A",
    )
    print(
        f"Cuotas obtenidas para {new_matches} partidos. "
        f"Peticiones restantes este mes: {last_remaining}"
    )
