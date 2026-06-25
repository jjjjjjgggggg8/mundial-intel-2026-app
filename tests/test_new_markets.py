"""tests/test_new_markets.py — Tests para los nuevos mercados del megaprompt.

Cubre: asian handicap, asian total, european handicap, goal ranges,
ev_calculator y player_markets.
"""

from __future__ import annotations

import sys
import os
import math

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.models.poisson import DixonColesModel
from scripts.ingestion.historical import load_matches

# ---------------------------------------------------------------------------
# Fixture común: modelo entrenado
# ---------------------------------------------------------------------------

_DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
_RESULTS   = os.path.join(_DATA_DIR, "results.csv")
_WC_JSON   = os.path.join(_DATA_DIR, "wc2026", "worldcup.json")
_SQUADS    = os.path.join(_DATA_DIR, "worldcup.squads.json")


@pytest.fixture(scope="module")
def trained_dc() -> DixonColesModel:
    df = load_matches(_RESULTS)
    model = DixonColesModel()
    model.fit(df)
    return model


@pytest.fixture(scope="module")
def sample_matrix(trained_dc):
    """Matriz de probabilidades España vs Alemania (Elo 2050 vs 2000, neutral)."""
    return trained_dc._build_matrix("Spain", "Germany", 2050.0, 2000.0, neutral=True)


# ---------------------------------------------------------------------------
# Test 1 — Hándicap Asiático: quarter lines y sumas de probabilidad
# ---------------------------------------------------------------------------

class TestAsianHandicap:
    def test_half_line_sums_to_one(self, trained_dc, sample_matrix):
        """Líneas de medio gol no tienen push: prob_home + prob_away = 1."""
        matrix, lam, mu = sample_matrix
        result = trained_dc.predict_asian_handicap(matrix, 0.5)
        total = result["prob_home_covers"] + result["prob_away_covers"]
        assert abs(total - 1.0) < 1e-6, f"prob_home + prob_away = {total} ≠ 1.0"
        assert result["prob_push"] == pytest.approx(0.0)

    def test_quarter_line_split_structure(self, trained_dc, sample_matrix):
        """
        Línea 0.25 es split de 0.0 (entero, tiene push) y 0.5 (semientero, no tiene push).
        El push promediado es la mitad del push en la línea 0.0, no cero.
        La suma home + push + away debe ser ≈ 1.
        """
        matrix, lam, mu = sample_matrix
        result = trained_dc.predict_asian_handicap(matrix, 0.25)
        total = result["prob_home_covers"] + result["prob_away_covers"] + result["prob_push"]
        assert abs(total - 1.0) < 1e-4, f"Suma de prob = {total}"
        # El push de 0.25 debe ser la mitad del push en 0.0
        r00 = trained_dc.predict_asian_handicap(matrix, 0.0)
        assert abs(result["prob_push"] - r00["prob_push"] / 2.0) < 0.001

    def test_integer_line_has_push(self, trained_dc, sample_matrix):
        """Líneas enteras tienen probabilidad de push > 0."""
        matrix, lam, mu = sample_matrix
        result = trained_dc.predict_asian_handicap(matrix, 0.0)
        assert result["prob_push"] > 0
        total = (result["prob_home_covers"] + result["prob_away_covers"]
                 + result["prob_push"])
        assert abs(total - 1.0) < 1e-6

    def test_large_handicap_flips_favorite(self, trained_dc, sample_matrix):
        """Con hándicap de +2.0 para el visitante (Spain -2.0), la prob_away_covers sube."""
        matrix, lam, mu = sample_matrix
        res_0   = trained_dc.predict_asian_handicap(matrix, 0.0)
        res_neg2 = trained_dc.predict_asian_handicap(matrix, -2.0)
        # Spain -2.0 → más difícil cubrir → prob_home_covers debería bajar vs -0
        assert res_neg2["prob_home_covers"] < res_0["prob_home_covers"]


# ---------------------------------------------------------------------------
# Test 2 — Asian Total: push en líneas enteras
# ---------------------------------------------------------------------------

