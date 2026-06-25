# Mundial Intel 2026

Herramienta de análisis matemático para el Mundial de Fútbol 2026.
Calcula probabilidades con el modelo Elo + Dixon-Coles Poisson, 
detecta value bets comparando con cuotas reales de Bet365 y Winamax,
y genera análisis narrativo con Gemini Flash + Google Search Grounding.

**Stack:** Python 3.11 · Next.js 14 · GitHub Actions · Vercel

---

## Cómo funciona la automatización

El repo es público. GitHub Actions en repos públicos es **gratuito e 
ilimitado** (sin restricción de minutos). El pipeline corre 
automáticamente dos veces al día:

| Ejecución | UTC   | Hora Madrid (verano) |
|-----------|-------|----------------------|
| Mañana    | 07:00 | 09:00                |
| Tarde     | 15:00 | 17:00                |

Cada ejecución:
1. Ejecuta `scripts/main.py`
2. El script calcula predicciones, fetchea cuotas, detecta value bets
   y genera análisis con Gemini
3. Si todo va bien (exit code 0): hace commit automático de los JSON
   actualizados en `web/public/data/`
4. Vercel detecta el nuevo commit y redespliega la web en ~30 segundos
5. Si hay error (exit code 1): no hace commit y el workflow falla 
   visiblemente en la pestaña Actions (para que lo veas)

---

## Configuración inicial: añadir las API keys como GitHub Secrets

El script necesita dos claves de API que **nunca deben subirse al repo**.
Se configuran como Secrets en GitHub y el workflow las inyecta como
variables de entorno en cada ejecución.

### Paso a paso:

1. Ve a tu repositorio en github.com
2. Haz clic en **Settings** (pestaña superior del repo, no de tu cuenta)
3. En el menú lateral izquierdo, busca **Secrets and variables** 
   y haz clic en **Actions**
4. Haz clic en el botón verde **New repository secret**
5. Añade el primer secret:
   - **Name:** `GEMINI_API_KEY`
   - **Secret:** tu clave de Google AI Studio (aistudio.google.com)
   - Haz clic en **Add secret**
6. Repite el proceso para el segundo secret:
   - **Name:** `ODDS_API_KEY`
   - **Secret:** tu clave de The Odds API (the-odds-api.com)
   - Haz clic en **Add secret**

✅ Listo. El GITHUB_TOKEN (necesario para que el bot pueda hacer push)
lo gestiona GitHub automáticamente, no tienes que añadirlo.

---

## Cómo forzar una ejecución manual

Útil para probar que todo funciona o para actualizar los datos 
antes de un partido importante sin esperar al horario automático.

1. Ve a tu repositorio en github.com
2. Haz clic en la pestaña **Actions**
3. En el panel izquierdo verás el workflow **"Update Data"**,
   haz clic sobre él
4. Haz clic en el botón **"Run workflow"** (lado derecho)
5. Deja la rama como `main` y haz clic en el botón verde **"Run workflow"**
6. Aparecerá una nueva ejecución en la lista. Haz clic sobre ella
   para ver los logs en tiempo real.

Si el workflow termina con ✅ verde: los JSON se han actualizado y
Vercel habrá redesplegado la web en unos segundos.
Si termina con ❌ rojo: revisa los logs del step que falló.

---

## Variables de entorno requeridas

| Variable        | Fuente              | Descripción                         |
|-----------------|---------------------|-------------------------------------|
| `GEMINI_API_KEY`| GitHub Secret       | Google AI Studio — Gemini Flash     |
| `ODDS_API_KEY`  | GitHub Secret       | The Odds API — cuotas en tiempo real|
| `GITHUB_TOKEN`  | Automático (GitHub) | Para el commit automático del bot   |

Para desarrollo local, crea un archivo `.env` en la raíz del proyecto
(ya está en `.gitignore`, no se subirá nunca al repo):

```
GEMINI_API_KEY=tu_clave_aqui
ODDS_API_KEY=tu_clave_aqui
```

---

## Estructura del proyecto

```
mundial-intel-2026/
├── .github/workflows/
│   └── update-data.yml      ← automatización GitHub Actions
├── scripts/
│   ├── models/              ← Elo + Dixon-Coles Poisson
│   ├── ingestion/           ← datos históricos + cuotas API
│   ├── analysis/            ← llamadas a Gemini
│   └── main.py              ← orquestador (GitHub Actions lo ejecuta)
├── web/                     ← Next.js 14 (App Router)
├── web/public/data/         ← JSON generados (leídos por la web)
├── data/raw/                ← CSVs históricos (no se tocan)
└── requirements.txt
```

---

## Advertencia legal

Esta herramienta es exclusivamente para análisis e información personal.
No garantiza resultados en apuestas deportivas. Las apuestas implican
riesgo de pérdida económica. Juega con responsabilidad.
