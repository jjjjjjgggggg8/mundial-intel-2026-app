"""scripts/main.py — Orquestador principal del pipeline Mundial Intel 2026.

Ejecutado dos veces al día por GitHub Actions (07:00 y 15:00 UTC).
Entrena los modelos Elo + Dixon-Coles, obtiene cuotas de The Odds API,
genera análisis con Gemini Flash y escribe los JSON que consume la web Next.js.
"""

import sys
import os

# Permite importar los módulos del proyecto tanto en local como en CI.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from scripts.models.elo import EloModel
from scripts.models.poisson import DixonColesModel
from scripts.ingestion.historical import load_matches, load_wc2026_calendar, normalize_team_name
from scripts.ingestion.odds import fetch_upcoming_odds, extract_fair_odds, save_odds_snapshot
from scripts.analysis.gemini_analyst import analyze_match
from scripts.analysis.ev_calculator import calculate_ev_all_markets
from scripts.analysis.player_markets import PlayerMarketAnalyzer
from scripts.analysis.smart_picks import compute_smart_picks
from scripts.config import EV_THRESHOLD, SQUADS_PATH

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------

_ROOT        = Path(__file__).resolve().parent.parent
_DATA_RAW    = _ROOT / "data" / "raw"
_DATA_LOGS   = _ROOT / "data" / "logs"
_ODDS_SNAP   = _ROOT / "data" / "output" / "odds.json"
_WEB_PUBLIC  = _ROOT / "web" / "public" / "data"

_ODDS_STALE_HOURS = 6.0
_UPCOMING_HOURS   = 48

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(run_ts: str) -> None:
    """Configura handlers simultáneos a stdout y a archivo de log fechado."""
    _DATA_LOGS.mkdir(parents=True, exist_ok=True)
    fmt     = "%(asctime)s %(levelname)-5s %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(_DATA_LOGS / f"run_{run_ts}.txt"), encoding="utf-8"),
        ],
    )


# ---------------------------------------------------------------------------
# Helpers de snapshot de cuotas
# ---------------------------------------------------------------------------

