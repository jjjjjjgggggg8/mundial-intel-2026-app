import type { Match, Analysis, SmartPick } from '@/lib/data'
import { formatRelativeTime } from '@/lib/utils'
import HorizontalBar from './HorizontalBar'
import EloComparison from './EloComparison'

type Props = {
  match: Match
  analysis: Analysis
}

export default function AnalysisPanel({ match, analysis }: Props) {
  const { probs, top_scorelines, high_prob_events } = analysis
  const topScore = top_scorelines[0]
  const smart_picks = analysis.smart_picks ?? []

  const updatedAt = analysis.odds_updated_at
    ? new Date(analysis.odds_updated_at).toLocaleString('es-ES', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : '—'

  return (
    <div className="space-y-6 pt-4">
      {/* ── AI Analysis ── */}
      <div>
        <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-2 flex items-center gap-1">
          <span>✦</span>
          <span>
            Análisis IA — Gemini Flash · Actualizado{' '}
            {analysis.odds_updated_at ? formatRelativeTime(analysis.odds_updated_at) : '—'}
          </span>
        </p>
        <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 leading-relaxed">
          {analysis.gemini_analysis ?? 'Análisis no disponible.'}
        </div>
      </div>

      <Divider />

      {/* ── Elo ── */}
      <EloComparison
        eloHome={analysis.elo_home}
        eloAway={analysis.elo_away}
        eloAdvantage={analysis.elo_advantage}
        homeTeam={match.home_team}
        awayTeam={match.away_team}
      />

      <Divider />

      {/* ── Probabilities ── */}
      <div>
        <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
          Probabilidades del modelo
        </p>
        <div className="space-y-2">
          <HorizontalBar
            label={`Victoria ${match.home_team}`}
            value={probs.home_win}
            displayValue={`${Math.round(probs.home_win * 100)}%`}
            color="blue"
          />
          <HorizontalBar
            label="Empate"
            value={probs.draw}
            displayValue={`${Math.round(probs.draw * 100)}%`}
            color="gray"
          />
          <HorizontalBar
            label={`Victoria ${match.away_team}`}
            value={probs.away_win}
            displayValue={`${Math.round(probs.away_win * 100)}%`}
            color="red"
          />
        </div>

        <div className="space-y-2 mt-4">
          <HorizontalBar
            label="Over 2.5 goles"
            value={probs.over_2_5}
            displayValue={`${Math.round(probs.over_2_5 * 100)}%`}
            color="green"
          />
          <HorizontalBar
            label="Ambos marcan"
            value={probs.btts}
            displayValue={`${Math.round(probs.btts * 100)}%`}
            color="indigo"
          />
          {topScore && (
            <HorizontalBar
              label="Marcador más prob."
              value={topScore.prob}
              displayValue={`${topScore.score} (${Math.round(topScore.prob * 100)}%)`}
              color="yellow"
            />
          )}
        </div>
      </div>

      <Divider />

      {/* ── High probability events ── */}
      <div>
        <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-1">
          Eventos de alta probabilidad
        </p>
        <div>
          {high_prob_events.map(ev => (
            <div
              key={ev.event}
              className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0"
            >
              <div className="flex items-center gap-2">
                <span className="text-green-500 text-sm">✓</span>
                <span className="text-sm text-gray-700">{ev.event}</span>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700 ml-4 shrink-0">
                {Math.round(ev.prob * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Smart Picks ── */}
      {smart_picks.length > 0 && (
        <>
          <Divider />
          <div>
            <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
              Top picks del partido
            </p>
            <div className="space-y-3">
              {smart_picks.map((pick) => (
                <SmartPickCard
                  key={pick.market_key}
                  pick={pick}
                />
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── Footer ── */}
      <p className="text-xs text-gray-400 text-right pt-1">
        Cuotas: {updatedAt} · Modelo: Elo + Dixon-Coles Poisson v2
      </p>
    </div>
  )
}

function SmartPickCard({ pick }: { pick: SmartPick }) {
  const probPct = Math.round(pick.model_prob * 100)
  const bestOdds =
    pick.best_bookmaker === 'bet365' ? pick.odds_bet365
    : pick.best_bookmaker === 'winamax' ? pick.odds_winamax
    : null

  return (
    <div className="rounded-lg border border-gray-100 bg-white p-4 space-y-2.5 shadow-sm">
      {/* Header: label + EV badge */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-gray-800 leading-tight">{pick.label}</p>
        {pick.has_ev && (
          <span className="shrink-0 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-green-100 text-green-700">
            Value ✓
          </span>
        )}
      </div>

      {/* Probability bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
          <div
            className="h-1.5 rounded-full bg-blue-500 transition-all"
            style={{ width: `${probPct}%` }}
          />
        </div>
        <span className="text-xs font-bold text-gray-700 shrink-0 w-10 text-right">
          {probPct}%
        </span>
      </div>

      {/* Reasoning */}
      <p className="text-[11px] text-gray-500 leading-relaxed">{pick.reasoning}</p>

      {/* EV info */}
      {pick.has_ev && pick.best_ev !== null && (
        <p className="text-[11px] font-semibold text-green-600">
          EV: +{Math.round(pick.best_ev * 100)}%
          {pick.best_bookmaker ? ` · ${pick.best_bookmaker}` : ''}
          {bestOdds ? ` @ ${bestOdds}` : ''}
        </p>
      )}

      {/* Navigation paths */}
      <div className="space-y-1 pt-0.5">
        <p className="text-[10px] text-gray-400 leading-tight truncate">
          <span className="font-medium text-gray-500">W</span> {pick.where_to_bet_winamax}
        </p>
        <p className="text-[10px] text-gray-400 leading-tight truncate">
          <span className="font-medium text-gray-500">B</span> {pick.where_to_bet_bet365}
        </p>
      </div>
    </div>
  )
}

function Divider() {
  return <hr className="border-gray-100" />
}
