"""scripts/analysis/ev_calculator.py — Cálculo de EV para todos los mercados.

Compara las probabilidades del modelo Dixon-Coles (get_all_markets) con las
cuotas de Bet365 y Winamax obtenidas de The Odds API (extract_fair_odds).
"""

from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.config import EV_THRESHOLD, BOOKMAKERS

_BOOKMAKER_DISPLAY = {"bet365": "Bet365", "winamax": "Winamax"}


# ---------------------------------------------------------------------------
# Rutas de navegación en casa de apuestas
# ---------------------------------------------------------------------------

def _where_to_bet(bookmaker: str, home: str, away: str,
                  market_label: str, outcome: str) -> str:
    """Construye la ruta de navegación para encontrar la apuesta."""
    bk = _BOOKMAKER_DISPLAY.get(bookmaker, bookmaker.capitalize())
    partido = f"{home} vs {away}"

    if bookmaker == "bet365":
        if "Hándicap Asiático" in market_label or "AH" in market_label:
            return f"Bet365 › Fútbol › Copa del Mundo › {partido} › Asian Handicap › {outcome}"
        if "Gol" in market_label or "Over" in market_label or "Under" in market_label:
            return f"Bet365 › Fútbol › Copa del Mundo › {partido} › Match Goals › {outcome}"
        if "Córner" in market_label or "corner" in market_label.lower():
            return f"Bet365 › Fútbol › Copa del Mundo › {partido} › Match Corners › {outcome}"
        if "Tarjeta" in market_label or "tarjeta" in market_label.lower():
            return f"Bet365 › Fútbol › Copa del Mundo › {partido} › Cards › {outcome}"
        return f"Bet365 › Fútbol › Copa del Mundo › {partido} › {market_label} › {outcome}"
    else:
        if "Hándicap Europeo" in market_label or "EH" in market_label:
            return f"Winamax › Fútbol › Copa del Mundo › {partido} › Hándicap Europeo › {outcome}"
        if "Intervalos" in market_label or "goles" in market_label.lower():
            return f"Winamax › Fútbol › Copa del Mundo › {partido} › Número de Goles › {outcome}"
        if "Gol" in market_label or "Over" in market_label:
            return f"Winamax › Fútbol › Copa del Mundo › {partido} › Total de Goles › {outcome}"
        return f"Winamax › Fútbol › Copa del Mundo › {partido} › {market_label} › {outcome}"


# ---------------------------------------------------------------------------
# Mapeo de mercados de cuotas → probabilidades del modelo
# ---------------------------------------------------------------------------

