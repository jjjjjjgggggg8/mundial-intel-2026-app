import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ingestion.historical import filter_competitive, normalize_team_name
from scripts.ingestion.odds import extract_fair_odds, save_odds_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_odds(home_price: float = 2.1, draw_price: float = 3.3,
                   away_price: float = 3.5) -> dict:
    return {
        "evt1": {
            "home_team":          "Team A",
            "away_team":          "Team B",
            "commence_time":      "2026-06-25T19:00:00Z",
            "bookmakers": {
                "bet365": {
                    "last_update": "2026-06-25T12:00:00Z",
                    "markets": {
                        "h2h": [
                            {"name": "Team A", "price": home_price},
                            {"name": "Draw",   "price": draw_price},
                            {"name": "Team B", "price": away_price},
                        ]
                    },
                }
            },
            "requests_remaining": 100,
            "fetched_at":         "2026-06-25T12:00:00Z",
        }
    }


# ---------------------------------------------------------------------------
# historical.py
# ---------------------------------------------------------------------------

def test_normalize_known_names():
    assert normalize_team_name("Korea Republic") == "South Korea"
    assert normalize_team_name("USA") == "United States"
    assert normalize_team_name("West Germany") == "Germany"
    assert normalize_team_name("Desconocido FC") == "Desconocido FC"


def test_filter_competitive_removes_friendlies():
    df = pd.DataFrame({
        "tournament": ["FIFA World Cup", "UEFA Euro", "Friendly"],
        "home_team":  ["A", "B", "C"],
        "away_team":  ["D", "E", "F"],
    })
    result = filter_competitive(df)
    assert len(result) == 2
    assert "Friendly" not in result["tournament"].values


def test_filter_competitive_also_removes_friendly_variants():
    df = pd.DataFrame({
        "tournament": ["Copa América", "Friendly (short tournament)", "FIFA World Cup"],
        "home_team":  ["A", "B", "C"],
        "away_team":  ["D", "E", "F"],
    })
    result = filter_competitive(df)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# odds.py — extract_fair_odds
# ---------------------------------------------------------------------------

def test_extract_fair_odds_sums_to_one():
    raw = _make_raw_odds()
    fair = extract_fair_odds(raw)
    probs = [
        o["prob_fair"]
        for o in fair["evt1"]["bet365"]["h2h"]["outcomes"].values()
    ]
    assert sum(probs) == pytest.approx(1.0, abs=1e-6)


def test_extract_fair_odds_power_no_negative():
    raw = _make_raw_odds()
    fair = extract_fair_odds(raw)
    probs = [
        o["prob_fair"]
        for o in fair["evt1"]["bet365"]["h2h"]["outcomes"].values()
    ]
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_extract_fair_odds_booksum_in_range():
    raw = _make_raw_odds()
    fair = extract_fair_odds(raw)
    booksum = fair["evt1"]["bet365"]["h2h"]["booksum"]
    assert 1.03 <= booksum <= 1.12


def test_extract_fair_odds_multiplicative_fallback():
    raw = _make_raw_odds()
    fair = extract_fair_odds(raw, method="multiplicative")
    probs = [
        o["prob_fair"]
        for o in fair["evt1"]["bet365"]["h2h"]["outcomes"].values()
    ]
    assert sum(probs) == pytest.approx(1.0, abs=1e-6)
    assert fair["evt1"]["bet365"]["h2h"]["method"] == "multiplicative"
    assert fair["evt1"]["bet365"]["h2h"]["k"] is None


# ---------------------------------------------------------------------------
# odds.py — save_odds_snapshot
# ---------------------------------------------------------------------------

def test_save_odds_snapshot_creates_dir(tmp_path):
    nested = str(tmp_path / "nested" / "subdir" / "odds.json")
    odds = {
        "evt1": {
            "home_team": "A", "away_team": "B",
            "bookmakers": {}, "requests_remaining": 100,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
    }
    save_odds_snapshot(odds, path=nested)
    assert Path(nested).exists()


def test_save_odds_snapshot_writes_meta(tmp_path):
    path = str(tmp_path / "odds.json")
    odds = {
        "evt1": {
            "home_team": "A", "away_team": "B",
            "bookmakers": {}, "requests_remaining": 100,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
    }
    save_odds_snapshot(odds, path=path)
    with open(path) as f:
        result = json.load(f)
    assert "_meta" in result
    assert result["_meta"]["total_matches"] == 1
    assert result["_meta"]["updated_count"] == 1
    assert result["_meta"]["skipped_fresh"] == 0


def test_save_odds_snapshot_skip_fresh(tmp_path):
    path = str(tmp_path / "odds.json")
    # fetched_at set to current UTC so the snapshot is "fresh" (< 6h)
    recent_ts = datetime.utcnow().isoformat() + "Z"
    odds = {
        "evt1": {
            "home_team": "A", "away_team": "B",
            "bookmakers": {}, "requests_remaining": 100,
            "fetched_at": recent_ts,
        },
        "evt2": {
            "home_team": "C", "away_team": "D",
            "bookmakers": {}, "requests_remaining": 99,
            "fetched_at": recent_ts,
        },
    }
    # First save persists both events
    save_odds_snapshot(odds, path=path)

    # Second save immediately after: both events are < 6h old → both skipped
    save_odds_snapshot(odds, path=path)

    with open(path) as f:
        result = json.load(f)

    assert result["_meta"]["skipped_fresh"] == 2
    assert result["_meta"]["updated_count"] == 0
