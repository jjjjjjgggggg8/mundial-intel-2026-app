import type { Match, Analysis } from '@/lib/data'
import { formatRelativeTime } from '@/lib/utils'
import HorizontalBar from './HorizontalBar'
import EloComparison from './EloComparison'
import ValueBetCard from './ValueBetCard'

type Props = {
  match: Match
  analysis: Analysis
}

export default function AnalysisPanel({ match, analysis }: Props) {
  const { probs, top_scorelines, high_prob_events, value_bets } = analysis
  const topScore = top_scorelines[0]

  return (
    <div className="space-y-6 pt-4">
      {/* ── AI Analysis ── */}
      <div>
        <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-2 flex items-center gap-1">
          <span>✦</span>
          <span>
            Análisis IA — Gemini Flash · Actualizado{' '}
            {formatRelativeTime(analysis.odds_updated_at)}
          </span>
        </p>
        <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 leading-relaxed">
          {analysis.gemini_analysis}
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

      {value_bets.length > 0 && (
        <>
          <Divider />

          {/* ── Value bets ── */}
          <div>
            <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
              Value bets detectados
            </p>
            <div className="space-y-3">
              {value_bets.map(bet => (
                <ValueBetCard key={bet.market} bet={bet} />
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── Footer ── */}
      <p className="text-xs text-gray-400 text-right pt-1">
        Cuotas: {new Date(analysis.odds_updated_at).toLocaleString('es-ES', {
          day: 'numeric',
          month: 'short',
          hour: '2-digit',
          minute: '2-digit',
        })} · Modelo: Elo + Dixon-Coles Poisson v2
      </p>
    </div>
  )
}

function Divider() {
  return <hr className="border-gray-100" />
}
