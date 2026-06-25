import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.models.elo import EloModel
from scripts.models.normalizer import normalize_team_name
from scripts.models.poisson import DixonColesModel


# ── EloModel ──────────────────────────────────────────────────────────── #

def test_elo_expected_probability_equal_teams():
    model = EloModel()
    model.ratings = {"A": 1500.0, "B": 1500.0}
    assert abs(model.predict("A", "B") - 0.5) < 0.001


def test_elo_k_factor_world_cup_group():
    model = EloModel()
    assert model.get_k_factor("FIFA World Cup", stage="group") == 50


def test_elo_k_factor_world_cup_final():
    model = EloModel()
    assert model.get_k_factor("FIFA World Cup", stage="Final") == 60


def test_elo_k_factor_world_cup_round_of_16():
    model = EloModel()
    assert model.get_k_factor("FIFA World Cup", stage="Round of 16") == 60


def test_elo_k_factor_friendly():
    model = EloModel()
    assert model.get_k_factor("Friendly") == 10


def test_elo_k_factor_qualification():
    model = EloModel()
    assert model.get_k_factor("FIFA World Cup qualification") == 30


def test_elo_k_factor_nations_league():
    model = EloModel()
    assert model.get_k_factor("UEFA Nations League") == 20


def test_elo_home_advantage():
    model = EloModel()
    model.ratings = {"Spain": 2000.0, "Germany": 2000.0}
    prob_neutral = model.predict("Spain", "Germany", neutral=True)
    prob_home = model.predict("Spain", "Germany", neutral=False)
    assert prob_home > prob_neutral


def test_elo_higher_rated_team_favored():
    model = EloModel()
    model.ratings = {"Strong": 2000.0, "Weak": 1600.0}
    prob = model.predict("Strong", "Weak", neutral=True)
    assert prob > 0.5


def test_elo_get_rating_unknown_team():
    model = EloModel()
    assert model.get_rating("Atlantis") == model.default_rating


# ── DixonColesModel ───────────────────────────────────────────────────── #

def test_dixon_coles_factor_00():
    dc = DixonColesModel()
    rho = -0.05
    lam = mu = 1.2
    factor = dc._dixon_coles_factor(0, 0, lam, mu, rho)
    assert factor == pytest.approx(1.0 - lam * mu * rho)


def test_dixon_coles_factor_10():
    dc = DixonColesModel()
    rho = -0.05
    factor = dc._dixon_coles_factor(1, 0, 1.2, 1.2, rho)
    assert factor == pytest.approx(1.0 + 1.2 * rho)


def test_dixon_coles_factor_01():
    dc = DixonColesModel()
    rho = -0.05
    factor = dc._dixon_coles_factor(0, 1, 1.2, 1.2, rho)
    assert factor == pytest.approx(1.0 + 1.2 * rho)


def test_dixon_coles_factor_11():
    dc = DixonColesModel()
    rho = -0.05
    factor = dc._dixon_coles_factor(1, 1, 1.2, 1.2, rho)
    assert factor == pytest.approx(1.0 - rho)


def test_dixon_coles_factor_high_score():
    dc = DixonColesModel()
    # Any scoreline with x>1 or y>1 → τ = 1
    assert dc._dixon_coles_factor(3, 2, 1.2, 1.2, -0.05) == 1.0
    assert dc._dixon_coles_factor(2, 0, 1.2, 1.2, -0.05) == 1.0


def test_predict_match_probabilities_sum_to_one():
    dc = DixonColesModel()
    dc.params = (0.25, 0.40, 0.05, -0.40, -0.05)
    result = dc.predict_match("Spain", "Germany", 2134, 1954)
    total = result["prob_home_win"] + result["prob_draw"] + result["prob_away_win"]
    assert abs(total - 1.0) < 0.001


def test_predict_match_contains_all_keys():
    dc = DixonColesModel()
    result = dc.predict_match("Spain", "Germany", 2134, 1954)
    for key in ("prob_home_win", "prob_draw", "prob_away_win",
                "prob_over_0_5", "prob_over_1_5", "prob_over_2_5", "prob_over_3_5",
                "prob_btts", "expected_goals_home", "expected_goals_away",
                "top_scorelines"):
        assert key in result


def test_predict_match_top_scorelines_count():
    dc = DixonColesModel()
    result = dc.predict_match("Spain", "Germany", 2134, 1954)
    assert len(result["top_scorelines"]) == 8


def test_predict_match_higher_elo_favored():
    dc = DixonColesModel()
    result = dc.predict_match("Strong", "Weak", 2100, 1600, neutral=True)
    assert result["prob_home_win"] > result["prob_away_win"]


# ── normalizer ───────────────────────────────────────────────────────── #

def test_normalize_korea_republic():
    assert normalize_team_name("Korea Republic") == "South Korea"


def test_normalize_usa():
    assert normalize_team_name("USA") == "United States"


def test_normalize_turkiye():
    assert normalize_team_name("Türkiye") == "Turkey"


def test_normalize_west_germany():
    assert normalize_team_name("West Germany") == "Germany"


def test_normalize_ir_iran():
    assert normalize_team_name("IR Iran") == "Iran"


def test_normalize_unknown_passthrough():
    assert normalize_team_name("SomeFictionalTeam") == "SomeFictionalTeam"


def test_normalize_none():
    assert normalize_team_name(None) == "Unknown"


def test_normalize_czech_republic():
    assert normalize_team_name("Czech Republic") == "Czechia"