def _snapshot_age_hours() -> float | None:
    """Antigüedad en horas del snapshot de cuotas, o None si no existe o es inválido."""
    if not _ODDS_SNAP.exists():
        return None
    try:
        with _ODDS_SNAP.open(encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("_meta", {}).get("last_updated", "")
        if not ts:
            return None
        dt = datetime.fromisoformat(ts.rstrip("Z"))
        return (datetime.utcnow() - dt).total_seconds() / 3600.0
    except Exception:
        return None


def _load_snapshot_raw() -> tuple[dict, str | None]:
    """
    Carga el snapshot de cuotas excluyendo la clave _meta.

    Returns:
        (raw_odds_dict, last_updated_iso)
    """
    with _ODDS_SNAP.open(encoding="utf-8") as f:
        data = json.load(f)
    raw = {k: v for k, v in data.items() if not k.startswith("_")}
    ts  = data.get("_meta", {}).get("last_updated")
    return raw, ts


# ---------------------------------------------------------------------------
# Matching de eventos Odds API → match_ids del calendario
# ---------------------------------------------------------------------------

def _build_odds_maps(
    raw_odds: dict,
    calendar_df,
) -> tuple[dict, dict]:
    """
    Relaciona los eventos de The Odds API (UUIDs) con los match_ids del calendario.

    La coincidencia se hace por (fecha UTC, home normalizado, away normalizado).

    Returns:
        raw_by_match  — {match_id: raw_event_data}
        fair_by_match — {match_id: fair_odds_per_bookmaker_and_market}
    """
    # Lookup del calendario: (date_str, home_lower, away_lower) → match_id
    cal_lookup: dict[tuple, str] = {}
    for _, row in calendar_df.iterrows():
        date_str = str(row["date"])[:10] if row["date"] else ""
        home     = normalize_team_name(str(row["home_team"])).lower()
        away     = normalize_team_name(str(row["away_team"])).lower()
        cal_lookup[(date_str, home, away)] = row["match_id"]

    # Emparejar eventos Odds API con match_ids
    uuid_to_match: dict[str, str] = {}
    match_to_uuid: dict[str, str] = {}
    for uid, event in raw_odds.items():
        if not isinstance(event, dict) or "home_team" not in event:
            continue
        date_str = event.get("commence_time", "")[:10]
        home     = normalize_team_name(event.get("home_team", "")).lower()
        away     = normalize_team_name(event.get("away_team", "")).lower()
        mid      = cal_lookup.get((date_str, home, away))
        if mid:
            uuid_to_match[uid] = mid
            match_to_uuid[mid] = uid

    if not uuid_to_match:
        return {}, {}

    raw_by_match: dict = {
        uuid_to_match[uid]: raw_odds[uid]
        for uid in uuid_to_match
        if uid in raw_odds
    }

    # Extraer fair_odds una sola vez para todos los eventos emparejados
    matched_raw  = {uid: raw_odds[uid] for uid in uuid_to_match}
    fair_by_uuid = extract_fair_odds(matched_raw)
    fair_by_match: dict = {
        uuid_to_match[uid]: fair
        for uid, fair in fair_by_uuid.items()
        if uid in uuid_to_match
    }

    return raw_by_match, fair_by_match


# ---------------------------------------------------------------------------
# Cálculo de EV y value bets
# ---------------------------------------------------------------------------

_MARKET_LABELS: dict[str, str] = {
    "home_win": "Victoria local",
    "draw":     "Empate",
    "away_win": "Victoria visitante",
    "over_0_5": "Más de 0.5 goles",
    "over_1_5": "Más de 1.5 goles",
    "over_2_5": "Más de 2.5 goles",
    "over_3_5": "Más de 3.5 goles",
    "btts":     "Ambos marcan (Sí)",
}


def _where_to_bet(bookmaker: str, home: str, away: str, market_label: str) -> str:
    """Construye el texto de navegación para encontrar la apuesta."""
    bk  = "Bet365" if bookmaker == "bet365" else bookmaker.capitalize()
    sec = "Más/Menos" if "goles" in market_label else "Resultado"
    return f"{bk} › Fútbol › Mundial 2026 › {home} vs {away} › {sec} › {market_label}"


def _calc_value_bets(
    home_team: str,
    away_team: str,
    preds: dict,
    fair_for_match: dict,
    raw_for_match: dict,
) -> list[dict]:
    """
    Calcula el EV para cada mercado disponible y devuelve value bets (EV ≥ 5%).

    fair_for_match: salida de extract_fair_odds para este evento concreto.
        Estructura: {bookmaker: {market: {"outcomes": {label: {price, prob_implied, prob_fair}}}}}
    raw_for_match: raw event de fetch_upcoming_odds (para leer home_team / away_team de la API).
    """
    api_home = raw_for_match.get("home_team", home_team)
    api_away = raw_for_match.get("away_team", away_team)

    # (market_key, outcome_label_en_la_API, model_key, model_prob)
    targets: list[tuple[str, str, str, float]] = [
        ("h2h",    api_home,   "home_win", preds["prob_home_win"]),
        ("h2h",    "Draw",     "draw",     preds["prob_draw"]),
        ("h2h",    api_away,   "away_win", preds["prob_away_win"]),
        ("totals", "Over 0.5", "over_0_5", preds["prob_over_0_5"]),
        ("totals", "Over 1.5", "over_1_5", preds["prob_over_1_5"]),
        ("totals", "Over 2.5", "over_2_5", preds["prob_over_2_5"]),
        ("totals", "Over 3.5", "over_3_5", preds["prob_over_3_5"]),
    ]

    bookmakers = ["bet365", "winamax"]
    value_bets: list[dict] = []

    for market_key, outcome_label, model_key, model_prob in targets:
        if model_prob <= 0:
            continue

        row: dict = {
            "market":         _MARKET_LABELS.get(model_key, market_key),
            "model_prob":     round(model_prob, 4),
            "fair_odds":      round(1.0 / model_prob, 2),
            "best_ev":        -999.0,
            "best_bookmaker": None,
        }

        has_price = False
        for bk in bookmakers:
            outcomes = (
                fair_for_match
                .get(bk, {})
                .get(market_key, {})
                .get("outcomes", {})
            )
            # Búsqueda exacta primero, luego insensible a mayúsculas
            outcome_data = outcomes.get(outcome_label)
            if outcome_data is None:
                for k, v in outcomes.items():
                    if k.lower() == outcome_label.lower():
                        outcome_data = v
                        break
            if outcome_data is None:
                continue

            price = outcome_data["price"]
            ev    = model_prob * price - 1.0
            row[f"odds_{bk}"] = round(price, 2)
            row[f"ev_{bk}"]   = round(ev, 4)
            has_price = True

            if ev > row["best_ev"]:
                row["best_ev"]        = round(ev, 4)
                row["best_bookmaker"] = "Winamax" if bk == "winamax" else "Bet365"

        if not has_price:
            continue

        # Rellenar bookmakers sin cuota
        for bk in bookmakers:
            if f"odds_{bk}" not in row:
                row[f"odds_{bk}"] = None
                row[f"ev_{bk}"]   = None

        if row["best_ev"] < _EV_THRESHOLD:
            continue

        row["where_to_bet"] = _where_to_bet(
            row["best_bookmaker"].lower(),
            home_team, away_team, row["market"],
        )
        value_bets.append(row)

    return sorted(value_bets, key=lambda x: x["best_ev"], reverse=True)


# ---------------------------------------------------------------------------
# Conversión de cuotas para smart_picks
# ---------------------------------------------------------------------------

def _build_smart_picks_odds(
    fair_for_match: dict,
    home_team: str,
    away_team: str,
) -> dict:
    """Convierte fair_by_match[mid] al formato {market_key: {bet365, winamax}} esperado por compute_smart_picks."""
    home_lo = home_team.lower().strip()
    away_lo = away_team.lower().strip()
    result: dict = {}

    for bk, bk_data in fair_for_match.items():
        if bk not in ("bet365", "winamax"):
            continue
        for market_key, market_data in bk_data.items():
            for label, odata in market_data.get("outcomes", {}).items():
                price = odata.get("price")
                if not price or price <= 1.0:
                    continue
                label_lo = label.lower().strip()
                pick_key: str | None = None

                if market_key == "h2h":
                    if label_lo == "draw":
                        pick_key = "draw"
                    elif label_lo in (home_lo, home_lo.split()[0]):
                        pick_key = "home_win"
                    elif label_lo in (away_lo, away_lo.split()[0]):
                        pick_key = "away_win"

                elif market_key in ("totals", "alternate_totals"):
                    parts = label_lo.split()
                    if len(parts) >= 2:
                        try:
                            line = float(parts[1])
                            line_key = f"{line:.1f}".replace(".", "_")
                            if parts[0] == "over":
                                pick_key = f"over_{line_key}"
                            elif parts[0] == "under":
                                pick_key = f"under_{line_key}"
                        except ValueError:
                            pass

                elif market_key == "btts":
                    if "yes" in label_lo:
                        pick_key = "btts_yes"
                    elif "no" in label_lo:
                        pick_key = "btts_no"

                elif market_key in ("spreads", "alternate_spreads"):
                    parts = label.rsplit(None, 1)
                    if len(parts) == 2:
                        team_lo2 = parts[0].strip().lower()
                        try:
                            hc = float(parts[1].strip())
                            if team_lo2 in (home_lo, home_lo.split()[0]):
                                if hc == -0.5:
                                    pick_key = "ah_home_minus_0_5"
                                elif hc == -1.5:
                                    pick_key = "ah_home_minus_1_5"
                            elif team_lo2 in (away_lo, away_lo.split()[0]):
                                if hc == 0.5:
                                    pick_key = "ah_away_plus_0_5"
                        except ValueError:
                            pass

                if pick_key:
                    result.setdefault(pick_key, {})[bk] = price

    return result


# ---------------------------------------------------------------------------
# Construcción de dict de análisis completo
# ---------------------------------------------------------------------------

def _build_analysis(
    row,
    preds: dict,
    elo_home: float,
    elo_away: float,
    value_bets: list,
    gemini_text: str | None,
    snapshot_ts: str | None,
    is_upcoming: bool,
    player_markets: dict | None = None,
    smart_picks: list | None = None,
) -> dict:
    """Construye el dict completo de análisis para un partido."""
    date_str    = str(row["date"])[:10] if row["date"] else ""
    kickoff_utc = row.get("kickoff_utc", "") or ""
    kickoff_str = kickoff_utc[11:16] if len(kickoff_utc) >= 16 else ""

    elo_diff   = abs(elo_home - elo_away)
    confidence = "high" if elo_diff > 100 else "medium" if elo_diff > 40 else "low"

    # Mercados asiáticos — solo si get_all_markets fue llamado
    asian_handicap = preds.get("asian_handicap", {})
    asian_total    = preds.get("asian_total", {})
    goal_ranges    = preds.get("goal_ranges", [])

    return {
        "match_id":    row["match_id"],
        "home_team":   row["home_team"],
        "away_team":   row["away_team"],
        "phase":       row.get("phase", ""),
        "date":        date_str,
        "kickoff":     kickoff_str,
        "venue":       row.get("venue", ""),
        "elo_home":    round(elo_home, 1),
        "elo_away":    round(elo_away, 1),
        "elo_advantage": round(elo_home - elo_away, 1),
        "probs": {
            "home_win":            preds["prob_home_win"],
            "draw":                preds["prob_draw"],
            "away_win":            preds["prob_away_win"],
            "over_0_5":            preds["prob_over_0_5"],
            "over_1_5":            preds["prob_over_1_5"],
            "over_2_5":            preds["prob_over_2_5"],
            "over_3_5":            preds["prob_over_3_5"],
            "btts":                preds["prob_btts"],
            "expected_goals_home": preds["expected_goals_home"],
            "expected_goals_away": preds["expected_goals_away"],
        },
        "top_scorelines": preds["top_scorelines"],
        "high_prob_events": [
            {"event": "Ambos equipos marcan",           "prob": preds["prob_btts"]},
            {"event": "Más de 1 gol",                   "prob": preds["prob_over_1_5"]},
            {"event": "Más de 2 goles",                 "prob": preds["prob_over_2_5"]},
            {"event": "Al menos 1 gol en cada tiempo",
             "prob": round(preds["prob_over_0_5"] * 0.72, 3)},
        ],
        "asian_handicap": asian_handicap,
        "asian_total":    asian_total,
        "goal_ranges":    goal_ranges,
        "value_bets":     value_bets,
        "has_value_bet":  len(value_bets) > 0,
        "confidence":     confidence,
        "gemini_analysis":  gemini_text,
        "odds_updated_at":  snapshot_ts,
        "is_upcoming":      is_upcoming,
        "top_scorers": {
            "home": (player_markets or {}).get("top_home_picks", []),
            "away": (player_markets or {}).get("top_away_picks", []),
        },
        "smart_picks": smart_picks or [],
    }


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def main() -> None:
    """Orquestador completo: datos → modelos → cuotas → Gemini → JSON web."""
    start_time       = time.monotonic()
    run_ts           = datetime.utcnow().strftime("%Y%m%d_%H%M")
    run_timestamp_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    _setup_logging(run_ts)
    log = logging.getLogger(__name__)

    ODDS_API_KEY  = os.environ.get("ODDS_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

    # ── PASO 1: Carga de datos ──────────────────────────────────────────────
    log.info("Iniciando pipeline Mundial Intel 2026")
    matches_df  = load_matches(str(_DATA_RAW / "results.csv"))
    calendar_df = load_wc2026_calendar(str(_DATA_RAW / "wc2026" / "worldcup.json"))
    log.info(f"Calendario cargado: {len(calendar_df)} partidos en total")

    # ── PASO 2: Entrenamiento de modelos e inicialización de analizadores ───
    elo_model = EloModel()
    elo_model.fit(matches_df)
    dc_model = DixonColesModel()
    dc_model.fit(matches_df)
    log.info("Modelos entrenados correctamente")

    squads_path = str(_ROOT / SQUADS_PATH)
    try:
        player_analyzer = PlayerMarketAnalyzer(squads_path)
        log.info(f"PlayerMarketAnalyzer cargado: {len(player_analyzer.squads)} equipos")
    except FileNotFoundError:
        player_analyzer = None
        log.warning(f"Plantillas no encontradas en {squads_path}. Mercados de jugadores desactivados.")

    # ── PASO 3: Separar upcoming (48h) vs. resto ───────────────────────────
    now_utc     = datetime.now(tz=timezone.utc)
    cutoff      = now_utc + timedelta(hours=_UPCOMING_HOURS)
    upcoming_rows: list = []
    rest_rows:    list = []

    for _, row in calendar_df.iterrows():
        koff_str = row.get("kickoff_utc", "") or ""
        if not koff_str:
            rest_rows.append(row)
            continue
        try:
            dt = datetime.fromisoformat(koff_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        except ValueError:
            rest_rows.append(row)
            continue
        if now_utc <= dt <= cutoff:
            upcoming_rows.append(row)
        elif dt > cutoff:
            rest_rows.append(row)
        # Partidos ya disputados: omitir

    log.info(
        f"Próximas 48h: {len(upcoming_rows)} partidos. "
        f"Resto del torneo: {len(rest_rows)} partidos"
    )

    # ── PASO 4: Cuotas (solo upcoming) ─────────────────────────────────────
    raw_by_match:  dict = {}
    fair_by_match: dict = {}
    snapshot_ts:   str | None = None
    odds_age:      float | None = None

    if upcoming_rows and ODDS_API_KEY:
        try:
            age = _snapshot_age_hours()
            if age is not None and age < _ODDS_STALE_HOURS:
                log.info(f"Usando snapshot de cuotas de hace {age:.1f}h")
                raw_odds, snapshot_ts = _load_snapshot_raw()
                odds_age = age
            else:
                log.info("Descargando cuotas desde The Odds API...")
                raw_odds = fetch_upcoming_odds(ODDS_API_KEY, days_ahead=3)
                save_odds_snapshot(raw_odds)
                snapshot_ts = run_timestamp_iso
                odds_age    = 0.0
                remaining   = next(
                    (
                        v.get("requests_remaining")
                        for v in raw_odds.values()
                        if isinstance(v, dict) and v.get("requests_remaining") is not None
                    ),
                    "N/A",
                )
                log.info(
                    f"Cuotas descargadas para {len(raw_odds)} partidos. "
                    f"Peticiones API restantes: {remaining}"
                )

            raw_by_match, fair_by_match = _build_odds_maps(raw_odds, calendar_df)

        except Exception as exc:
            log.warning(f"Error al obtener cuotas: {exc}. Continuando sin odds.")
    elif not ODDS_API_KEY:
        log.warning("ODDS_API_KEY no configurada. Continuando sin cuotas.")

    # ── PASO 5: Partidos próximos (con cuotas + Gemini) ────────────────────
    analyses:          dict = {}
    total_value_bets:  int  = 0

    for row in upcoming_rows:
        mid       = row["match_id"]
        home_team = row["home_team"]
        away_team = row["away_team"]

        log.info(f"Procesando partido próximo: {home_team} vs {away_team}")

        # a) Elo
        elo_home = elo_model.get_rating(home_team)
        elo_away = elo_model.get_rating(away_team)
        log.info(f"  Elo {home_team}: {elo_home:.0f} | {away_team}: {elo_away:.0f}")

        # b) Predicciones Dixon-Coles — todos los mercados
        preds = dc_model.get_all_markets(home_team, away_team, elo_home, elo_away, neutral=True)

        # c) Value bets con ev_calculator (todos los mercados)
        value_bets: list = []
        if mid in fair_by_match:
            try:
                value_bets = calculate_ev_all_markets(
                    preds, fair_by_match[mid], home_team, away_team, EV_THRESHOLD
                )
            except Exception as exc:
                log.warning(f"  Error calculando EV para {mid}: {exc}")

        # d) Mercados de jugadores
        player_markets: dict | None = None
        if player_analyzer is not None:
            try:
                player_markets = player_analyzer.analyze_match_players(
                    home_team, away_team, preds
                )
            except Exception as exc:
                log.warning(f"  Error en mercados de jugadores para {mid}: {exc}")

        total_value_bets += len(value_bets)
        log.info(f"  Value bets encontrados: {len(value_bets)}")

        # e) Smart picks
        smart_picks_result: list = []
        try:
            match_data_for_sp = {
                "home_team": home_team,
                "away_team": away_team,
                "phase": row.get("phase", "group"),
                "elo_home": elo_home,
                "elo_away": elo_away,
            }
            odds_data_for_sp = _build_smart_picks_odds(
                fair_by_match.get(mid, {}), home_team, away_team
            )
            smart_picks_result = compute_smart_picks(
                match_data=match_data_for_sp,
                model_probs=preds,
                player_markets=player_markets or {},
                odds_data=odds_data_for_sp,
            )
            log.info(f"  Smart picks generados: {len(smart_picks_result)}")
        except Exception as exc:
            log.warning(f"  Error en smart_picks para {mid}: {exc}")

        # f) Gemini
        if GEMINI_API_KEY:
            date_str    = str(row["date"])[:10] if row["date"] else ""
            kickoff_utc = row.get("kickoff_utc", "") or ""
            kickoff_str = kickoff_utc[11:16] if len(kickoff_utc) >= 16 else ""

            gemini_text = analyze_match(
                match_data={
                    "id":        mid,
                    "home_team": home_team,
                    "away_team": away_team,
                    "phase":     row.get("phase", ""),
                    "date":      date_str,
                    "kickoff":   kickoff_str,
                    "venue":     row.get("venue", ""),
                },
                model_predictions={
                    "elo_home":            elo_home,
                    "elo_away":            elo_away,
                    "elo_advantage":       round(elo_home - elo_away, 1),
                    "prob_home_win":       preds["prob_home_win"],
                    "prob_draw":           preds["prob_draw"],
                    "prob_away_win":       preds["prob_away_win"],
                    "prob_over_2_5":       preds["prob_over_2_5"],
                    "prob_btts":           preds["prob_btts"],
                    "expected_goals_home": preds["expected_goals_home"],
                    "expected_goals_away": preds["expected_goals_away"],
                },
                odds_data={"value_bets": value_bets, "has_value": len(value_bets) > 0},
                api_key=GEMINI_API_KEY,
            )
            log.info(f"  Análisis Gemini generado ({len(gemini_text)} chars)")
        else:
            gemini_text = (
                f"Análisis no disponible. {home_team} ({elo_home:.0f} Elo) vs "
                f"{away_team} ({elo_away:.0f} Elo). "
                f"Probabilidad victoria local: {preds['prob_home_win']:.0%}."
            )
            log.warning("  GEMINI_API_KEY no configurada, usando fallback")

        # g) Dict completo
        analyses[mid] = _build_analysis(
            row, preds, elo_home, elo_away,
            value_bets, gemini_text, snapshot_ts,
            is_upcoming=True, player_markets=player_markets,
            smart_picks=smart_picks_result,
        )

    # ── PASO 6: Resto del torneo (sin cuotas ni Gemini) ────────────────────
    log.info(f"Procesando {len(rest_rows)} partidos sin cuotas...")
    for row in rest_rows:
        mid       = row["match_id"]
        home_team = row["home_team"]
        away_team = row["away_team"]
        elo_home  = elo_model.get_rating(home_team)
        elo_away  = elo_model.get_rating(away_team)
        preds     = dc_model.predict_match(home_team, away_team, elo_home, elo_away, neutral=True)
        rest_sp: list = []
        try:
            rest_sp = compute_smart_picks(
                match_data={
                    "home_team": home_team,
                    "away_team": away_team,
                    "phase": row.get("phase", "group"),
                    "elo_home": elo_home,
                    "elo_away": elo_away,
                },
                model_probs=preds,
                player_markets={},
                odds_data={},
            )
        except Exception as exc:
            log.warning(f"  Error en smart_picks (rest) para {mid}: {exc}")
        analyses[mid] = _build_analysis(
            row, preds, elo_home, elo_away,
            value_bets=[], gemini_text=None,
            snapshot_ts=None, is_upcoming=False,
            smart_picks=rest_sp,
        )

    # ── PASO 7: Escribir JSON de salida ────────────────────────────────────
    _WEB_PUBLIC.mkdir(parents=True, exist_ok=True)

    all_sorted = sorted(
        analyses.values(),
        key=lambda x: (x["date"] or "9999", x["kickoff"] or "99:99"),
    )

    # matches.json — lista compacta para la UI
    matches_list = [
        {
            "id":           a["match_id"],
            "phase":        a["phase"],
            "date":         a["date"],
            "kickoff":      a["kickoff"],
            "home_team":    a["home_team"],
            "away_team":    a["away_team"],
            "venue":        a["venue"],
            "has_value_bet": a["has_value_bet"],
            "confidence":   a["confidence"],
            "prob_home":    a["probs"]["home_win"],
            "prob_draw":    a["probs"]["draw"],
            "prob_away":    a["probs"]["away_win"],
            "is_upcoming":  a["is_upcoming"],
            "updated_at":   run_timestamp_iso,
        }
        for a in all_sorted
    ]

    with (_WEB_PUBLIC / "matches.json").open("w", encoding="utf-8") as f:
        json.dump(matches_list, f, ensure_ascii=False, indent=2)

    # analyses.json — dict completo keyed por match_id
    with (_WEB_PUBLIC / "analyses.json").open("w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)

    log.info("JSON escritos en web/public/data/")

    # ── PASO 8: last_run.json ───────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    log.info(f"Pipeline completado en {elapsed:.1f}s")

    last_run = {
        "timestamp":               run_timestamp_iso,
        "matches_total":           len(analyses),
        "matches_upcoming":        len(upcoming_rows),
        "value_bets_total":        total_value_bets,
        "odds_snapshot_age_hours": round(odds_age, 2) if odds_age is not None else None,
        "status":                  "ok",
    }
    with (_WEB_PUBLIC / "last_run.json").open("w", encoding="utf-8") as f:
        json.dump(last_run, f, ensure_ascii=False, indent=2)

    # ── PASO 9: Resumen y salida ────────────────────────────────────────────
    print(f"Procesados {len(analyses)} partidos. Value bets detectados: {total_value_bets}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.critical(f"Error crítico: {exc}", exc_info=True)
        try:
            _WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
            with (_WEB_PUBLIC / "last_run.json").open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp":     datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status":        "error",
                        "error_message": str(exc),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass
        sys.exit(1)