class TestAsianTotal:
    def test_integer_line_has_push(self, trained_dc, sample_matrix):
        matrix, _, _ = sample_matrix
        result = trained_dc.predict_asian_total(matrix, 2.0)
        assert result["prob_push"] > 0
        total = result["prob_over"] + result["prob_under"] + result["prob_push"]
        assert abs(total - 1.0) < 1e-6

    def test_half_line_no_push(self, trained_dc, sample_matrix):
        matrix, _, _ = sample_matrix
        result = trained_dc.predict_asian_total(matrix, 2.5)
        assert result["prob_push"] == pytest.approx(0.0)
        assert abs(result["prob_over"] + result["prob_under"] - 1.0) < 1e-6

    def test_over_decreases_with_higher_line(self, trained_dc, sample_matrix):
        """P(Over 3.5) < P(Over 2.5) < P(Over 1.5) para cualquier partido."""
        matrix, _, _ = sample_matrix
        p15 = trained_dc.predict_asian_total(matrix, 1.5)["prob_over"]
        p25 = trained_dc.predict_asian_total(matrix, 2.5)["prob_over"]
        p35 = trained_dc.predict_asian_total(matrix, 3.5)["prob_over"]
        assert p15 > p25 > p35


# ---------------------------------------------------------------------------
# Test 3 — European Handicap: tres outcomes suman 1
# ---------------------------------------------------------------------------

class TestEuropeanHandicap:
    def test_three_outcomes_sum_to_one(self, trained_dc, sample_matrix):
        """Las keys reales son prob_home_win_adj / prob_draw_adj / prob_away_win_adj.
        Tolerancia 2e-4 por errores de redondeo acumulados (round a 4 decimales × 3 términos)."""
        matrix, _, _ = sample_matrix
        for hc in [-1, 0, 1]:
            result = trained_dc.predict_european_handicap(matrix, hc)
            total = (result["prob_home_win_adj"] + result["prob_draw_adj"]
                     + result["prob_away_win_adj"])
            assert abs(total - 1.0) < 2e-4, f"EH {hc}: sum={total}"

    def test_zero_handicap_matches_1x2(self, trained_dc, sample_matrix):
        """EH 0 debe coincidir con las probabilidades 1X2 normales."""
        matrix, lam, mu = sample_matrix
        preds_1x2 = trained_dc.predict_match(
            "Spain", "Germany", 2050.0, 2000.0, neutral=True
        )
        result_eh0 = trained_dc.predict_european_handicap(matrix, 0)
        assert abs(result_eh0["prob_home_win_adj"] - preds_1x2["prob_home_win"]) < 1e-6
        assert abs(result_eh0["prob_draw_adj"]     - preds_1x2["prob_draw"])     < 1e-6
        assert abs(result_eh0["prob_away_win_adj"] - preds_1x2["prob_away_win"]) < 1e-6


# ---------------------------------------------------------------------------
# Test 4 — Goal Ranges: suma total = 1 (excepto truncamiento a MAX_GOALS)
# ---------------------------------------------------------------------------

class TestGoalRanges:
    def test_four_ranges_sum_to_approx_one(self, trained_dc, sample_matrix):
        """Los 4 intervalos estándar (0-1, 2-3, 4-5, 6+) deben sumar ~1. Key: 'prob'."""
        matrix, _, _ = sample_matrix
        ranges = trained_dc.predict_all_goal_ranges(matrix)
        assert len(ranges) == 4
        total = sum(r["prob"] for r in ranges)
        assert abs(total - 1.0) < 0.01, f"Suma intervalos = {total}"

    def test_first_range_most_likely(self, trained_dc, sample_matrix):
        """En un partido promedio, 0-1 goles es el intervalo más o segundo más probable."""
        matrix, _, _ = sample_matrix
        ranges = trained_dc.predict_all_goal_ranges(matrix)
        # Cada rango devuelve {"label": ..., "prob": ...}
        assert all("prob" in r and "label" in r for r in ranges)
        probs = [r["prob"] for r in ranges]
        idx_max = probs.index(max(probs))
        # El rango máximo debería ser 0-1 o 2-3 (índice 0 o 1)
        assert idx_max <= 1, f"Intervalo más probable inesperado: índice {idx_max}"


# ---------------------------------------------------------------------------
# Test 5 — EV Calculator: estructura de salida y umbral
# ---------------------------------------------------------------------------

