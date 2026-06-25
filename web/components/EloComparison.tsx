type Props = {
  eloHome: number
  eloAway: number
  eloAdvantage: number
  homeTeam: string
  awayTeam: string
}

export default function EloComparison({
  eloHome,
  eloAway,
  eloAdvantage,
  homeTeam,
  awayTeam,
}: Props) {
  const maxElo = Math.max(eloHome, eloAway)
  const homeWidth = Math.round((eloHome / maxElo) * 100)
  const awayWidth = Math.round((eloAway / maxElo) * 100)

  return (
    <div>
      <p className="text-[11px] uppercase tracking-widest text-gray-400 font-medium mb-3">
        Fuerza relativa — Elo
      </p>
      <div className="grid grid-cols-3 items-end gap-2">
        {/* Home */}
        <div>
          <p className="text-4xl font-bold text-gray-900 tabular-nums">{eloHome}</p>
          <p className="text-xs text-gray-500 mt-0.5 mb-2 truncate">{homeTeam}</p>
          <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${homeWidth}%` }} />
        </div>

        {/* Centre */}
        <div className="text-center pb-1">
          <p className="text-sm font-semibold text-gray-700">
            {eloAdvantage > 0 ? `+${eloAdvantage}` : eloAdvantage} pts
          </p>
          <p className="text-xs text-gray-400">ventaja local</p>
        </div>

        {/* Away */}
        <div className="text-right">
          <p className="text-4xl font-bold text-gray-600 tabular-nums">{eloAway}</p>
          <p className="text-xs text-gray-500 mt-0.5 mb-2 truncate">{awayTeam}</p>
          <div className="flex justify-end">
            <div
              className="h-1.5 rounded-full bg-blue-400"
              style={{ width: `${awayWidth}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
