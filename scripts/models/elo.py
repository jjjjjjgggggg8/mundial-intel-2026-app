import math
from collections import defaultdict
from datetime import date as date_type

import pandas as pd

from .normalizer import normalize_team_name

_WC2026_HOSTS = {"United States", "Canada", "Mexico"}

_KNOCKOUT_KEYWORDS = {
    "round of 16", "quarter-final", "semi-final", "final",
    "third place", "quarterfinal", "semifinal",
}

_INITIAL_RATINGS = {
    "Argentina":     2144, "Spain":         2134, "France":        2090,
    "England":       2028, "Colombia":      2006, "Portugal":      1988,
    "Brazil":        1986, "Netherlands":   1972, "Germany":       1954,
    "Norway":        1951, "Japan":         1925, "Croatia":       1896,
    "Mexico":        1896, "Switzerland":   1885, "Denmark":       1869,
    "Italy":         1869, "Belgium":       1869, "Morocco":       1866,
    "Ecuador":       1864, "Uruguay":       1851, "Austria":       1841,
    "United States": 1820, "Senegal":       1817, "Paraguay":      1816,
    "Turkey":        1813, "Australia":     1799, "Algeria":       1780,
    "Ukraine":       1780, "Canada":        1777, "Russia":        1772,
    "South Korea":   1771, "Scotland":      1768, "Nigeria":       1767,
    "Iran":          1766,
}


class EloModel:
    def __init__(self, default_rating: float = 1500.0):
        self.default_rating = default_rating
        self.ratings: dict[str, float] = {}
        self.ratings_history: dict[str, dict] = defaultdict(dict)

    # ------------------------------------------------------------------ #
    #  Public helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_k_factor(self, tournament: str, stage: str | None = None) -> int:
        t = (tournament or "").strip()
        s = (stage or "").lower()

        if t == "FIFA World Cup":
            if any(kw in s for kw in _KNOCKOUT_KEYWORDS):
                return 60
            return 50

        if t in ("UEFA Euro", "Copa América", "Africa Cup of Nations",
                 "African Cup of Nations", "AFC Asian Cup", "Gold Cup"):
            return 40

        if "World Cup qualification" in t:
            return 30

        if "UEFA Nations League" in t or "CONCACAF Nations League" in t:
            return 20

        if "Friendly" in t:
            return 10

        # Copa América qualifiers, AFCON qualifiers, etc.
        if any(x in t for x in ("qualification", "qualifier", "Qualifier")):
            return 30

        # Copa América, EURO qualifiers, continental championships
        if any(x in t for x in ("Copa América", "UEFA Euro", "Africa Cup",
                                  "AFC Asian", "Gold Cup")):
            return 40

        return 20

    def get_rating(self, team: str, date=None) -> float:
        team = normalize_team_name(team)
        if date is None:
            return self.ratings.get(team, self.default_rating)

        history = self.ratings_history.get(team)
        if not history:
            return self.default_rating

        # Convert to pandas Timestamp for uniform comparison
        target = pd.Timestamp(date)
        best_rating = self.default_rating
        best_date = None
        for d, r in history.items():
            pd_d = pd.Timestamp(d)
            if pd_d < target:
                if best_date is None or pd_d > best_date:
                    best_date = pd_d
                    best_rating = r
        return best_rating

    def predict(self, team_a: str, team_b: str, neutral: bool = True) -> float:
        team_a = normalize_team_name(team_a)
        team_b = normalize_team_name(team_b)
        ra = self.ratings.get(team_a, self.default_rating)
        rb = self.ratings.get(team_b, self.default_rating)
        home_bonus = 0.0 if neutral else 75.0
        dr = (ra + home_bonus) - rb
        return 1.0 / (10.0 ** (-dr / 400.0) + 1.0)

    # ------------------------------------------------------------------ #
    #  Fitting                                                              #
    # ------------------------------------------------------------------ #

    def fit(self, matches_df: pd.DataFrame) -> None:
        self.ratings = {normalize_team_name(t): float(r)
                        for t, r in _INITIAL_RATINGS.items()}
        self.ratings_history = defaultdict(dict)

        df = matches_df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)

        for _, row in df.iterrows():
            home = normalize_team_name(str(row["home_team"]))
            away = normalize_team_name(str(row["away_team"]))
            match_date = row["date"]

            try:
                home_score = int(row["home_score"])
                away_score = int(row["away_score"])
            except (ValueError, TypeError):
                continue

            tournament = str(row.get("tournament", ""))
            neutral_flag = str(row.get("neutral", "TRUE")).upper() not in ("FALSE", "0", "F")

            # Special case: WC2026 hosts play at home despite neutral=TRUE in CSV
            if "2026" in str(match_date) and tournament == "FIFA World Cup":
                if home in _WC2026_HOSTS:
                    neutral_flag = False

            k = self.get_k_factor(tournament)

            ra = self.ratings.get(home, self.default_rating)
            rb = self.ratings.get(away, self.default_rating)
            home_bonus = 0.0 if neutral_flag else 75.0
            dr = (ra + home_bonus) - rb

            we_home = 1.0 / (10.0 ** (-dr / 400.0) + 1.0)
            we_away = 1.0 - we_home

            goal_diff = abs(home_score - away_score)

            if home_score > away_score:
                result_home, result_away = 1.0, 0.0
            elif home_score < away_score:
                result_home, result_away = 0.0, 1.0
            else:
                result_home = result_away = 0.5

            # Margin multiplier W
            if home_score == away_score:
                w = 1.0
            else:
                elo_diff_sign_home = dr * math.copysign(1.0, result_home - 0.5)
                w = math.log(goal_diff + 1) * (2.2 / (elo_diff_sign_home * 0.001 + 2.2))

            ra_new = ra + k * w * (result_home - we_home)
            rb_new = rb + k * w * (result_away - we_away)

            self.ratings[home] = ra_new
            self.ratings[away] = rb_new

            date_key = match_date.date() if hasattr(match_date, "date") else match_date
            self.ratings_history[home][date_key] = ra_new
            self.ratings_history[away][date_key] = rb_new