def _resolve_model_prob(
    bk_key: str,
    market_key: str,
    outcome_label: str,
    model: dict,
    home_team: str,
    away_team: str,
) -> tuple[float | None, str, str, float, bool]:
    """
    Resuelve la probabilidad del modelo para un outcome concreto de la API.

    Returns:
        (prob, market_display, outcome_display, push_prob, is_asian)
        prob=None si no hay mapeo definido.
    """
    label_lo = outcome_label.lower().strip()
    home_lo  = home_team.lower().strip()
    away_lo  = away_team.lower().strip()

    # ── 1X2 ────────────────────────────────────────────────────────────────
    if market_key == "h2h":
        if label_lo == "draw":
            return (model["prob_draw"], "1X2 — Empate", "Empate", 0.0, False)
        if label_lo == home_lo or label_lo == home_lo.split()[0]:
            return (model["prob_home_win"], f"1X2 — {home_team}", home_team, 0.0, False)
        if label_lo == away_lo or label_lo == away_lo.split()[0]:
            return (model["prob_away_win"], f"1X2 — {away_team}", away_team, 0.0, False)
        return (None, "", "", 0.0, False)

    # ── Over/Under (totals) ─────────────────────────────────────────────────
    if market_key == "totals":
        parts = label_lo.split()
        if len(parts) < 2:
            return (None, "", "", 0.0, False)
        direction = parts[0]  # "over" / "under"
        try:
            line = float(parts[1])
        except ValueError:
            return (None, "", "", 0.0, False)

        key = str(line)
        at = model.get("asian_total", {}).get(key, {})
        if not at:
            # Fallback a prob_over_X_5 estándar
            line_key = f"prob_over_{str(line).replace('.', '_')}"
            if direction == "over":
                return (model.get(line_key), f"Total Over {line}", f"Over {line}", 0.0, False)
            return (None, "", "", 0.0, False)

        push = at.get("prob_push", 0.0)
        if direction == "over":
            return (at["prob_over"], f"Total Over {line}", f"Over {line}", push, at["is_asian"])
        else:
            return (at["prob_under"], f"Total Under {line}", f"Under {line}", push, at["is_asian"])

    # ── alternate_totals ────────────────────────────────────────────────────
    if market_key == "alternate_totals":
        parts = label_lo.split()
        if len(parts) < 2:
            return (None, "", "", 0.0, False)
        direction = parts[0]
        try:
            line = float(parts[1])
        except ValueError:
            return (None, "", "", 0.0, False)
        key = str(line)
        at  = model.get("asian_total", {}).get(key, {})
        if not at:
            return (None, "", "", 0.0, False)
        push = at.get("prob_push", 0.0)
        if direction == "over":
            return (at["prob_over"],  f"Alt Total Over {line}",  f"Over {line}",  push, at["is_asian"])
        return (at["prob_under"], f"Alt Total Under {line}", f"Under {line}", push, at["is_asian"])

    # ── spreads (hándicap, formato: "TeamName point") ───────────────────────
    if market_key in ("spreads", "alternate_spreads"):
        # outcome_label puede ser "Spain -1.0" o "Germany +1.0"
        # La API incluye el punto en el label cuando procesamos con el punto
        parts = outcome_label.rsplit(None, 1)  # split por último espacio
        if len(parts) != 2:
            return (None, "", "", 0.0, False)
        team_part, hc_str = parts[0].strip(), parts[1].strip()
        try:
            hc = float(hc_str)
        except ValueError:
            return (None, "", "", 0.0, False)

        team_lo = team_part.lower()
        ah      = model.get("asian_handicap", {}).get(str(hc), {})
        if not ah:
            ah = model.get("asian_handicap", {}).get(f"{hc:.1f}", {})
        if not ah:
            return (None, "", "", 0.0, False)

        push = ah.get("prob_push", 0.0)
        is_asian = abs(hc % 1.0) < 1e-9 or abs(abs(hc % 1.0) - 0.5) > 1e-9

        if team_lo == home_lo or team_lo == home_lo.split()[0]:
            # Home team covers → prob_home_covers
            return (ah["prob_home_covers"], f"AH {home_team} {hc:+.1f}",
                    f"{home_team} {hc:+.1f}", push, is_asian)
        if team_lo == away_lo or team_lo == away_lo.split()[0]:
            # Away team covers → prob_away_covers with inverted handicap
            return (ah["prob_away_covers"], f"AH {away_team} {-hc:+.1f}",
                    f"{away_team} {-hc:+.1f}", push, is_asian)
        return (None, "", "", 0.0, False)

    # ── btts ────────────────────────────────────────────────────────────────
    if market_key == "btts":
        if "yes" in label_lo:
            return (model["prob_btts"], "Ambos marcan — Sí", "Sí", 0.0, False)
        if "no" in label_lo:
            return (1.0 - model["prob_btts"], "Ambos marcan — No", "No", 0.0, False)
        return (None, "", "", 0.0, False)

    return (None, "", "", 0.0, False)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def calculate_ev_all_markets(
    model_predictions: dict,
    odds_data: dict,
    home_team: str,
    away_team: str,
    ev_threshold: float = EV_THRESHOLD,
) -> list[dict]:
    """
    Compara todos los mercados del modelo con las cuotas disponibles y
    devuelve la lista de value bets ordenada por EV descendente.

    Parámetros:
        model_predictions : salida de DixonColesModel.get_all_markets()
        odds_data         : fair_by_match[mid] de extract_fair_odds()
                            {bookmaker: {market: {outcomes: {label: {price, prob_fair}}}}}
        home_team         : nombre del equipo local (para mapeo de h2h)
        away_team         : nombre del equipo visitante
        ev_threshold      : EV mínimo para considerar value bet
    """
    # Agrupamos por (market_key, outcome_label) para comparar ambas casas a la vez
    candidates: dict[tuple, dict] = {}

    for bk in BOOKMAKERS:
        bk_data = odds_data.get(bk, {})
        for market_key, market_data in bk_data.items():
            outcomes = market_data.get("outcomes", {})
            for outcome_label, odata in outcomes.items():
                price = odata.get("price")
                if not price or price <= 1.0:
                    continue

                (prob, market_disp, outcome_disp, push_prob, is_asian) = _resolve_model_prob(
                    bk, market_key, outcome_label,
                    model_predictions, home_team, away_team,
                )
                if prob is None or prob <= 0:
                    continue

                key = (market_key, outcome_label)
                if key not in candidates:
                    candidates[key] = {
                        "market":       market_disp,
                        "market_type":  market_key,
                        "outcome":      outcome_disp,
                        "model_prob":   round(prob, 4),
                        "fair_odds":    round(1.0 / prob, 2),
                        "push_prob":    round(push_prob, 4),
                        "is_asian":     is_asian,
                        "best_ev":      -999.0,
                        "best_bookmaker": None,
                        "best_odds":    None,
                        "odds_bet365":  None,
                        "ev_bet365":    None,
                        "odds_winamax": None,
                        "ev_winamax":   None,
                        "where_to_bet_bet365":  "",
                        "where_to_bet_winamax": "",
                    }

                ev = prob * price - 1.0
                c  = candidates[key]
                c[f"odds_{bk}"] = round(price, 2)
                c[f"ev_{bk}"]   = round(ev, 4)
                c[f"where_to_bet_{bk}"] = _where_to_bet(
                    bk, home_team, away_team, market_disp, outcome_disp
                )

                if ev > c["best_ev"]:
                    c["best_ev"]        = round(ev, 4)
                    c["best_bookmaker"] = _BOOKMAKER_DISPLAY.get(bk, bk)
                    c["best_odds"]      = round(price, 2)

    # Filtrar por umbral, añadir where_to_bet genérico
    value_bets: list[dict] = []
    for c in candidates.values():
        if c["best_ev"] < ev_threshold:
            continue
        # Compatibilidad con ValueBetCard existente (campo where_to_bet único)
        best_bk = (c["best_bookmaker"] or "").lower().replace(" ", "")
        if "bet365" in best_bk:
            c["where_to_bet"] = c["where_to_bet_bet365"]
        else:
            c["where_to_bet"] = c["where_to_bet_winamax"]
        c["is_player_market"] = False
        value_bets.append(c)

    return sorted(value_bets, key=lambda x: x["best_ev"], reverse=True)
