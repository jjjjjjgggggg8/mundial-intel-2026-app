# Umbral mínimo de Expected Value para considerar una apuesta con valor
EV_THRESHOLD = 0.02          # 2% — bajado desde 5% para capturar más señales

# Máximo de goles por equipo a considerar en la distribución Poisson
MAX_GOALS = 10

# Ventana temporal para fetching de cuotas (horas antes del partido)
ODDS_FETCH_WINDOW_HOURS = 48

# Bookmakers prioritarios
BOOKMAKERS = ["bet365", "winamax"]

# Ruta al JSON de plantillas
SQUADS_PATH = "data/raw/worldcup.squads.json"

# EV mínimo para mercados de jugadores (más ruidosos, umbral más alto)
PLAYER_MARKET_EV_THRESHOLD = 0.04   # 4%
