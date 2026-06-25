import os
import json
import logging
from pathlib import Path
from datetime import date
import truststore
truststore.inject_into_ssl()
from google import genai

logger = logging.getLogger(__name__)

_last_used_fallback = False

USAGE_LOG_PATH = Path("data/logs/gemini_usage.json")

SYSTEM_PROMPT = """
Eres un analista cuantitativo especializado en mercados de apuestas deportivas de fútbol
internacional. Trabajas con datos del modelo matemático Elo + Dixon-Coles Poisson bivariante,
que calcula probabilidades independientes de las casas de apuestas.

TU MISIÓN en cada análisis:
1. Interpretar si la diferencia de Elo entre los equipos justifica las probabilidades del modelo.
   No te limites a listar números: explica qué significa esa diferencia en términos de rendimiento
   real del partido.
2. Evaluar críticamente si las cuotas de Bet365 y Winamax están bien o mal valoradas respecto
   al modelo. Si el EV es positivo, di en qué dirección está el valor y cuánto.
3. Incorporar cualquier información reciente que hayas encontrado (lesiones clave, suspensiones,
   forma reciente, historial cabeza a cabeza) que pueda afectar al resultado.
4. Concluir con una valoración directa sobre si hay o no argumento matemático para apostar
   y en qué mercado concreto.

REGLAS DE FORMATO:
- Exactamente 3 o 4 frases. Ni más, ni menos.
- Texto corrido en español, sin bullets, sin markdown, sin negritas, sin emojis.
- Tono directo y profesional, como un analista que habla a otro analista.
- Nunca uses frases genéricas como "será un partido emocionante" o "ambos equipos lucharán".
- Si no hay value bets (EV < 5%), di explícitamente que el modelo no detecta valor en las cuotas
  actuales y explica por qué (mercado bien valorado, incertidumbre alta, etc.).
- No añadas disclaimers sobre riesgos del juego: eso ya está en la interfaz.
"""


def _build_user_prompt(match_data: dict, model_predictions: dict, odds_data: dict) -> str:
    home = match_data["home_team"]
    away = match_data["away_team"]
    elo_home = model_predictions["elo_home"]
    elo_away = model_predictions["elo_away"]
    elo_adv = model_predictions["elo_advantage"]

    if elo_adv >= 0:
        elo_line = f"{home} tiene ventaja Elo de {elo_adv} puntos ({elo_home} vs {elo_away})."
    else:
        elo_line = f"{away} tiene ventaja Elo de {abs(elo_adv)} puntos ({elo_away} vs {elo_home})."

    prob_home = round(model_predictions["prob_home_win"] * 100, 1)
    prob_draw = round(model_predictions["prob_draw"] * 100, 1)
    prob_away = round(model_predictions["prob_away_win"] * 100, 1)
    prob_over = round(model_predictions["prob_over_2_5"] * 100, 1)
    prob_btts = round(model_predictions["prob_btts"] * 100, 1)
    xg_home = model_predictions["expected_goals_home"]
    xg_away = model_predictions["expected_goals_away"]

    if odds_data.get("has_value") and odds_data.get("value_bets"):
        vb_lines = []
        for vb in odds_data["value_bets"]:
            bookie = vb["best_bookmaker"]
            bookie_key = bookie.lower()
            odds_bet365 = vb.get("odds_bet365", "N/D")
            ev_bet365 = round(vb.get("ev_bet365", 0) * 100, 1)
            odds_winamax = vb.get("odds_winamax", "N/D")
            ev_winamax = round(vb.get("ev_winamax", 0) * 100, 1)
            best_ev = round(vb["best_ev"] * 100, 1)
            model_prob = round(vb["model_prob"] * 100, 1)
            vb_lines.append(
                f"  - Mercado: {vb['market']} | Prob. modelo: {model_prob}% | "
                f"Bet365: {odds_bet365} (EV: +{ev_bet365}%) | "
                f"Winamax: {odds_winamax} (EV: +{ev_winamax}%) | "
                f"Mejor opción: {bookie} con EV +{best_ev}%"
            )
        value_section = "VALUE BETS DETECTADOS:\n" + "\n".join(vb_lines)
    else:
        value_section = "VALUE BETS: Ninguno detectado (EV < 5% en todos los mercados)."

    return f"""PARTIDO: {home} vs {away}
FASE: {match_data["phase"]}
FECHA: {match_data["date"]} a las {match_data["kickoff"]}
SEDE: {match_data["venue"]}

RATINGS ELO:
{home}: {elo_home} | {away}: {elo_away}
{elo_line}

GOLES ESPERADOS (xG del modelo):
{home}: {xg_home} | {away}: {xg_away}

PROBABILIDADES DEL MODELO:
Victoria {home}: {prob_home}% | Empate: {prob_draw}% | Victoria {away}: {prob_away}%
Over 2.5 goles: {prob_over}% | Ambos marcan (BTTS): {prob_btts}%

{value_section}

Usa Google Search para buscar noticias recientes sobre lesiones, suspensiones o forma de ambos \
equipos antes de escribir el análisis. Responde en texto plano, 3-4 frases, sin markdown."""


