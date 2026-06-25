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

  const asianHcLines = analysis.asian_handicap
    ? Object.entries(analysis.asian_handicap)
        .map(([line, d]) => ({ line: parseFloat(line), ...d }))
        .sort((a, b) => a.line - b.line)
    : []

  const asianTotalLines = analysis.asian_total
    ? Object.entries(analysis.asian_total)
        .map(([line, d]) => ({ line: parseFloat(line), ...d }))
        .sort((a, b) => a.line - b.line)
    : []

  const goalRanges = analysis.goal_ranges ?? []

  const topHome = analysis.top_scorers?.home ?? []
  const topAway = analysis.top_scorers?.away ?? []
  const hasTopScorers = topHome.length > 0 || topAway.length > 0

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

      {/* ── Asian Markets ── */}
      {(asianHcLines.length > 0 || asianTotalLines.length > 0) && (
        <>
          <Divider />
          <div>
            <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
              Mercados asiáticos
            </p>
            {asianHcLines.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-gray-500 mb-1">Hándicap Asiático</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-400 border-b border-gray-100">
                        <th className="text-left py-1 pr-3 font-medium">Línea</th>
                        <th className="text-right py-1 pr-3 font-medium">{match.home_team}</th>
                        <th className="text-right py-1 pr-3 font-medium">Push</th>
                        <th className="text-right py-1 font-medium">{match.away_team}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {asianHcLines.map(({ line, prob_home_covers, prob_away_covers, prob_push }) => (
                        <tr key={line} className="border-b border-gray-50 last:border-0">
                          <td className="py-1.5 pr-3 font-mono text-gray-600">
                            {line > 0 ? `+${line}` : line}
                          </td>
                          <td className="text-right py-1.5 pr-3 font-semibold text-blue-600">
                            {Math.round(prob_home_covers * 100)}%
                          </td>
                          <td className="text-right py-1.5 pr-3 text-gray-400">
                            {prob_push > 0 ? `${Math.round(prob_push * 100)}%` : '—'}
                          </td>
                          <td className="text-right py-1.5 font-semibold text-red-500">
                            {Math.round(prob_away_covers * 100)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {asianTotalLines.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Total Asiático (Goles)</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-400 border-b border-gray-100">
                        <th className="text-left py-1 pr-3 font-medium">Línea</th>
                        <th className="text-right py-1 pr-3 font-medium">Over</th>
                        <th className="text-right py-1 pr-3 font-medium">Push</th>
                        <th className="text-right py-1 font-medium">Under</th>
                      </tr>
                    </thead>
                    <tbody>
                      {asianTotalLines.map(({ line, prob_over, prob_under, prob_push }) => (
                        <tr key={line} className="border-b border-gray-50 last:border-0">
                          <td className="py-1.5 pr-3 font-mono text-gray-600">{line}</td>
                          <td className="text-right py-1.5 pr-3 font-semibold text-green-600">
                            {Math.round(prob_over * 100)}%
                          </td>
                          <td className="text-right py-1.5 pr-3 text-gray-400">
                            {prob_push > 0 ? `${Math.round(prob_push * 100)}%` : '—'}
                          </td>
                          <td className="text-right py-1.5 font-semibold text-orange-500">
                            {Math.round(prob_under * 100)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Goal Ranges (Winamax) ── */}
      {goalRanges.length > 0 && (
        <>
          <Divider />
          <div>
            <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
              Intervalos de goles (Winamax)
            </p>
            <div className="space-y-2">
              {goalRanges.map(range => (
                <HorizontalBar
                  key={range.label}
                  label={range.label}
                  value={range.prob}
                  displayValue={`${Math.round(range.prob * 100)}%`}
                  color="purple"
                />
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── Top Scorers ── */}
      {hasTopScorers && (
        <>
          <Divider />
          <div>
            <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
              Máximos goleadores probables
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500 mb-2 font-medium">{match.home_team}</p>
                {topHome.map(p => (
                  <div key={p.name} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{p.name}</p>
                      <p className="text-[10px] text-gray-400 uppercase">{p.position}</p>
                    </div>
                    <span className="text-xs font-semibold text-blue-600 ml-2 shrink-0">
                      {Math.round(p.prob_anytime_scorer * 100)}%
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-2 font-medium">{match.away_team}</p>
                {topAway.map(p => (
                  <div key={p.name} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                    <div>
                      <p className="text-sm font-medium text-gray-800">{p.name}</p>
                      <p className="text-[10px] text-gray-400 uppercase">{p.position}</p>
                    </div>
                    <span className="text-xs font-semibold text-red-500 ml-2 shrink-0">
                      {Math.round(p.prob_anytime_scorer * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

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
        Cuotas: {updatedAt} · Modelo: Elo + Dixon-Coles Poisson v2
      </p>
    </div>
  )
}

function Divider() {
  return <hr className="border-gray-100" />
}
