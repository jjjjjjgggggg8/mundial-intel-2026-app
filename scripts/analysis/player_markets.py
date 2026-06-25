"""scripts/analysis/player_markets.py — Mercados de jugadores (Winamax y Bet365).

Los datos de plantillas vienen de data/raw/worldcup.squads.json.
Como el JSON solo contiene pos/nombre/club/fecha_nac, se usan defaults
estadísticos por posición calibrados sobre Mundiales 2014-2022.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from scipy.stats import poisson as poisson_dist, norm


# ---------------------------------------------------------------------------
# Defaults estadísticos por posición (calibrados en WC 2014-2022)
# ---------------------------------------------------------------------------

_GOALS_PER_GAME: dict[str, float] = {
    "GK": 0.00, "DF": 0.03, "MF": 0.10, "FW": 0.32,
}
_SHOTS_PER_GAME: dict[str, float] = {
    "GK": 0.00, "DF": 0.30, "MF": 0.90, "FW": 2.50,
}
_PASSES_PER_GAME: dict[str, float] = {
    "GK": 35.0, "DF": 55.0, "MF": 65.0, "FW": 30.0,
}
_TACKLES_PER_GAME: dict[str, float] = {
    "GK": 0.00, "DF": 2.80, "MF": 1.80, "FW": 0.40,
}
_FOULS_COMMITTED: dict[str, float] = {
    "GK": 0.20, "DF": 1.00, "MF": 1.20, "FW": 0.80,
}
_FOULS_WON: dict[str, float] = {
    "GK": 0.10, "DF": 0.50, "MF": 0.90, "FW": 1.50,
}
_HEADER_PCT: dict[str, float] = {
    "GK": 0.00, "DF": 0.25, "MF": 0.10, "FW": 0.15,
}
_POS_GOAL_ADJ: dict[str, float] = {
    "GK": 0.00, "DF": 0.70, "MF": 0.85, "FW": 1.00,
}

_POSSESSION_TEAMS = {
    "spain", "germany", "netherlands", "brazil", "portugal",
    "france", "belgium", "argentina", "italy", "japan",
    "united states", "usa", "england",
}

# Distribución temporal de goles en Mundiales 2010-2022
_FIRST_HALF_PCT  = 0.44
_SECOND_HALF_PCT = 0.56

# Distribución de método de gol en Mundiales 2010-2022
_METHOD_OPEN_PLAY   = 0.72
_METHOD_HEADER      = 0.12
_METHOD_FREE_KICK   = 0.06
_METHOD_PENALTY     = 0.10


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class PlayerMarketAnalyzer:
    """Calcula probabilidades de mercados de jugadores para Winamax y Bet365."""

    def __init__(self, squads_path: str):
        self.squads_path = squads_path
        self.squads: dict[str, list[dict]] = self._load_squads()

    def _load_squads(self) -> dict[str, list[dict]]:
        """
        Lee worldcup.squads.json y construye {team_name: [jugadores]}.
        El JSON real es una lista de equipos con campo 'players'.
        """
        path = Path(self.squads_path)
        if not path.exists():
            raise FileNotFoundError(
                f"JSON de plantillas no encontrado: {self.squads_path}. "
                "Asegúrate de que data/raw/worldcup.squads.json existe."
            )
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)

        result: dict[str, list[dict]] = {}
        # Formato: lista de equipos con campo 'name' y 'players'
        if isinstance(raw, list):
            for team_entry in raw:
                team_name = team_entry.get("name", "")
                players   = team_entry.get("players", [])
                if team_name:
                    result[team_name] = players
        elif isinstance(raw, dict):
            # Formato alternativo: {team_name: [players]}
            result = {k: v for k, v in raw.items() if isinstance(v, list)}
        return result

    def get_team_players(self, team: str) -> list[dict]:
        """Retorna la lista de jugadores de un equipo (normaliza el nombre)."""
        # Búsqueda exacta primero
        if team in self.squads:
            return self.squads[team]
        # Búsqueda insensible a mayúsculas
        team_lo = team.lower()
        for k, v in self.squads.items():
            if k.lower() == team_lo:
                return v
        return []

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _get_pos(self, player: dict) -> str:
        """Normaliza la clave de posición ('pos' o 'position')."""
        pos = player.get("pos", player.get("position", "MF")).upper()
        return pos if pos in ("GK", "DF", "MF", "FW") else "MF"

    def _get_goals_per_game(self, player: dict) -> float:
        """Goles por partido: usa stats del jugador si existen, o default por posición."""
        pos = self._get_pos(player)
        explicit = player.get("goals_per_game")
        if explicit is not None:
            return float(explicit)
        club_goals = player.get("club_goals_2425", 0)
        minutes    = player.get("minutes_2425", 0)
        if minutes > 0:
            return club_goals / (minutes / 90.0)
        return _GOALS_PER_GAME.get(pos, 0.1)

    def _lambda_player(self, player: dict, team_expected_goals: float,
                       all_players: list[dict]) -> float:
        """
        Calcula los goles esperados del jugador en el partido.
        Usa distribución proporcional de goles del equipo entre los jugadores.
        """
        pos = self._get_pos(player)
        if pos == "GK":
            return 0.0

        gpg = self._get_goals_per_game(player)
        team_total_gpg = sum(
            self._get_goals_per_game(p) for p in all_players
            if self._get_pos(p) != "GK"
        )
        if team_total_gpg <= 0:
            share = 1.0 / max(len(all_players) - 1, 10)
        else:
            share = gpg / team_total_gpg

        lam = share * team_expected_goals * _POS_GOAL_ADJ.get(pos, 0.85)
        return max(lam, 0.0)

    # ------------------------------------------------------------------
    # Mercados de goleador (Winamax)
    # ------------------------------------------------------------------

    def predict_anytime_scorer(self, player: dict, team_expected_goals: float,
                                all_players: list[dict]) -> dict:
        """
        Probabilidad de que el jugador marque al menos 1 gol (Winamax — Goleador).
        """
        lam = self._lambda_player(player, team_expected_goals, all_players)
        pos = self._get_pos(player)

        prob_score    = float(1.0 - math.exp(-lam)) if lam > 0 else 0.0
        prob_brace    = float(1.0 - poisson_dist.cdf(1, lam)) if lam > 0 else 0.0
        prob_hat_trick = float(1.0 - poisson_dist.cdf(2, lam)) if lam > 0 else 0.0

        return {
            "player":               player.get("name", ""),
            "position":             pos,
            "lambda_goals":         round(lam, 4),
            "prob_anytime_scorer":  round(prob_score, 4),
            "prob_brace":           round(prob_brace, 4),
            "prob_hat_trick":       round(prob_hat_trick, 4),
            "market_type":          "anytime_scorer",
        }

    def predict_scorer_method(self, player: dict, lambda_goals: float) -> dict:
        """Mercado Winamax: método del primer gol (cabeza, falta, penalti, juego abierto)."""
        pos = self._get_pos(player)
        if pos == "GK" or lambda_goals <= 0:
            return {}

        header_pct  = player.get("header_goals_pct", _HEADER_PCT.get(pos, 0.12))
        # Redistribuir proporcionalmente manteniendo suma = 1
        remaining   = 1.0 - header_pct
        fk_pct      = _METHOD_FREE_KICK * remaining / (1.0 - _METHOD_HEADER)
        pen_pct     = _METHOD_PENALTY   * remaining / (1.0 - _METHOD_HEADER)
        open_pct    = 1.0 - header_pct - fk_pct - pen_pct

        prob_score = float(1.0 - math.exp(-lambda_goals))
        methods = {
            "open_play":  round(prob_score * open_pct, 4),
            "header":     round(prob_score * header_pct, 4),
            "free_kick":  round(prob_score * fk_pct, 4),
            "penalty":    round(prob_score * pen_pct, 4),
        }
        most_likely = max(methods, key=lambda k: methods[k])

        return {
            "prob_goal_open_play":  methods["open_play"],
            "prob_goal_header":     methods["header"],
            "prob_goal_free_kick":  methods["free_kick"],
            "prob_goal_penalty":    methods["penalty"],
            "most_likely_method":   most_likely,
        }

    def predict_first_half_scorer(self, lambda_goals: float) -> dict:
        """Mercado Winamax: goleador en primera o segunda parte."""
        lam_1h = lambda_goals * _FIRST_HALF_PCT
        lam_2h = lambda_goals * _SECOND_HALF_PCT
        return {
            "prob_score_first_half":  round(float(1.0 - math.exp(-lam_1h)), 4),
            "prob_score_second_half": round(float(1.0 - math.exp(-lam_2h)), 4),
            "lambda_first_half":      round(lam_1h, 4),
            "lambda_second_half":     round(lam_2h, 4),
        }

    def predict_scorer_plus_result(self, player: dict, team_expected_goals: float,
                                    all_players: list[dict],
                                    match_probs: dict,
                                    team_is_home: bool) -> dict:
        """
        Combinada correlacionada: jugador marca Y equipo gana/empata/pierde.
        P(jugador marca AND equipo gana) ≈ P(jugador marca|equipo gana) × P(equipo gana)
        """
        lam  = self._lambda_player(player, team_expected_goals, all_players)
        prob_score = float(1.0 - math.exp(-lam)) if lam > 0 else 0.0

        # Factor de correlación positiva (marcar → más probable ganar)
        corr = 1.0 + 0.15 * (lam / max(team_expected_goals, 0.1))

        prob_win  = match_probs.get("prob_home_win" if team_is_home else "prob_away_win", 0.3)
        prob_draw = match_probs.get("prob_draw", 0.25)
        prob_lose = 1.0 - prob_win - prob_draw

        return {
            "prob_scorer_and_team_wins":  round(prob_score * corr * prob_win, 4),
            "prob_scorer_and_draw":       round(prob_score * prob_draw, 4),
            "prob_scorer_and_team_loses": round(prob_score * max(prob_lose, 0.0), 4),
            "correlation_factor":         round(corr, 4),
            "note": "Correlación positiva entre goleador y victoria del equipo",
        }

    # ------------------------------------------------------------------
    # Mercados de estadísticas físicas (Bet365)
    # ------------------------------------------------------------------

    def predict_shots(self, player: dict, elo_diff: float) -> dict:
        """
        Tiros a puerta / tiros totales (Bet365).
        elo_diff = elo_local - elo_visitante (desde perspectiva del jugador).
        """
        pos = self._get_pos(player)
        base_shots = player.get("shots_per_game", _SHOTS_PER_GAME.get(pos, 0.9))

        if elo_diff > 100:
            shots_adj = base_shots * 1.10
        elif elo_diff < -100:
            shots_adj = base_shots * 0.90
        else:
            shots_adj = base_shots

        sot_adj = shots_adj * 0.38  # ratio histórico tiros a puerta en WC

        lines = {}
        for line in [0.5, 1.5, 2.5]:
            lf = math.floor(line)
            p_over  = float(1.0 - poisson_dist.cdf(lf, shots_adj))
            p_under = float(poisson_dist.cdf(lf, shots_adj))
            lines[str(line)] = {"prob_over": round(p_over, 4), "prob_under": round(p_under, 4)}

        # Línea recomendada: la más cercana a 50/50
        rec = min(lines, key=lambda k: abs(lines[k]["prob_over"] - 0.5))

        return {
            "player":                  player.get("name", ""),
            "expected_shots_total":    round(shots_adj, 3),
            "expected_shots_on_target": round(sot_adj, 3),
            "lines":                   lines,
            "recommended_line":        rec,
            "market_type":             "shots",
        }

    def predict_passes(self, player: dict, team_name: str,
                       rival_name: str) -> dict:
        """Pases completados (Bet365) — especialmente relevante para MF y DF."""
        pos  = self._get_pos(player)
        base = player.get("passes_completed_per_game", _PASSES_PER_GAME.get(pos, 50.0))

        # Ajuste por estilo de posesión
        if team_name.lower() in _POSSESSION_TEAMS:
            base *= 1.10
        if rival_name.lower() in _POSSESSION_TEAMS:
            base *= 1.05

        # Ajuste por posición
        pos_adj = {"GK": 0.50, "DF": 1.00, "MF": 1.00, "FW": 0.70}
        passes_adj = base * pos_adj.get(pos, 1.0)

        std = passes_adj * 0.20
        all_lines = [25.5, 30.5, 40.5, 50.5, 65.5, 80.5]

        lines: dict = {}
        for line in all_lines:
            p_over  = float(1.0 - norm.cdf(line, loc=passes_adj, scale=std))
            p_under = float(norm.cdf(line, loc=passes_adj, scale=std))
            lines[str(line)] = {"prob_over": round(p_over, 4), "prob_under": round(p_under, 4)}

        # Líneas relevantes según posición
        rel_by_pos = {
            "GK": ["25.5", "30.5"],
            "DF": ["40.5", "50.5", "65.5"],
            "MF": ["50.5", "65.5", "80.5"],
            "FW": ["25.5", "30.5", "40.5"],
        }
        relevant = rel_by_pos.get(pos, ["40.5", "50.5"])

        return {
            "player":          player.get("name", ""),
            "expected_passes": round(passes_adj, 1),
            "lines":           lines,
            "relevant_lines":  relevant,
            "market_type":     "passes_completed",
        }

    def predict_tackles(self, player: dict, elo_diff: float) -> dict | None:
        """Entradas/tackles (Bet365). Solo para DF y MF; retorna None para FW/GK."""
        pos = self._get_pos(player)
        if pos in ("GK", "FW"):
            return None

        base = player.get("tackles_per_game", _TACKLES_PER_GAME.get(pos, 1.8))
        if elo_diff < -100:
            tackles_adj = base * 1.15   # defienden más si rival es favorito
        elif elo_diff > 100:
            tackles_adj = base * 0.90
        else:
            tackles_adj = base

        lines: dict = {}
        for line in [0.5, 1.5, 2.5]:
            lf = math.floor(line)
            lines[str(line)] = {
                "prob_over":  round(float(1.0 - poisson_dist.cdf(lf, tackles_adj)), 4),
                "prob_under": round(float(poisson_dist.cdf(lf, tackles_adj)), 4),
            }

        rec = min(lines, key=lambda k: abs(lines[k]["prob_over"] - 0.5))
        return {
            "player":           player.get("name", ""),
            "expected_tackles": round(tackles_adj, 3),
            "lines":            lines,
            "recommended_line": rec,
            "market_type":      "tackles",
        }

    def predict_fouls(self, player: dict, elo_diff: float) -> dict:
        """Faltas cometidas y recibidas (Bet365)."""
        pos = self._get_pos(player)
        base_committed = player.get("fouls_committed_per_game", _FOULS_COMMITTED.get(pos, 1.0))
        base_won       = player.get("fouls_won_per_game",       _FOULS_WON.get(pos, 0.9))

        if pos in ("DF", "MF") and elo_diff < -100:
            base_committed *= 1.10
        if pos == "FW":
            base_won *= 1.05

        def _lines(lam: float) -> dict:
            out: dict = {}
            for line in [0.5, 1.5, 2.5]:
                lf = math.floor(line)
                out[str(line)] = {
                    "prob_over":  round(float(1.0 - poisson_dist.cdf(lf, lam)), 4),
                    "prob_under": round(float(poisson_dist.cdf(lf, lam)), 4),
                }
            return out

        return {
            "fouls_committed": {
                "expected": round(base_committed, 3),
                "lines":    _lines(base_committed),
            },
            "fouls_won": {
                "expected": round(base_won, 3),
                "lines":    _lines(base_won),
            },
        }

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def analyze_match_players(self, home_team: str, away_team: str,
                               match_predictions: dict) -> dict:
        """
        Analiza todos los jugadores relevantes de ambos equipos para todos los mercados.
        match_predictions: output de DixonColesModel.get_all_markets().
        """
        exp_home = match_predictions.get("expected_goals_home", 1.2)
        exp_away = match_predictions.get("expected_goals_away", 1.0)
        match_probs = {k: match_predictions[k]
                       for k in ("prob_home_win", "prob_draw", "prob_away_win")
                       if k in match_predictions}

        elo_diff_home = 0.0  # positivo = home favorito

        def _analyze_squad(team: str, exp_goals: float,
                           is_home: bool) -> list[dict]:
            players = self.get_team_players(team)
            if not players:
                return []

            sign = 1.0 if is_home else -1.0
            elo_diff_for_team = sign * elo_diff_home

            # Selección de jugadores a analizar:
            # Todos los FW + top MF por passes + top DF por passes
            fw  = [p for p in players if self._get_pos(p) == "FW"]
            mf  = sorted(
                [p for p in players if self._get_pos(p) == "MF"],
                key=lambda p: p.get("passes_completed_per_game",
                                     _PASSES_PER_GAME["MF"]),
                reverse=True,
            )[:4]
            df  = sorted(
                [p for p in players if self._get_pos(p) == "DF"],
                key=lambda p: p.get("passes_completed_per_game",
                                     _PASSES_PER_GAME["DF"]),
                reverse=True,
            )[:3]

            analyzed: list[dict] = []
            for player in (fw + mf + df):
                pos = self._get_pos(player)
                all_non_gk = [p for p in players if self._get_pos(p) != "GK"]
                scorer_info = self.predict_anytime_scorer(player, exp_goals, all_non_gk)
                lam = scorer_info["lambda_goals"]

                markets: dict = {
                    "anytime_scorer": scorer_info,
                    "scorer_method":  self.predict_scorer_method(player, lam),
                    "first_half_scorer": self.predict_first_half_scorer(lam),
                    "scorer_and_team_wins": self.predict_scorer_plus_result(
                        player, exp_goals, all_non_gk, match_probs, is_home
                    ),
                    "shots":   self.predict_shots(player, elo_diff_for_team),
                    "passes":  self.predict_passes(player, team, away_team if is_home else home_team),
                    "tackles": self.predict_tackles(player, elo_diff_for_team),
                    "fouls":   self.predict_fouls(player, elo_diff_for_team),
                }
                analyzed.append({
                    "name":     player.get("name", ""),
                    "position": pos,
                    "club":     player.get("club", {}).get("name", "") if isinstance(
                                    player.get("club"), dict) else player.get("club", ""),
                    "markets":  markets,
                })

            return analyzed

        home_players = _analyze_squad(home_team, exp_home, is_home=True)
        away_players = _analyze_squad(away_team, exp_away, is_home=False)

        # Top 3 por prob_anytime_scorer
        def _top_picks(analyzed: list[dict]) -> list[dict]:
            scored = [
                {
                    "name":     p["name"],
                    "position": p["position"],
                    "prob_anytime_scorer": p["markets"]["anytime_scorer"].get("prob_anytime_scorer", 0),
                    "lambda_goals": p["markets"]["anytime_scorer"].get("lambda_goals", 0),
                }
                for p in analyzed
                if p["markets"]["anytime_scorer"].get("prob_anytime_scorer", 0) > 0
            ]
            return sorted(scored, key=lambda x: x["prob_anytime_scorer"], reverse=True)[:3]

        return {
            "home_team":       home_team,
            "away_team":       away_team,
            "home_players":    home_players,
            "away_players":    away_players,
            "top_home_picks":  _top_picks(home_players),
            "top_away_picks":  _top_picks(away_players),
        }
