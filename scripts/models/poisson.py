import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from .normalizer import normalize_team_name

_MAX_GOALS = 9  # 0..8 inclusive → 9×9 matrix


class DixonColesModel:
    def __init__(self):
        # (a, b, c, d, rho)
        self.params: tuple[float, float, float, float, float] = (
            0.25, 0.40, 0.05, -0.40, -0.05
        )

    # ------------------------------------------------------------------ #
    #  Dixon-Coles τ correction                                            #
    # ------------------------------------------------------------------ #

    def _dixon_coles_factor(self, x: int, y: int,
                             lam: float, mu: float, rho: float) -> float:
        if x == 0 and y == 0:
            return 1.0 - lam * mu * rho
        if x == 1 and y == 0:
            return 1.0 + mu * rho
        if x == 0 and y == 1:
            return 1.0 + lam * rho
        if x == 1 and y == 1:
            return 1.0 - rho
        return 1.0

    # ------------------------------------------------------------------ #
    #  Fitting                                                              #
    # ------------------------------------------------------------------ #

    def fit(self, matches_df: pd.DataFrame) -> None:
        from .elo import EloModel

        df = matches_df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # Only rows with complete scores
        df = df.dropna(subset=["home_score", "away_score"])
        df = df[df["home_score"].astype(str) != "NA"]
        df = df[df["away_score"].astype(str) != "NA"]
        try:
            df["home_score"] = df["home_score"].astype(int)
            df["away_score"] = df["away_score"].astype(int)
        except (ValueError, TypeError):
            df = df[pd.to_numeric(df["home_score"], errors="coerce").notna()]
            df["home_score"] = df["home_score"].astype(int)
            df["away_score"] = df["away_score"].astype(int)

        # Keep only World Cup matches for calibration (richest signal)
        wc = df[df["tournament"] == "FIFA World Cup"].copy()
        if len(wc) < 50:
            wc = df  # fallback to all data

        # Build Elo model once on all available data up to each WC match
        elo = EloModel()
        elo.fit(df)

        records = []
        for _, row in wc.iterrows():
            home = normalize_team_name(str(row["home_team"]))
            away = normalize_team_name(str(row["away_team"]))
            neutral_flag = str(row.get("neutral", "TRUE")).upper() not in ("FALSE", "0", "F")

            elo_a = elo.get_rating(home, date=row["date"])
            elo_b = elo.get_rating(away, date=row["date"])
            home_bonus = 0.0 if neutral_flag else 75.0
            elo_adv = (elo_a + home_bonus - elo_b) / 400.0
            records.append((row["home_score"], row["away_score"], elo_adv))

        def neg_log_likelihood(params):
            a, b, c, d, rho = params
            ll = 0.0
            for x, y, adv in records:
                lam = math.exp(a + b * adv)
                mu  = math.exp(c + d * adv)
                # Clamp rho to feasibility region
                rho_eff = max(-1.0 / max(lam, 1e-9), min(rho, 1.0 / max(lam * mu, 1e-9)))
                tau = self._dixon_coles_factor(x, y, lam, mu, rho_eff)
                if tau <= 0:
                    tau = 1e-10
                ll += (math.log(tau)
                       + x * math.log(lam) - lam - math.lgamma(x + 1)
                       + y * math.log(mu)  - mu  - math.lgamma(y + 1))
            return -ll

        x0 = list(self.params)
        result = minimize(neg_log_likelihood, x0, method="Nelder-Mead",
                          options={"maxiter": 10000, "xatol": 1e-6, "fatol": 1e-6})

        a, b, c, d, rho = result.x
        self.params = (a, b, c, d, rho)
        print(f"Parámetros calibrados: a={a:.4f} b={b:.4f} c={c:.4f} d={d:.4f} rho={rho:.4f}")

    # ------------------------------------------------------------------ #
    #  Prediction                                                           #
    # ------------------------------------------------------------------ #

    def predict_match(self, team_a: str, team_b: str,
                      elo_a: float, elo_b: float,
                      neutral: bool = True) -> dict:
        a, b, c, d, rho = self.params
        home_bonus = 0.0 if neutral else 75.0
        elo_adv = (elo_a + home_bonus - elo_b) / 400.0

        lam = math.exp(a + b * elo_adv)
        mu  = math.exp(c + d * elo_adv)

        # Clamp rho
        rho_eff = max(-1.0 / max(lam, 1e-9), min(rho, 1.0 / max(lam * mu, 1e-9)))

        # Build probability matrix
        prob_matrix = np.zeros((_MAX_GOALS, _MAX_GOALS))
        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                tau = self._dixon_coles_factor(i, j, lam, mu, rho_eff)
                prob_matrix[i, j] = (tau
                                     * poisson.pmf(i, lam)
                                     * poisson.pmf(j, mu))

        total = prob_matrix.sum()
        if total > 0:
            prob_matrix /= total

        # 1X2
        prob_home_win = float(np.tril(prob_matrix, -1).sum())
        prob_draw     = float(np.trace(prob_matrix))
        prob_away_win = float(np.triu(prob_matrix, 1).sum())

        # Totals
        goals = np.array([[i + j for j in range(_MAX_GOALS)]
                           for i in range(_MAX_GOALS)])
        prob_over_0_5 = float(prob_matrix[goals > 0].sum())
        prob_over_1_5 = float(prob_matrix[goals > 1].sum())
        prob_over_2_5 = float(prob_matrix[goals > 2].sum())
        prob_over_3_5 = float(prob_matrix[goals > 3].sum())

        # BTTS
        home_scores = prob_matrix.copy()
        home_scores[0, :] = 0.0
        away_scores = home_scores.copy()
        away_scores[:, 0] = 0.0
        prob_btts = float(away_scores.sum())

        # Top 8 scorelines
        flat = [(prob_matrix[i, j], f"{i}-{j}")
                for i in range(_MAX_GOALS) for j in range(_MAX_GOALS)]
        flat.sort(reverse=True)
        top_scorelines = [{"score": s, "prob": round(p, 4)} for p, s in flat[:8]]

        return {
            "prob_home_win":        round(prob_home_win, 4),
            "prob_draw":            round(prob_draw, 4),
            "prob_away_win":        round(prob_away_win, 4),
            "prob_over_0_5":        round(prob_over_0_5, 4),
            "prob_over_1_5":        round(prob_over_1_5, 4),
            "prob_over_2_5":        round(prob_over_2_5, 4),
            "prob_over_3_5":        round(prob_over_3_5, 4),
            "prob_btts":            round(prob_btts, 4),
            "expected_goals_home":  round(lam, 4),
            "expected_goals_away":  round(mu, 4),
            "top_scorelines":       top_scorelines,
        }