def _log_request(success: bool) -> None:
    today = str(date.today())
    usage = {}
    if USAGE_LOG_PATH.exists():
        with open(USAGE_LOG_PATH) as f:
            usage = json.load(f)
    if today not in usage:
        usage[today] = {"success": 0, "failed": 0}
    if success:
        usage[today]["success"] += 1
    else:
        usage[today]["failed"] += 1
    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG_PATH, "w") as f:
        json.dump(usage, f, indent=2)
    total_today = usage[today]["success"] + usage[today]["failed"]
    print(f"[Gemini] Peticiones hoy: {total_today}/1500")


def _fallback_analysis(match_data: dict, model_predictions: dict, odds_data: dict) -> str:
    home = match_data["home_team"]
    away = match_data["away_team"]
    elo_adv = model_predictions["elo_advantage"]
    prob_home = round(model_predictions["prob_home_win"] * 100)
    xg_home = model_predictions["expected_goals_home"]
    xg_away = model_predictions["expected_goals_away"]

    if elo_adv > 0:
        stronger = home
        weaker = away
    else:
        stronger = away
        weaker = home
        elo_adv = abs(elo_adv)

    base = (
        f"El modelo asigna {prob_home}% de probabilidad a la victoria de {home}, "
        f"con {stronger} {elo_adv} puntos Elo por encima de {weaker}. "
        f"Los goles esperados son {xg_home} para {home} y {xg_away} para {away}."
    )

    if odds_data.get("has_value") and odds_data.get("value_bets"):
        vb = odds_data["value_bets"][0]
        bookie = vb["best_bookmaker"]
        bookie_odds = vb.get(f"odds_{bookie.lower()}", vb.get("best_ev"))
        best_ev_pct = round(vb["best_ev"] * 100, 1)
        base += (
            f" Se detecta valor en {vb['market']} a {bookie_odds} "
            f"en {bookie} (EV: +{best_ev_pct}%)."
        )
    else:
        base += " El modelo no detecta valor claro en las cuotas actuales del mercado."

    return base


def analyze_match(
    match_data: dict,
    model_predictions: dict,
    odds_data: dict,
    api_key: str,
) -> str:
    user_prompt = _build_user_prompt(match_data, model_predictions, odds_data)

    try:
        client = genai.Client(api_key=api_key)

        interaction = client.interactions.create(
            model="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
            input=user_prompt,
            tools=[{"type": "google_search"}],
        )

        result_text = interaction.output_text
        if not result_text:
            for step in interaction.steps:
                if step.type == "model_output":
                    for block in step.content:
                        if block.type == "text":
                            result_text = block.text
                            break

        if not result_text or len(result_text) < 20:
            raise ValueError(f"Respuesta de Gemini vacía o truncada: {repr(result_text)}")

        _log_request(True)
        return result_text

    except Exception as e:
        logger.warning("Gemini no disponible, usando fallback. Error: %s", e)
        _log_request(False)
        global _last_used_fallback
        _last_used_fallback = True
        return _fallback_analysis(match_data, model_predictions, odds_data)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY no encontrada en entorno ni en .env")
        raise SystemExit(1)

    sample_match = {
        "id": "esp-ger-20260626",
        "home_team": "España",
        "away_team": "Alemania",
        "date": "2026-06-26",
        "kickoff": "21:00",
        "phase": "Grupo E · Jornada 3",
        "venue": "MetLife Stadium",
    }
    sample_predictions = {
        "elo_home": 2012,
        "elo_away": 1976,
        "elo_advantage": 36,
        "prob_home_win": 0.47,
        "prob_draw": 0.27,
        "prob_away_win": 0.26,
        "prob_over_2_5": 0.61,
        "prob_btts": 0.68,
        "expected_goals_home": 1.42,
        "expected_goals_away": 1.18,
    }
    sample_odds = {
        "value_bets": [
            {
                "market": "Over 2.5 goles",
                "model_prob": 0.61,
                "best_ev": 0.189,
                "best_bookmaker": "Winamax",
                "odds_bet365": 1.90,
                "ev_bet365": 0.159,
                "odds_winamax": 1.95,
                "ev_winamax": 0.189,
            }
        ],
        "has_value": True,
    }

    result = analyze_match(sample_match, sample_predictions, sample_odds, api_key)

    print("=== ANÁLISIS GENERADO ===")
    print(result)
    print("=== FIN DEL ANÁLISIS ===")
    if _last_used_fallback:
        print("AVISO: Se usó el análisis de fallback (Gemini no disponible)")
