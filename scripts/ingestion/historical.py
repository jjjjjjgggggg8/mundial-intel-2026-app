"""Historical match data ingestion from Kaggle CSV and openfootball WC-2026 JSON."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

_TEAM_ALIASES: dict[str, str] = {
    "Korea Republic":         "South Korea",
    "Korea DPR":              "North Korea",
    "IR Iran":                "Iran",
    "USA":                    "United States",
    "United States":          "United States",
    "Cape Verde Islands":     "Cape Verde",
    "China PR":               "China",
    "Chinese Taipei":         "Taiwan",
    "Ivory Coast":            "Côte d'Ivoire",
    "Czech Republic":         "Czechia",
    "Bosnia-Herzegovina":     "Bosnia and Herzegovina",
    "Saint Kitts and Nevis":  "St. Kitts and Nevis",
    "Swaziland":              "Eswatini",
    "Macedonia":              "North Macedonia",
    "FYR Macedonia":          "North Macedonia",
    "Yugoslavia":             "Serbia",
    "Soviet Union":           "Russia",
    "West Germany":           "Germany",
    "Czechoslovakia":         "Czechia",
    "Trinidad and Tobago":    "Trinidad & Tobago",
    "Congo DR":               "DR Congo",
    "Congo":                  "Republic of Congo",
    "Kyrgyz Republic":        "Kyrgyzstan",
    "Turkey":                 "Türkiye",
    "Curacao":                "Curaçao",
    "Netherlands Antilles":   "Curaçao",
    "São Tomé and Príncipe":  "Sao Tome and Principe",
    "Reunion":                "Réunion",
    "England":                "England",
    "Scotland":               "Scotland",
    "Wales":                  "Wales",
    "Northern Ireland":       "Northern Ireland",
    "Tahiti":                 "Tahiti",
}


def normalize_team_name(name: str) -> str:
    stripped = name.strip()
    return _TEAM_ALIASES.get(stripped, stripped)


def load_matches(path: str = "data/raw/results.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[["date", "home_team", "away_team", "home_score", "away_score",
             "tournament", "neutral"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["home_score", "away_score"]).reset_index(drop=True)
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["home_team"] = df["home_team"].apply(normalize_team_name)
    df["away_team"] = df["away_team"].apply(normalize_team_name)
    df["neutral"] = df["neutral"].map({"TRUE": True, "FALSE": False}).fillna(False)
    return df.reset_index(drop=True)


def filter_competitive(df: pd.DataFrame) -> pd.DataFrame:
    mask = ~df["tournament"].str.contains("Friendly", regex=False)
    return df[mask].reset_index(drop=True)


def _parse_kickoff_utc(date_str: str, time_str: str) -> str:
    # time_str format: "HH:MM UTC±N"  e.g. "13:00 UTC-6" or "20:00 UTC-5"
    m = re.match(r"(\d{1,2}):(\d{2})\s+UTC([+-]\d+)", time_str)
    if not m or not date_str:
        return ""
    h, mn, offset = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        local_dt = datetime.fromisoformat(date_str).replace(hour=h, minute=mn)
        utc_dt = local_dt - timedelta(hours=offset)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError):
        return ""


def load_wc2026_calendar(path: str = "data/raw/wc2026/worldcup.json") -> pd.DataFrame:
    """Parse the openfootball worldcup.json fixture list into a tidy DataFrame.

    The actual JSON (data/raw/wc2026/worldcup.json) uses a flat ``matches``
    array where each entry carries ``"time": "HH:MM UTC±N"``.  kickoff_utc is
    built from that per-match UTC offset rather than a single zone; the offset
    still reflects the venue's wall-clock zone, not DST-aware IANA zones, so
    it may be off by 1 h for venues that observe DST (e.g. Vancouver, Toronto).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"World Cup calendar JSON not found: {path}")

    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Malformed JSON in {path}: {e.msg}", e.doc, e.pos
        )

    # Build team-name → FIFA-code lookup from the sibling teams file.
    code_map: dict[str, str] = {}
    teams_path = p.parent / "worldcup.teams.json"
    if teams_path.exists():
        with teams_path.open(encoding="utf-8") as f:
            for t in json.load(f):
                code_map[t["name"]] = t.get("fifa_code", t["name"][:3].upper())

    def _code(raw_name: str) -> str:
        return code_map.get(raw_name, raw_name[:3].upper())

    rows = []
    for m in data.get("matches", []):
        date_str: str = m.get("date", "")
        time_str: str = m.get("time", "")
        raw1: str = m.get("team1", "")
        raw2: str = m.get("team2", "")

        date_iso = date_str.replace("-", "")
        match_id = f"{_code(raw1)}-{_code(raw2)}-{date_iso}"

        try:
            match_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            match_date = None

        rows.append({
            "match_id":    match_id,
            "phase":       m.get("round", ""),
            "date":        match_date,
            "home_team":   normalize_team_name(raw1),
            "away_team":   normalize_team_name(raw2),
            "venue":       m.get("ground", ""),
            "kickoff_utc": _parse_kickoff_utc(date_str, time_str),
        })

    return pd.DataFrame(rows)
