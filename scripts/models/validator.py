from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as __main__ from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.models.elo import EloModel
from scripts.models.normalizer import normalize_team_name
from scripts.models.poisson import DixonColesModel

_WC_EVAL_YEARS = {2010, 2014, 2018, 2022}
_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "results.csv"


class ModelValidator:

    def backtest(self, matches_df: pd.DataFrame,
                 elo_model: EloModel,
                 dc_model: DixonColesModel) -> dict:

        df = matches_df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["home_score", "away_score"])
        df = df[df["home_score"].astype(str) != "NA"]
        df = df[df["away_score"].astype(str) != "NA"]
        df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
        df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
        df = df.dropna(subset=["home_score", "away_score"])
        df["home_score"] = df["home_score"].astype(int)
        df["away_score"] = df["away_score"].astype(int)

        wc_eval = df[
            (df["tournament"] == "FIFA World Cup") &
            (df["date"].dt.year.isin(_WC_EVAL_YEARS))
        ].sort_values("date").reset_index(drop=True)

        predictions: list[tuple[float, float, float, int]] = []  # (p_h, p_d, p_a, outcome 0/1/2)

        for _, row in wc_eval.iterrows():
            home = normalize_team_name(str(row["home_team"]))
            away = normalize_team_name(str(row["away_team"]))
            match_date = row["date"]
            neutral_flag = str(row.get("neutral", "TRUE")).upper() not in ("FALSE", "0", "F")

            elo_a = elo_model.get_rating(home, date=match_date)
            elo_b = elo_model.get_rating(away, date=match_date)

            preds = dc_model.predict_match(home, away, elo_a, elo_b,
                                           neutral=neutral_flag)
            p_h = preds["prob_home_win"]
            p_d = preds["prob_draw"]
            p_a = preds["prob_away_win"]

            if row["home_score"] > row["away_score"]:
                outcome = 0   # home win
            elif row["home_score"] == row["away_score"]:
                outcome = 1   # draw
            else:
                outcome = 2   # away win

            predictions.append((p_h, p_d, p_a, outcome))

        n = len(predictions)
        if n == 0:
            print("Sin partidos para evaluar.")
            return {}

        # ── Brier Score ──────────────────────────────────────────────── #
        brier_total = 0.0
        for p_h, p_d, p_a, outcome in predictions:
            i_h = 1 if outcome == 0 else 0
            i_d = 1 if outcome == 1 else 0
            i_a = 1 if outcome == 2 else 0
            brier_total += (p_h - i_h) ** 2 + (p_d - i_d) ** 2 + (p_a - i_a) ** 2
        brier_score = brier_total / n

        # ── Log Loss ─────────────────────────────────────────────────── #
        eps = 1e-3
        ll_total = 0.0
        for p_h, p_d, p_a, outcome in predictions:
            p_h = max(eps, min(1 - eps, p_h))
            p_d = max(eps, min(1 - eps, p_d))
            p_a = max(eps, min(1 - eps, p_a))
            if outcome == 0:
                ll_total += math.log(p_h)
            elif outcome == 1:
                ll_total += math.log(p_d)
            else:
                ll_total += math.log(p_a)
        log_loss = -ll_total / n

        # ── Accuracy ─────────────────────────────────────────────────── #
        correct = sum(
            1 for p_h, p_d, p_a, outcome in predictions
            if [p_h, p_d, p_a].index(max(p_h, p_d, p_a)) == outcome
        )
        accuracy = correct / n * 100.0

        # ── Calibration by decile ─────────────────────────────────────── #
        home_probs = [(p_h, 1 if outcome == 0 else 0)
                      for p_h, _, _, outcome in predictions]
        home_probs.sort(key=lambda x: x[0])
        decile_size = max(1, n // 10)
        decile_rows = []
        for i in range(10):
            chunk = home_probs[i * decile_size: (i + 1) * decile_size]
            if not chunk:
                continue
            pred_mean = sum(p for p, _ in chunk) / len(chunk)
            real_rate = sum(r for _, r in chunk) / len(chunk)
            decile_rows.append((i * 10, (i + 1) * 10, pred_mean, real_rate, len(chunk)))

        # ── ROI simulation ────────────────────────────────────────────── #
        n_h = sum(1 for _, _, _, o in predictions if o == 0)
        n_d = sum(1 for _, _, _, o in predictions if o == 1)
        n_a = sum(1 for _, _, _, o in predictions if o == 2)
        freq_h = n_h / n
        freq_d = n_d / n
        freq_a = n_a / n

        overround = 1.08
        odd_h_mkt = (1.0 / max(freq_h, 1e-6)) * overround
        odd_d_mkt = (1.0 / max(freq_d, 1e-6)) * overround
        odd_a_mkt = (1.0 / max(freq_a, 1e-6)) * overround

        bets_placed = 0
        bets_won = 0
        profit = 0.0

        for p_h, p_d, p_a, outcome in predictions:
            ev_h = p_h * odd_h_mkt - 1.0
            ev_d = p_d * odd_d_mkt - 1.0
            ev_a = p_a * odd_a_mkt - 1.0

            if ev_h > 0.05:
                bets_placed += 1
                if outcome == 0:
                    profit += odd_h_mkt - 1.0
                    bets_won += 1
                else:
                    profit -= 1.0

            if ev_d > 0.05:
                bets_placed += 1
                if outcome == 1:
                    profit += odd_d_mkt - 1.0
                    bets_won += 1
                else:
                    profit -= 1.0

            if ev_a > 0.05:
                bets_placed += 1
                if outcome == 2:
                    profit += odd_a_mkt - 1.0
                    bets_won += 1
                else:
                    profit -= 1.0

        roi = (profit / bets_placed * 100.0) if bets_placed > 0 else 0.0

        # ── Print report ─────────────────────────────────────────────── #
        sep = "=" * 47
        print(sep)
        print("BACKTESTING - MUNDIALES 2010/2014/2018/2022")
        print(sep)
        print(f"Partidos evaluados: {n}")
        print()
        print("CALIBRACION DEL MODELO")
        print(f"Brier Score:  {brier_score:.3f}  (aleatorio=0.667, objetivo<0.55)")
        print(f"Log Loss:     {log_loss:.3f}")
        print(f"Accuracy 1X2: {accuracy:.1f}%")
        print()
        print("CALIBRACION POR DECILES (prob_local predicha vs real)")
        print(f"{'Decil':<9} {'Pred':>6} {'Real':>6} {'N':>4}")
        for lo, hi, pred, real, cnt in decile_rows:
            print(f"{lo:>2}-{hi:>3}%   {pred:.2f}   {real:.2f}   {cnt:>3}")
        print()
        print("SIMULACION ROI (EV > 5%)")
        print(f"Apuestas realizadas: {bets_placed}")
        if bets_placed:
            print(f"Apuestas ganadas:    {bets_won} ({bets_won / bets_placed * 100:.1f}%)")
        print(f"ROI simulado:       {roi:+.1f}%")
        print(f"El modelo habria tenido un ROI de {roi:.1f}% en {bets_placed} apuestas")
        print(sep)

        return {
            "n": n,
            "brier_score": brier_score,
            "log_loss": log_loss,
            "accuracy": accuracy,
            "roi": roi,
            "bets_placed": bets_placed,
        }


def main():
    if not _DATA_PATH.exists():
        print(f"ERROR: No se encontró {_DATA_PATH}")
        sys.exit(1)

    print("Cargando datos...")
    df = pd.read_csv(_DATA_PATH)

    print("Entrenando EloModel...")
    elo = EloModel()
    elo.fit(df)

    print("Calibrando DixonColesModel (puede tardar unos minutos)...")
    dc = DixonColesModel()
    dc.fit(df)

    validator = ModelValidator()
    validator.backtest(df, elo, dc)


if __name__ == "__main__":
    main()
