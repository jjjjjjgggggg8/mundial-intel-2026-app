"""scripts/analysis/smart_picks.py — Motor de picks inteligentes para el Mundial 2026.

Analiza TODOS los mercados de un partido y devuelve solo los picks que son
estadísticamente notables para ESE partido concreto, priorizando value bets
confirmados y diversidad de mercados.
"""

from __future__ import annotations

import math
from scipy.stats import poisson as _poisson


# ─────────────────────────────────────────────────────────────────────────────
# Baselines históricos de Mundiales 2010–2022 (256 partidos)
# ─────────────────────────────────────────────────────────────────────────────

WORLD_CUP_BASELINES: dict[str, dict] = {
    # ── GOLES ─────────────────────────────────────────────────────────────
    "over_0_5":   {"mean": 0.940, "std": 0.040, "label": "Más de 0.5 goles"},
    "over_1_5":   {"mean": 0.820, "std": 0.070, "label": "Más de 1.5 goles"},
    "over_2_5":   {"mean": 0.520, "std": 0.100, "label": "Más de 2.5 goles"},
    "over_3_5":   {"mean": 0.330, "std": 0.090, "label": "Más de 3.5 goles"},
    "over_4_5":   {"mean": 0.170, "std": 0.065, "label": "Más de 4.5 goles"},
    "under_0_5":  {"mean": 0.060, "std": 0.040, "label": "Menos de 0.5 goles"},
    "under_1_5":  {"mean": 0.180, "std": 0.070, "label": "Menos de 1.5 goles"},
    "under_2_5":  {"mean": 0.480, "std": 0.100, "label": "Menos de 2.5 goles"},
    "under_3_5":  {"mean": 0.670, "std": 0.090, "label": "Menos de 3.5 goles"},
    # ── BTTS ──────────────────────────────────────────────────────────────
    "btts_yes":   {"mean": 0.480, "std": 0.095, "label": "Ambos equipos marcan - Sí"},
    "btts_no":    {"mean": 0.520, "std": 0.095, "label": "Ambos equipos marcan - No"},
    # ── RESULTADO 1X2 ─────────────────────────────────────────────────────
    "home_win":   {"mean": 0.450, "std": 0.110, "label": "Victoria equipo A"},
    "draw":       {"mean": 0.270, "std": 0.060, "label": "Empate"},
    "away_win":   {"mean": 0.280, "std": 0.100, "label": "Victoria equipo B"},
    # ── MARCADOR EXACTO ───────────────────────────────────────────────────
    "score_1_0":  {"mean": 0.125, "std": 0.040, "label": "Marcador exacto 1-0"},
    "score_0_0":  {"mean": 0.085, "std": 0.035, "label": "Marcador exacto 0-0"},
    "score_1_1":  {"mean": 0.110, "std": 0.038, "label": "Marcador exacto 1-1"},
    "score_2_1":  {"mean": 0.105, "std": 0.038, "label": "Marcador exacto 2-1"},
    "score_2_0":  {"mean": 0.090, "std": 0.035, "label": "Marcador exacto 2-0"},
    # ── DESCANSO / FINAL ──────────────────────────────────────────────────
    "ht_win_ft_win":  {"mean": 0.310, "std": 0.075, "label": "Gana 1ª parte y partido"},
    "ht_draw_ft_win": {"mean": 0.190, "std": 0.060, "label": "Empate 1ª parte, gana partido"},
    # ── TARJETAS ──────────────────────────────────────────────────────────
    "cards_over_3_5": {"mean": 0.450, "std": 0.110, "label": "Más de 3.5 tarjetas"},
    "cards_over_4_5": {"mean": 0.280, "std": 0.090, "label": "Más de 4.5 tarjetas"},
    "red_card_yes":   {"mean": 0.180, "std": 0.070, "label": "Tarjeta roja - Sí"},
    # ── CÓRNERS ───────────────────────────────────────────────────────────
    "corners_over_8_5":  {"mean": 0.520, "std": 0.105, "label": "Más de 8.5 córners"},
    "corners_over_9_5":  {"mean": 0.400, "std": 0.100, "label": "Más de 9.5 córners"},
    "corners_over_10_5": {"mean": 0.290, "std": 0.090, "label": "Más de 10.5 córners"},
    # ── HANDICAP ASIÁTICO ─────────────────────────────────────────────────
    "ah_home_minus_0_5": {"mean": 0.450, "std": 0.110, "label": "Hándicap Asiático local -0.5"},
    "ah_home_minus_1_5": {"mean": 0.270, "std": 0.085, "label": "Hándicap Asiático local -1.5"},
    "ah_away_plus_0_5":  {"mean": 0.550, "std": 0.110, "label": "Hándicap Asiático visitante +0.5"},
    # ── GANAR A CERO ──────────────────────────────────────────────────────
    "home_clean_sheet": {"mean": 0.310, "std": 0.080, "label": "Equipo A gana a cero"},
    "away_clean_sheet": {"mean": 0.260, "std": 0.075, "label": "Equipo B gana a cero"},
    # ── PENALTI ───────────────────────────────────────────────────────────
    "penalty_yes": {"mean": 0.270, "std": 0.080, "label": "Penalti pitado - Sí"},
    # ── PRIMER GOL ────────────────────────────────────────────────────────
    "first_goal_home":  {"mean": 0.480, "std": 0.100, "label": "Equipo A marca primero"},
    "first_goal_away":  {"mean": 0.340, "std": 0.090, "label": "Equipo B marca primero"},
    "first_goal_none":  {"mean": 0.085, "std": 0.035, "label": "Sin goles (0-0)"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Rutas de navegación en cada casa de apuestas
# ─────────────────────────────────────────────────────────────────────────────

MARKET_NAVIGATION: dict[str, dict[str, str]] = {
    "winamax": {
        "1x2":              "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Resultado",
        "over_2_5":         "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Total Goles › Más de 2.5",
        "over_1_5":         "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Total Goles › Más de 1.5",
        "over_3_5":         "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Total Goles › Más de 3.5",
        "under_2_5":        "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Total Goles › Menos de 2.5",
        "btts_yes":         "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Ambos Equipos Marcan › Sí",
        "btts_no":          "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Ambos Equipos Marcan › No",
        "exact_score":      "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Marcador Exacto › {score}",
        "ah_home":          "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Hándicap Europeo › {team} {line}",
        "double_chance":    "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Doble Oportunidad › {outcome}",
        "cards_over":       "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Tarjetas › Total Más de {line}",
        "corners_over":     "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Córners › Total Más de {line}",
        "home_clean_sheet": "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Ganar a Cero › {team}",
        "ht_ft":            "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Descanso / Final › {outcome}",
        "first_goal":       "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Equipo que marcará el 1er gol › {team}",
        "penalty_yes":      "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Penalti pitado › Sí",
        "player_scorer":    "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Goleador › {player}",
        "player_shots":     "Winamax › Fútbol › Copa del Mundo 2026 › {match} › {player} › Tiros totales › Más de {line}",
        "player_shots_ot":  "Winamax › Fútbol › Copa del Mundo 2026 › {match} › {player} › Tiros a puerta › Más de {line}",
        "player_assists":   "Winamax › Fútbol › Copa del Mundo 2026 › {match} › {player} › Asistencias › Más de {line}",
        "player_passes":    "Winamax › Fútbol › Copa del Mundo 2026 › {match} › {player} › Pases › Más de {line}",
        "red_card_yes":     "Winamax › Fútbol › Copa del Mundo 2026 › {match} › Tarjeta Roja › Sí",
        "myMatch":          "Winamax › Fútbol › Copa del Mundo 2026 › {match} › MyMatch (combinada personalizada)",
    },
    "bet365": {
        "1x2":              "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Resultado del partido",
        "over_2_5":         "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Objetivos › Más de 2.5",
        "over_1_5":         "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Objetivos › Más de 1.5",
        "over_3_5":         "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Objetivos › Más de 3.5",
        "under_2_5":        "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Objetivos › Menos de 2.5",
        "btts_yes":         "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Ambos equipos anotarán › Sí",
        "btts_no":          "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Ambos equipos anotarán › No",
        "exact_score":      "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Resultado correcto › {score}",
        "ah_home":          "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Hándicap asiático › {team} {line}",
        "double_chance":    "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Doble oportunidad › {outcome}",
        "cards_over":       "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Tarjetas › Total tarjetas asiáticas › Más de {line}",
        "corners_over":     "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Saques de esquina › Total córners › Más de {line}",
        "home_clean_sheet": "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Ganar a cero › {team}",
        "ht_ft":            "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Descanso/Final › {outcome}",
        "first_goal":       "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Primer equipo en marcar › {team}",
        "penalty_yes":      "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Penalti en el partido › Sí",
        "player_scorer":    "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Goleador en cualquier momento › {player}",
        "player_shots":     "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Tiros del jugador › {player} › Más de {line}",
        "player_shots_ot":  "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Tiros a puerta del jugador › {player} › Más de {line}",
        "player_assists":   "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Asistencias del jugador › {player} › Más de {line}",
        "player_passes":    "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Pases del jugador › {player} › Más de {line}",
        "player_tackles":   "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Entradas del jugador › {player} › Más de {line}",
        "red_card_yes":     "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Tarjeta roja en el partido › Sí",
        "bet_builder":      "Bet365 › Fútbol › Copa del Mundo 2026 › {match} › Crear apuesta (Bet Builder)",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Metadatos internos
# ─────────────────────────────────────────────────────────────────────────────

# Categoría de cada mercado para la regla de diversidad (1 pick por categoría)
_CATEGORY: dict[str, str] = {
    "over_0_5": "goals",  "over_1_5": "goals",  "over_2_5": "goals",
    "over_3_5": "goals",  "over_4_5": "goals",
    "under_0_5": "goals", "under_1_5": "goals",  "under_2_5": "goals",
    "under_3_5": "goals",
    "btts_yes": "btts",   "btts_no": "btts",
    "home_win": "result",   "draw": "result",     "away_win": "result",
    "score_1_0": "result",  "score_0_0": "result", "score_1_1": "result",
    "score_2_1": "result",  "score_2_0": "result",
    "ah_home_minus_0_5": "handicap", "ah_home_minus_1_5": "handicap",
    "ah_away_plus_0_5": "handicap",
    "home_clean_sheet": "clean_sheet", "away_clean_sheet": "clean_sheet",
    "ht_win_ft_win": "ht_ft",  "ht_draw_ft_win": "ht_ft",
    "cards_over_3_5": "cards", "cards_over_4_5": "cards", "red_card_yes": "cards",
    "corners_over_8_5": "corners", "corners_over_9_5": "corners",
    "corners_over_10_5": "corners",
    "penalty_yes": "special",
    "first_goal_home": "first_goal", "first_goal_away": "first_goal",
    "first_goal_none": "first_goal",
}

# Pares semánticamente equivalentes o redundantes: si el primero ya está en picks,
# descartar el segundo
_SEMANTIC_CONFLICTS: list[tuple[str, str]] = [
    ("score_0_0",       "under_0_5"),
    ("score_0_0",       "first_goal_none"),
    ("under_0_5",       "first_goal_none"),
    ("over_2_5",        "over_1_5"),   # over_1_5 es subset de over_2_5
    ("over_3_5",        "over_2_5"),
    ("under_2_5",       "under_3_5"),
    ("ah_home_minus_0_5", "home_win"), # básicamente idénticos
    ("btts_yes",        "over_1_5"),   # correlados pero no idénticos → solo bloquear si z muy bajo
]

# Mapeo market_key → clave en MARKET_NAVIGATION
_NAV_KEY: dict[str, str] = {
    "home_win": "1x2",   "draw": "1x2",   "away_win": "1x2",
    "over_1_5": "over_1_5", "over_2_5": "over_2_5", "over_3_5": "over_3_5",
    "under_2_5": "under_2_5",
    "btts_yes": "btts_yes", "btts_no": "btts_no",
    "score_1_0": "exact_score", "score_0_0": "exact_score",
    "score_1_1": "exact_score", "score_2_1": "exact_score", "score_2_0": "exact_score",
    "ah_home_minus_0_5": "ah_home", "ah_home_minus_1_5": "ah_home",
    "ah_away_plus_0_5": "ah_home",
    "cards_over_3_5": "cards_over", "cards_over_4_5": "cards_over",
    "red_card_yes": "red_card_yes",
    "corners_over_8_5": "corners_over", "corners_over_9_5": "corners_over",
    "corners_over_10_5": "corners_over",
    "home_clean_sheet": "home_clean_sheet", "away_clean_sheet": "home_clean_sheet",
    "ht_win_ft_win": "ht_ft", "ht_draw_ft_win": "ht_ft",
    "penalty_yes": "penalty_yes",
    "first_goal_home": "first_goal", "first_goal_away": "first_goal",
    "first_goal_none": "first_goal",
}

# Valores para los placeholders de navegación según market_key
_SCORE_LABEL: dict[str, str] = {
    "score_1_0": "1-0", "score_0_0": "0-0", "score_1_1": "1-1",
    "score_2_1": "2-1", "score_2_0": "2-0",
}
_LINE_LABEL: dict[str, str] = {
    "cards_over_3_5": "3.5",   "cards_over_4_5": "4.5",
    "corners_over_8_5": "8.5", "corners_over_9_5": "9.5",
    "corners_over_10_5": "10.5",
    "ah_home_minus_0_5": "-0.5", "ah_home_minus_1_5": "-1.5",
    "ah_away_plus_0_5": "+0.5",
}


# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def _score_market(market_key: str, model_prob: float,
                  baselines: dict = WORLD_CUP_BASELINES) -> dict:
    """
    Calcula el score de notabilidad para UN mercado.

    Retorna dict vacío si el mercado no está en baselines.
    El campo 'notability_score' es el valor z: (model_prob - mean) / std.
    Positivo = el partido tiene probabilidad ALTA para ese mercado vs. WC medio.
    Negativo = probabilidad BAJA.
    """
    b = baselines.get(market_key)
    if b is None:
        return {}
    mean, std = b["mean"], b["std"]
    if std <= 0:
        return {}
    z = (model_prob - mean) / std
    return {
        "market_key":       market_key,
        "label":            b["label"],
        "model_prob":       round(model_prob, 4),
        "baseline_mean":    mean,
        "baseline_std":     std,
        "notability_score": round(z, 3),
        "direction":        "HIGH" if z >= 0 else "LOW",
    }


def _compute_ev(model_prob: float, decimal_odds: float) -> float:
    """EV = prob_modelo × cuota_decimal - 1."""
    return model_prob * decimal_odds - 1.0


def _extract_all_probs(model_probs: dict, match_data: dict) -> dict[str, float]:
    """
    Extrae del output de get_all_markets() las probabilidades para cada
    clave de WORLD_CUP_BASELINES. Deriva los mercados que no están directamente
    disponibles usando lam/mu y distribuciones Poisson.
    """
    lam = model_probs.get("expected_goals_home", 1.2)
    mu  = model_probs.get("expected_goals_away", 1.0)
    lam_total = lam + mu

    p: dict[str, float] = {}

    # ── 1x2 ──────────────────────────────────────────────────────────────────
    p["home_win"]  = model_probs.get("prob_home_win", 0.0)
    p["draw"]      = model_probs.get("prob_draw", 0.0)
    p["away_win"]  = model_probs.get("prob_away_win", 0.0)

    # ── Over/Under (directos desde predict_match / get_all_markets) ───────────
    p["over_0_5"] = model_probs.get("prob_over_0_5", 0.0)
    p["over_1_5"] = model_probs.get("prob_over_1_5", 0.0)
    p["over_2_5"] = model_probs.get("prob_over_2_5", 0.0)
    p["over_3_5"] = model_probs.get("prob_over_3_5", 0.0)
    # over_4_5: aproximación Poisson(lam+mu) — suma de dos Poissons independientes
    p["over_4_5"] = float(1.0 - _poisson.cdf(4, lam_total))

    p["under_0_5"] = 1.0 - p["over_0_5"]
    p["under_1_5"] = 1.0 - p["over_1_5"]
    p["under_2_5"] = 1.0 - p["over_2_5"]
    p["under_3_5"] = 1.0 - p["over_3_5"]

    # ── BTTS ──────────────────────────────────────────────────────────────────
    p["btts_yes"] = model_probs.get("prob_btts", 0.0)
    p["btts_no"]  = 1.0 - p["btts_yes"]

    # ── Marcadores exactos (top_scorelines del modelo) ────────────────────────
    _score_raw = {"1-0": "score_1_0", "0-0": "score_0_0", "1-1": "score_1_1",
                  "2-1": "score_2_1", "2-0": "score_2_0"}
    for raw_s, key_s in _score_raw.items():
        found = next(
            (s["prob"] for s in model_probs.get("top_scorelines", [])
             if s["score"] == raw_s), 0.0
        )
        p[key_s] = float(found)

    # ── Ganar a cero (independence approximation: P(H>0) × P(A=0)) ───────────
    p_away_blank = math.exp(-mu)
    p_home_blank = math.exp(-lam)
    p["home_clean_sheet"] = (1.0 - p_home_blank) * p_away_blank
    p["away_clean_sheet"] = (1.0 - p_away_blank) * p_home_blank

    # ── Primer gol (carrera Poisson: T_home ~ Exp(lam), T_away ~ Exp(mu)) ─────
    if lam_total > 0:
        p_any = 1.0 - math.exp(-lam_total)
        p["first_goal_home"] = (lam / lam_total) * p_any
        p["first_goal_away"] = (mu  / lam_total) * p_any
        p["first_goal_none"] = math.exp(-lam_total)
    else:
        p["first_goal_home"] = 0.5
        p["first_goal_away"] = 0.5
        p["first_goal_none"] = 0.0

    # ── Hándicap Asiático (desde get_all_markets si disponible) ───────────────
    ah = model_probs.get("asian_handicap", {})
    p["ah_home_minus_0_5"] = ah.get("-0.5", {}).get("prob_home_covers", p["home_win"])
    p["ah_home_minus_1_5"] = ah.get("-1.5", {}).get("prob_home_covers", 0.0)
    p["ah_away_plus_0_5"]  = ah.get("-0.5", {}).get("prob_away_covers",
                                                     1.0 - p["home_win"])

    # ── Tarjetas (Poisson sobre expected_cards del modelo) ────────────────────
    cards_data = model_probs.get("cards_asian", {})
    if cards_data:
        p["cards_over_3_5"] = cards_data.get("3.5", {}).get("prob_over", 0.45)
        p["cards_over_4_5"] = cards_data.get("4.5", {}).get("prob_over", 0.28)
        exp_cards = cards_data.get("expected", 3.8)
    else:
        elo_diff_abs = abs(
            match_data.get("elo_home", 1500) - match_data.get("elo_away", 1500)
        )
        exp_cards = 3.8 + 0.5 * min(elo_diff_abs / 200.0, 1.5)
        p["cards_over_3_5"] = float(1.0 - _poisson.cdf(3, exp_cards))
        p["cards_over_4_5"] = float(1.0 - _poisson.cdf(4, exp_cards))

    # Tarjeta roja: ligero incremento por diferencia de Elo (más desesperación)
    elo_diff_abs = abs(
        match_data.get("elo_home", 1500) - match_data.get("elo_away", 1500)
    )
    p["red_card_yes"] = 0.180 + 0.025 * min(elo_diff_abs / 200.0, 1.0)

    # ── Córners (desde get_all_markets si disponible) ─────────────────────────
    corners_data = model_probs.get("corners_asian", {})
    if corners_data:
        exp_c = corners_data.get("expected", 9.5)
        p["corners_over_9_5"]  = corners_data.get("9.5",  {}).get("prob_over", 0.40)
        p["corners_over_10_5"] = corners_data.get("10.5", {}).get("prob_over", 0.29)
        p["corners_over_8_5"]  = float(1.0 - _poisson.cdf(8, exp_c))
    else:
        p["corners_over_8_5"]  = 0.52
        p["corners_over_9_5"]  = 0.40
        p["corners_over_10_5"] = 0.29

    # ── Penalti (levemente superior en fases eliminatorias) ───────────────────
    phase = match_data.get("phase", "group").lower()
    p["penalty_yes"] = 0.270 + (0.030 if any(
        kw in phase for kw in ("knockout", "round of", "quarter", "semi", "final")
    ) else 0.0)

    # ── HT/FT (aproximación calibrada en WC: ~69% de victorias ya ganaban en el HT)
    p["ht_win_ft_win"]  = p["home_win"] * 0.69
    p["ht_draw_ft_win"] = p["home_win"] * 0.31

    return {k: round(float(v), 4) for k, v in p.items()}


def _resolve_navigation(
    market_key: str,
    bookmaker: str,
    match_name: str,
    home_team: str,
    away_team: str,
) -> str:
    """
    Resuelve la plantilla de navegación para un mercado y casa de apuestas.
    Sustituye los placeholders {match}, {score}, {line}, {team}, {outcome}.
    """
    nav_bm  = MARKET_NAVIGATION.get(bookmaker, {})
    nav_key = _NAV_KEY.get(market_key, market_key)
    template = nav_bm.get(nav_key)

    if not template:
        return f"{bookmaker.title()} › Copa del Mundo 2026 › {match_name} › {market_key}"

    _outcome_labels: dict[str, str] = {
        "home_win":        home_team,
        "draw":            "Empate",
        "away_win":        away_team,
        "ht_win_ft_win":   f"{home_team}/{home_team}",
        "ht_draw_ft_win":  f"Empate/{home_team}",
        "first_goal_home": home_team,
        "first_goal_away": away_team,
        "first_goal_none": "Sin goles",
    }
    _team_labels: dict[str, str] = {
        "home_clean_sheet":  home_team,
        "away_clean_sheet":  away_team,
        "ah_home_minus_0_5": home_team,
        "ah_home_minus_1_5": home_team,
        "ah_away_plus_0_5":  away_team,
    }

    return template.format(
        match   = match_name,
        score   = _SCORE_LABEL.get(market_key, ""),
        line    = _LINE_LABEL.get(market_key, ""),
        team    = _team_labels.get(market_key, home_team),
        outcome = _outcome_labels.get(market_key, ""),
        player  = "",
    )


def _generate_reasoning(
    market_key: str,
    model_prob: float,
    baseline_mean: float,
    notability_score: float,
    direction: str,
    match_data: dict,
    model_probs: dict,
) -> str:
    """Genera una frase corta que explica POR QUÉ este mercado es notable."""
    lam   = model_probs.get("expected_goals_home", 1.2)
    mu    = model_probs.get("expected_goals_away", 1.0)
    home  = match_data.get("home_team", "Local")
    away  = match_data.get("away_team", "Visitante")
    elo_h = match_data.get("elo_home", 1500)
    elo_a = match_data.get("elo_away", 1500)
    elo_diff = elo_h - elo_a

    cat = _CATEGORY.get(market_key, "other")
    pct_model = f"{model_prob:.0%}"
    pct_base  = f"{baseline_mean:.0%}"
    adj_dir   = "por encima" if direction == "HIGH" else "por debajo"

    if cat == "goals":
        total_xg = lam + mu
        return (
            f"xG total {total_xg:.2f} ({home} {lam:.2f} + {away} {mu:.2f}) "
            f"→ modelo {pct_model} vs media WC {pct_base}"
        )
    if cat == "btts":
        return (
            f"{home} ({lam:.2f} xG) y {away} ({mu:.2f} xG) — "
            f"modelo BTTS {pct_model} vs media WC {pct_base}"
        )
    if cat in ("result", "handicap", "clean_sheet", "ht_ft"):
        return (
            f"Diferencia Elo {elo_diff:+.0f} pts — modelo {pct_model} "
            f"({adj_dir} de media WC {pct_base})"
        )
    if cat in ("cards", "corners"):
        return (
            f"Estimación del partido: {pct_model} vs media WC {pct_base} "
            f"(z={notability_score:+.2f})"
        )
    if cat == "first_goal":
        return (
            f"Tasa de primer gol — modelo {pct_model} vs media WC {pct_base} "
            f"(xG: {home} {lam:.2f} | {away} {mu:.2f})"
        )
    # special / other
    return (
        f"Modelo {pct_model} | Media WC {pct_base} | "
        f"z={notability_score:+.2f} ({adj_dir} de la media histórica)"
    )


def _pick_best_ev(
    market_key: str,
    model_prob: float,
    odds_data: dict,
    ev_threshold: float,
) -> dict:
    """
    Calcula EV para bet365 y winamax desde odds_data.
    odds_data formato: {market_key: {bet365: float|None, winamax: float|None}}
    Retorna dict con campos ev_*, odds_*, best_ev, best_bookmaker, has_ev.
    """
    mkt_odds  = odds_data.get(market_key, {})
    odds_b365 = mkt_odds.get("bet365")
    odds_wina = mkt_odds.get("winamax")

    ev_b365 = _compute_ev(model_prob, odds_b365) if odds_b365 else None
    ev_wina = _compute_ev(model_prob, odds_wina) if odds_wina else None

    evs = {k: v for k, v in {"bet365": ev_b365, "winamax": ev_wina}.items()
           if v is not None}

    if evs:
        best_bk = max(evs, key=lambda k: evs[k])
        best_ev = evs[best_bk]
    else:
        best_bk = None
        best_ev = None

    return {
        "ev_bet365":      round(ev_b365, 4) if ev_b365 is not None else None,
        "ev_winamax":     round(ev_wina, 4) if ev_wina is not None else None,
        "odds_bet365":    round(odds_b365, 2) if odds_b365 else None,
        "odds_winamax":   round(odds_wina, 2) if odds_wina else None,
        "best_ev":        round(best_ev, 4) if best_ev is not None else None,
        "best_bookmaker": best_bk,
        "has_ev":         best_ev is not None and best_ev >= ev_threshold,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def compute_smart_picks(
    match_data: dict,
    model_probs: dict,
    player_markets: dict,
    odds_data: dict,
    max_picks: int = 6,
    ev_threshold: float = 0.04,
) -> list[dict]:
    """
    Analiza TODOS los mercados de un partido y devuelve solo los picks
    estadísticamente notables para ESE partido concreto.

    Parámetros
    ----------
    match_data     : {home_team, away_team, phase, elo_home, elo_away, ...}
    model_probs    : salida de DixonColesModel.get_all_markets()
    player_markets : salida de PlayerMarketAnalyzer.analyze_match_players()
    odds_data      : {market_key: {bet365: float|None, winamax: float|None}}
                     donde float es la cuota decimal
    max_picks      : número máximo de picks a devolver
    ev_threshold   : EV mínimo para considerar value bet confirmado

    Retorna
    -------
    Lista de dicts con estructura definida en el módulo (ver docstring detallado
    en _score_market y la sección de picks de jugadores).
    """
    home  = match_data.get("home_team", "Local")
    away  = match_data.get("away_team", "Visitante")
    match_name = f"{home} vs {away}"

    # 1. Extraer probabilidades del modelo para todos los mercados
    all_probs = _extract_all_probs(model_probs, match_data)

    # 2. Puntuar cada mercado contra el baseline histórico
    scored: list[dict] = []
    for mkt_key, mkt_prob in all_probs.items():
        scored_mkt = _score_market(mkt_key, mkt_prob)
        if not scored_mkt:
            continue

        ev_info = _pick_best_ev(mkt_key, mkt_prob, odds_data, ev_threshold)
        nav_wina = _resolve_navigation(mkt_key, "winamax", match_name, home, away)
        nav_b365 = _resolve_navigation(mkt_key, "bet365", match_name, home, away)
        reasoning = _generate_reasoning(
            mkt_key, mkt_prob,
            scored_mkt["baseline_mean"],
            scored_mkt["notability_score"],
            scored_mkt["direction"],
            match_data,
            model_probs,
        )

        scored.append({
            **scored_mkt,
            **ev_info,
            "where_to_bet_winamax": nav_wina,
            "where_to_bet_bet365":  nav_b365,
            "reasoning":            reasoning,
            "is_player_market":     False,
        })

    # 3. Añadir picks de jugadores desde player_markets
    top_players = (
        player_markets.get("top_home_picks", []) +
        player_markets.get("top_away_picks", [])
    )
    for player_pick in top_players:
        player_name = player_pick.get("name", "")
        player_prob = player_pick.get("prob_anytime_scorer", 0.0)
        pos         = player_pick.get("position", "FW")
        if player_prob <= 0:
            continue

        # Baseline por posición (no en WORLD_CUP_BASELINES genérico)
        pos_baseline = {"GK": 0.02, "DF": 0.06, "MF": 0.12, "FW": 0.30}
        pos_std      = {"GK": 0.02, "DF": 0.04, "MF": 0.07, "FW": 0.10}
        bl_mean = pos_baseline.get(pos, 0.20)
        bl_std  = pos_std.get(pos, 0.07)
        z_player = (player_prob - bl_mean) / bl_std if bl_std > 0 else 0.0

        player_mkt_key = f"player_scorer_{player_name.lower().replace(' ', '_')}"
        ev_info = _pick_best_ev(player_mkt_key, player_prob, odds_data, ev_threshold)

        nav_wina = MARKET_NAVIGATION["winamax"]["player_scorer"].format(
            match=match_name, player=player_name
        )
        nav_b365 = MARKET_NAVIGATION["bet365"]["player_scorer"].format(
            match=match_name, player=player_name
        )

        scored.append({
            "market_key":       player_mkt_key,
            "label":            f"Goleador: {player_name}",
            "model_prob":       round(player_prob, 4),
            "baseline_mean":    bl_mean,
            "baseline_std":     bl_std,
            "notability_score": round(z_player, 3),
            "direction":        "HIGH" if z_player >= 0 else "LOW",
            **ev_info,
            "where_to_bet_winamax": nav_wina,
            "where_to_bet_bet365":  nav_b365,
            "reasoning": (
                f"{player_name} ({pos}) — prob. goleador {player_prob:.0%} "
                f"vs baseline {pos} ({bl_mean:.0%}), z={z_player:+.2f}"
            ),
            "is_player_market": True,
        })

    # 4. Separar mercados con EV confirmado y sin EV
    with_ev    = [s for s in scored if s["has_ev"]]
    without_ev = [s for s in scored if not s["has_ev"]]

    # 5. Ordenar: EV bets por best_ev desc; resto por |notability_score| desc
    with_ev.sort(key=lambda x: x["best_ev"] or 0.0, reverse=True)
    without_ev.sort(key=lambda x: abs(x["notability_score"]), reverse=True)

    # 6. Filtro de notabilidad mínima (|z| >= 1.0) para picks sin EV
    # EV bets siempre pasan, independientemente de z.
    without_ev = [s for s in without_ev if abs(s["notability_score"]) >= 1.0]

    # 7. Aplicar regla de diversidad: máximo 1 pick por categoría
    # Excepción: si todos los EV bets son de goles → se permite 1 extra de goles
    def _select_with_diversity(
        candidates: list[dict],
        category_slots: dict[str, int],
    ) -> list[dict]:
        """Selecciona picks respetando el cupo por categoría."""
        used_cats: dict[str, int] = {}
        result: list[dict] = []
        chosen_keys: set[str] = set()

        for pick in candidates:
            mkt_key = pick["market_key"]
            cat     = _CATEGORY.get(mkt_key, "player" if pick["is_player_market"] else "other")
            max_in_cat = category_slots.get(cat, 1)

            if used_cats.get(cat, 0) >= max_in_cat:
                continue

            # Verificar conflictos semánticos
            blocked = False
            for primary, redundant in _SEMANTIC_CONFLICTS:
                if mkt_key == redundant and primary in chosen_keys:
                    blocked = True
                    break
            if blocked:
                continue

            used_cats[cat] = used_cats.get(cat, 0) + 1
            chosen_keys.add(mkt_key)
            result.append(pick)

        return result

    # Determinar si todos los EV bets son de goles → liberar cupo extra
    ev_categories = {_CATEGORY.get(s["market_key"], "other") for s in with_ev}
    goals_only_ev = bool(with_ev) and ev_categories.issubset({"goals", "btts"})
    goals_slot = 2 if goals_only_ev else 1

    category_slots = {
        "goals": goals_slot, "btts": 1, "result": 1, "handicap": 1,
        "clean_sheet": 1, "ht_ft": 1, "cards": 1, "corners": 1,
        "first_goal": 1, "special": 1, "player": 2,
    }

    # Primero EV bets (respetan diversidad), luego sin EV hasta max_picks
    selected_ev    = _select_with_diversity(with_ev, category_slots)
    remaining_cats: dict[str, int] = {}
    for pick in selected_ev:
        cat = _CATEGORY.get(pick["market_key"], "player" if pick["is_player_market"] else "other")
        remaining_cats[cat] = remaining_cats.get(cat, 0) + 1

    # Slots restantes para picks sin EV
    slots_for_non_ev = {
        cat: max(0, category_slots.get(cat, 1) - remaining_cats.get(cat, 0))
        for cat in list(category_slots.keys()) + list(remaining_cats.keys())
    }
    selected_non_ev = _select_with_diversity(without_ev, slots_for_non_ev)

    # 8. Combinar, truncar a max_picks
    final_picks = (selected_ev + selected_non_ev)[:max_picks]

    # 9. Limpiar campos internos antes de devolver
    clean_fields = {
        "market_key", "label", "model_prob", "baseline_mean", "baseline_std",
        "notability_score", "direction", "has_ev", "ev_bet365", "ev_winamax",
        "best_ev", "best_bookmaker", "odds_bet365", "odds_winamax",
        "where_to_bet_winamax", "where_to_bet_bet365", "reasoning",
    }
    return [
        {k: v for k, v in pick.items() if k in clean_fields}
        for pick in final_picks
    ]