class TestEVCalculator:
    def test_ev_above_threshold(self, trained_dc):
        """Sólo se devuelven value bets con EV ≥ threshold."""
        from scripts.analysis.ev_calculator import calculate_ev_all_markets
        from scripts.config import EV_THRESHOLD

        preds = trained_dc.get_all_markets(
            "Spain", "Germany", 2050.0, 2000.0, neutral=True
        )

        # Odds sintéticas con EV positivo claro para h2h home win
        # P(Spain win) ≈ 0.45-0.55; cuota 2.3 → EV ≈ +5% o más
        prob_home = preds["prob_home_win"]
        injected_price = round(1.0 / prob_home * 1.07, 2)  # 7% de margen favorable

        mock_odds = {
            "bet365": {
                "h2h": {
                    "outcomes": {
                        "Spain": {"price": injected_price, "prob_fair": prob_home},
                        "Draw":  {"price": 4.0, "prob_fair": preds["prob_draw"]},
                        "Germany": {"price": 4.5, "prob_fair": preds["prob_away_win"]},
                    }
                }
            }
        }

        value_bets = calculate_ev_all_markets(
            preds, mock_odds, "Spain", "Germany", EV_THRESHOLD
        )
        for bet in value_bets:
            assert bet["best_ev"] >= EV_THRESHOLD, (
                f"EV {bet['best_ev']} < threshold {EV_THRESHOLD}"
            )

    def test_output_has_required_fields(self, trained_dc):
        """Cada value bet tiene los campos requeridos por ValueBetCard."""
        from scripts.analysis.ev_calculator import calculate_ev_all_markets

        preds = trained_dc.get_all_markets(
            "France", "Brazil", 2100.0, 2080.0, neutral=True
        )
        prob_home = preds["prob_home_win"]
        mock_odds = {
            "winamax": {
                "h2h": {
                    "outcomes": {
                        "France": {"price": round(1.0 / prob_home * 1.08, 2), "prob_fair": prob_home},
                        "Draw":   {"price": 3.8, "prob_fair": preds["prob_draw"]},
                        "Brazil": {"price": 4.0, "prob_fair": preds["prob_away_win"]},
                    }
                }
            }
        }
        value_bets = calculate_ev_all_markets(preds, mock_odds, "France", "Brazil", 0.0)
        required = {"market", "model_prob", "fair_odds", "best_ev", "best_bookmaker",
                    "best_odds", "where_to_bet"}
        for bet in value_bets:
            missing = required - set(bet.keys())
            assert not missing, f"Campos faltantes: {missing}"


# ---------------------------------------------------------------------------
# Test 6 — PlayerMarketAnalyzer: estructura y rangos de probabilidad
# ---------------------------------------------------------------------------

class TestPlayerMarkets:
    @pytest.fixture(scope="class")
    def analyzer(self):
        if not os.path.exists(_SQUADS):
            pytest.skip(f"Plantillas no disponibles: {_SQUADS}")
        from scripts.analysis.player_markets import PlayerMarketAnalyzer
        return PlayerMarketAnalyzer(_SQUADS)

    def test_loads_squads(self, analyzer):
        assert len(analyzer.squads) > 0

    def test_anytime_scorer_prob_in_range(self, analyzer, trained_dc):
        """Prob goleador esporádico debe estar en (0, 1)."""
        preds = trained_dc.get_all_markets(
            "Spain", "Germany", 2050.0, 2000.0, neutral=True
        )
        result = analyzer.analyze_match_players("Spain", "Germany", preds)
        all_scorers = result.get("home_players", []) + result.get("away_players", [])
        for player_data in all_scorers:
            prob = player_data["markets"]["anytime_scorer"]["prob_anytime_scorer"]
            assert 0.0 <= prob <= 1.0, (
                f"Prob fuera de rango para {player_data['name']}: {prob}"
            )

    def test_top_picks_sorted_descending(self, analyzer, trained_dc):
        """top_home_picks y top_away_picks deben estar ordenados de mayor a menor prob."""
        preds = trained_dc.get_all_markets(
            "Spain", "Germany", 2050.0, 2000.0, neutral=True
        )
        result = analyzer.analyze_match_players("Spain", "Germany", preds)
        for key in ("top_home_picks", "top_away_picks"):
            picks = result.get(key, [])
            probs = [p["prob_anytime_scorer"] for p in picks]
            assert probs == sorted(probs, reverse=True), (
                f"{key} no está ordenado: {probs}"
            )

    def test_gk_prob_is_zero(self, analyzer, trained_dc):
        """Los porteros no deben aparecer en top_picks (prob=0)."""
        preds = trained_dc.get_all_markets(
            "Spain", "Germany", 2050.0, 2000.0, neutral=True
        )
        result = analyzer.analyze_match_players("Spain", "Germany", preds)
        for key in ("top_home_picks", "top_away_picks"):
            for pick in result.get(key, []):
                assert pick["position"] != "GK", (
                    f"Portero en top picks: {pick['name']}"
                )
