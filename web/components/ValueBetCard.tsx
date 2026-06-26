type ValueBet = {
  market: string
  model_prob: number
  fair_odds: number
  best_ev: number
  best_bookmaker: string
  odds_bet365: number | null
  ev_bet365: number | null
  odds_winamax: number | null
  ev_winamax: number | null
  where_to_bet: string
}

type Props = {
  bet: ValueBet
}

function evLabel(ev: number): string {
  return `EV ${ev >= 0 ? '+' : ''}${(ev * 100).toFixed(1)}%`
}

export default function ValueBetCard({ bet }: Props) {
  const bestBm = bet.best_bookmaker.toLowerCase()
  const isBest365 = bestBm.includes('bet365') || bestBm.includes('365')
  const isBestWina = bestBm.toLowerCase().includes('winamax')

  const cellBase = 'rounded-lg p-3'
  const cellNeutral = `${cellBase} bg-gray-50 border border-gray-200`
  const cellBest = `${cellBase} bg-green-50 border border-green-200`

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white">
      {/* Header */}
      <div className="flex justify-between items-start gap-2">
        <p className="text-base font-semibold text-gray-900">{bet.market}</p>
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-green-100 text-green-700 shrink-0">
          Mejor EV: +{(bet.best_ev * 100).toFixed(1)}%
        </span>
      </div>
      <p className="text-xs text-gray-500 mt-0.5">
        Nuestro modelo: {Math.round(bet.model_prob * 100)}% · Cuota justa:{' '}
        {bet.fair_odds.toFixed(2)}
      </p>

      {/* Bookmaker grid */}
      <div className="grid grid-cols-2 gap-2 mt-3">
        {/* Bet365 */}
        <div className={isBest365 ? cellBest : cellNeutral}>
          <p className="text-xs text-gray-500 font-medium">
            Bet365{isBest365 && ' ☆'}
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {bet.odds_bet365 != null ? bet.odds_bet365.toFixed(2) : '—'}
          </p>
          <p className="text-xs text-green-600 font-medium mt-0.5">
            {bet.ev_bet365 != null ? evLabel(bet.ev_bet365) : '—'}
          </p>
        </div>

        {/* Winamax */}
        <div className={isBestWina ? cellBest : cellNeutral}>
          <p className="text-xs text-gray-500 font-medium">
            Winamax{isBestWina && ' ☆'}
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {bet.odds_winamax != null ? bet.odds_winamax.toFixed(2) : '—'}
          </p>
          <p className="text-xs text-green-600 font-medium mt-0.5">
            {bet.ev_winamax != null ? evLabel(bet.ev_winamax) : '—'}
          </p>
        </div>
      </div>

      {/* Where to bet breadcrumb */}
      <div className="mt-3 text-xs text-gray-600 bg-gray-100 rounded-md px-3 py-2 flex items-start gap-1">
        <span className="text-gray-400 shrink-0">→</span>
        <span>{bet.where_to_bet}</span>
      </div>
    </div>
  )
}
