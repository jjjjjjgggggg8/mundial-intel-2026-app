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

    # ------------------------------------------------------------------ #
    #  Matriz interna reutilizable                                          #
    # ------------------------------------------------------------------ #

    def _build_matrix(self, team_a: str, team_b: str,
                      elo_a: float, elo_b: float,
                      neutral: bool = True):
        """Devuelve (prob_matrix, lambda_home, mu_away) sin repetir lógica."""
        a, b, c, d, rho = self.params
        home_bonus = 0.0 if neutral else 75.0
        elo_adv = (elo_a + home_bonus - elo_b) / 400.0

        lam = math.exp(a + b * elo_adv)
        mu  = math.exp(c + d * elo_adv)
        rho_eff = max(-1.0 / max(lam, 1e-9), min(rho, 1.0 / max(lam * mu, 1e-9)))

        prob_matrix = np.zeros((_MAX_GOALS, _MAX_GOALS))
        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                tau = self._dixon_coles_factor(i, j, lam, mu, rho_eff)
                prob_matrix[i, j] = tau * poisson.pmf(i, lam) * poisson.pmf(j, mu)

        total = prob_matrix.sum()
        if total > 0:
            prob_matrix /= total

        return prob_matrix, lam, mu

    # ------------------------------------------------------------------ #
    #  Nuevos mercados de equipo                                            #
    # ------------------------------------------------------------------ #

    def predict_asian_handicap(self, matrix: np.ndarray, handicap: float) -> dict:
        """
        Calcula probabilidades para el mercado de Hándicap Asiático (Bet365).
        handicap: desde perspectiva local (negativo = local favorito).
        Líneas de cuarto (±0.25, ±0.75, ±1.25…) se dividen internamente en dos mitades.
        """
        # Líneas de cuarto: promedio de dos líneas adyacentes
        frac = handicap % 0.5
        if abs(frac) > 1e-9 and abs(frac - 0.5) > 1e-9:
            lower = math.floor(handicap * 2) / 2.0
            upper = lower + 0.5
            lo = self.predict_asian_handicap(matrix, lower)
            hi = self.predict_asian_handicap(matrix, upper)
            ph = (lo["prob_home_covers"] + hi["prob_home_covers"]) / 2.0
            pp = (lo["prob_push"] + hi["prob_push"]) / 2.0
            pa = max(1.0 - ph - pp, 0.0)
            return {
                "handicap": handicap,
                "prob_home_covers": round(ph, 4),
                "prob_push":        round(pp, 4),
                "prob_away_covers": round(pa, 4),
                "description": f"AH {handicap:+.2f} (split: {lower:+.1f}/{upper:+.1f})",
            }

        is_half = abs(handicap % 1.0) > 1e-9
        prob_home = prob_push = prob_away = 0.0

        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                adj = i + handicap - j
                p   = matrix[i, j]
                if is_half:
                    if adj > 0:
                        prob_home += p
                    else:
                        prob_away += p
                else:
                    if adj > 1e-9:
                        prob_home += p
                    elif adj > -1e-9:
                        prob_push += p
                    else:
                        prob_away += p

        total = prob_home + prob_push + prob_away
        if total > 0:
            prob_home /= total; prob_push /= total; prob_away /= total

        m = abs(int(round(handicap)))
        if handicap < 0:
            desc = f"AH {handicap:+.1f}: Local necesita ganar por {m+1}+ goles"
        else:
            desc = f"AH {handicap:+.1f}: Visitante necesita ganar por {m+1}+ goles"

        return {
            "handicap":         handicap,
            "prob_home_covers": round(prob_home, 4),
            "prob_push":        round(prob_push, 4),
            "prob_away_covers": round(prob_away, 4),
            "description":      desc,
        }

    def predict_asian_total(self, matrix: np.ndarray, line: float) -> dict:
        """
        Calcula probabilidades para la Línea de Gol Asiática (Bet365).
        Líneas enteras tienen posibilidad de PUSH (devolución de apuesta).
        """
        is_int = abs(line - round(line)) < 1e-9
        prob_over = prob_exact = prob_under = 0.0

        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                tot = i + j
                p   = matrix[i, j]
                if tot > line + 1e-9:
                    prob_over += p
                elif is_int and abs(tot - line) < 1e-9:
                    prob_exact += p
                else:
                    prob_under += p

        total = prob_over + prob_exact + prob_under
        if total > 0:
            prob_over /= total; prob_exact /= total; prob_under /= total

        return {
            "line":      line,
            "prob_over": round(prob_over, 4),
            "prob_push": round(prob_exact, 4),
            "prob_under": round(prob_under, 4),
            "is_asian":  is_int,
        }

    def predict_european_handicap(self, matrix: np.ndarray, handicap: float) -> dict:
        """
        Hándicap Europeo 3-way de Winamax (siempre entero, tres resultados posibles).
        handicap: entero desde perspectiva local (ej. -1 = local parte perdiendo 1).
        """
        h = int(round(handicap))
        prob_home = prob_draw = prob_away = 0.0

        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                adj = (i + h) - j
                p   = matrix[i, j]
                if adj > 0:
                    prob_home += p
                elif adj == 0:
                    prob_draw += p
                else:
                    prob_away += p

        total = prob_home + prob_draw + prob_away
        if total > 0:
            prob_home /= total; prob_draw /= total; prob_away /= total

        m = abs(h)
        if h < 0:
            desc = (f"EH {h}: Local gana por {m+1}+ / "
                    f"Empate ajustado si gana por {m} / Visitante si empata o pierde")
        elif h > 0:
            desc = (f"EH +{h}: Visitante gana por {m+1}+ / "
                    f"Empate ajustado si gana por {m} / Local si empata o pierde")
        else:
            desc = "EH 0: equivalente al 1X2 sin hándicap"

        return {
            "handicap":          h,
            "prob_home_win_adj": round(prob_home, 4),
            "prob_draw_adj":     round(prob_draw, 4),
            "prob_away_win_adj": round(prob_away, 4),
            "description":       desc,
        }

    def predict_goal_range(self, matrix: np.ndarray,
                           min_goals: int, max_goals: int) -> dict:
        """
        Probabilidad de que el total de goles caiga en [min_goals, max_goals].
        Usa max_goals=99 para el rango abierto '6+'.
        """
        prob = 0.0
        label = f"{min_goals}-{max_goals}" if max_goals < 99 else f"{min_goals}+"

        for i in range(_MAX_GOALS):
            for j in range(_MAX_GOALS):
                tot = i + j
                if max_goals < 99:
                    if min_goals <= tot <= max_goals:
                        prob += matrix[i, j]
                else:
                    if tot >= min_goals:
                        prob += matrix[i, j]

        return {
            "label":     label,
            "min_goals": min_goals,
            "max_goals": max_goals if max_goals < 99 else None,
            "prob":      round(prob, 4),
        }

    def predict_all_goal_ranges(self, matrix: np.ndarray) -> list:
        """Genera los 4 rangos de goles estándar de Winamax."""
        return [
            self.predict_goal_range(matrix, 0, 1),
            self.predict_goal_range(matrix, 2, 3),
            self.predict_goal_range(matrix, 4, 5),
            self.predict_goal_range(matrix, 6, 99),
        ]

    def predict_corners_asian(self, expected_corners: float, line: float) -> dict:
        """
        Córners Asiáticos de Bet365. Los córners siguen distribución Poisson.
        expected_corners se estima externamente a partir del ratio Elo.
        """
        is_int = abs(line - round(line)) < 1e-9
        lf = math.floor(line)

        if is_int:
            li = int(round(line))
            prob_over  = 1.0 - poisson.cdf(li, expected_corners)
            prob_push  = poisson.pmf(li, expected_corners)
            prob_under = poisson.cdf(li - 1, expected_corners)
        else:
            prob_over  = 1.0 - poisson.cdf(lf, expected_corners)
            prob_push  = 0.0
            prob_under = poisson.cdf(lf, expected_corners)

        return {
            "line":             line,
            "expected_corners": round(expected_corners, 2),
            "prob_over":        round(float(prob_over), 4),
            "prob_push":        round(float(prob_push), 4),
            "prob_under":       round(float(prob_under), 4),
            "is_asian":         is_int,
        }

    def predict_cards_asian(self, expected_cards: float, line: float) -> dict:
        """
        Tarjetas Asiáticas de Bet365. Misma lógica Poisson que los córners.
        """
        is_int = abs(line - round(line)) < 1e-9
        lf = math.floor(line)

        if is_int:
            li = int(round(line))
            prob_over  = 1.0 - poisson.cdf(li, expected_cards)
            prob_push  = poisson.pmf(li, expected_cards)
            prob_under = poisson.cdf(li - 1, expected_cards)
        else:
            prob_over  = 1.0 - poisson.cdf(lf, expected_cards)
            prob_push  = 0.0
            prob_under = poisson.cdf(lf, expected_cards)

        return {
            "line":           line,
            "expected_cards": round(expected_cards, 2),
            "prob_over":      round(float(prob_over), 4),
            "prob_push":      round(float(prob_push), 4),
            "prob_under":     round(float(prob_under), 4),
            "is_asian":       is_int,
        }

    # ------------------------------------------------------------------ #
    #  Método unificado                                                     #
    # ------------------------------------------------------------------ #

    def get_all_markets(self, team_a: str, team_b: str,
                        elo_a: float, elo_b: float,
                        neutral: bool = True) -> dict:
        """
        Calcula todos los mercados disponibles construyendo la matriz una sola vez.
        Devuelve un dict unificado con mercados estándar y todos los nuevos.
        """
        matrix, lam, mu = self._build_matrix(team_a, team_b, elo_a, elo_b, neutral)

        # Mercados estándar (misma lógica que predict_match)
        goals = np.array([[i + j for j in range(_MAX_GOALS)]
                          for i in range(_MAX_GOALS)])

        flat = [(matrix[i, j], f"{i}-{j}")
                for i in range(_MAX_GOALS) for j in range(_MAX_GOALS)]
        flat.sort(reverse=True)

        result: dict = {
            "prob_home_win":       round(float(np.tril(matrix, -1).sum()), 4),
            "prob_draw":           round(float(np.trace(matrix)), 4),
            "prob_away_win":       round(float(np.triu(matrix, 1).sum()), 4),
            "prob_over_0_5":       round(float(matrix[goals > 0].sum()), 4),
            "prob_over_1_5":       round(float(matrix[goals > 1].sum()), 4),
            "prob_over_2_5":       round(float(matrix[goals > 2].sum()), 4),
            "prob_over_3_5":       round(float(matrix[goals > 3].sum()), 4),
            "prob_btts":           round(float(matrix[1:, 1:].sum()), 4),
            "expected_goals_home": round(lam, 4),
            "expected_goals_away": round(mu, 4),
            "top_scorelines":      [{"score": s, "prob": round(p, 4)}
                                    for p, s in flat[:8]],
        }

        # Hándicap Asiático: ±0.5, ±1.0, ±1.5 y cuartos ±0.25, ±0.75, ±1.25
        ah_lines = [-1.5, -1.25, -1.0, -0.75, -0.5, -0.25,
                     0.25,  0.5,  0.75,  1.0,  1.25,  1.5]
        result["asian_handicap"] = {
            str(h): self.predict_asian_handicap(matrix, h) for h in ah_lines
        }

        # Línea de Gol Asiática
        result["asian_total"] = {
            str(l): self.predict_asian_total(matrix, l)
            for l in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
        }

        # Hándicap Europeo 3-way (Winamax)
        result["european_handicap"] = {
            str(h): self.predict_european_handicap(matrix, h)
            for h in [-2, -1, 0, 1, 2]
        }

        # Intervalos de goles (Winamax)
        result["goal_ranges"] = self.predict_all_goal_ranges(matrix)

        # Córners asiáticos (Bet365) — estimación basada en Elo
        total_elo = elo_a + elo_b
        exp_corners = (10.5 * elo_a / total_elo) if total_elo > 0 else 5.25
        elo_diff = elo_a - elo_b
        if abs(elo_diff) > 200:
            exp_corners += 1.0 if elo_diff > 0 else -1.0
        exp_corners = max(1.0, exp_corners)
        result["corners_asian"] = {
            "expected": round(exp_corners, 2),
            "9.5":  self.predict_corners_asian(exp_corners, 9.5),
            "10.5": self.predict_corners_asian(exp_corners, 10.5),
            "11.5": self.predict_corners_asian(exp_corners, 11.5),
        }

        # Tarjetas asiáticas (Bet365) — estimación basada en diferencia Elo
        exp_cards = 3.8 + 0.5 * (abs(elo_diff) / 200.0)
        result["cards_asian"] = {
            "expected": round(exp_cards, 2),
            "3.5": self.predict_cards_asian(exp_cards, 3.5),
            "4.5": self.predict_cards_asian(exp_cards, 4.5),
            "5.5": self.predict_cards_asian(exp_cards, 5.5),
        }

        return result
