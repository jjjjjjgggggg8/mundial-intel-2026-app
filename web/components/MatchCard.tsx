'use client'

import { useState } from 'react'
import type { Match, Analysis } from '@/lib/data'
import ProbabilityBar from './ProbabilityBar'
import AnalysisPanel from './AnalysisPanel'

type Props = {
  match: Match
  analysis: Analysis | null
}

function Badges({
  has_value_bet,
  confidence,
}: Pick<Match, 'has_value_bet' | 'confidence'>) {
  if (!has_value_bet) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
        Sin value claro
      </span>
    )
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
        Value bet detectado
      </span>
      {confidence === 'high' && (
        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
          Alta confianza
        </span>
      )}
      {confidence === 'medium' && (
        <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800 font-medium">
          Confianza media
        </span>
      )}
    </div>
  )
}

export default function MatchCard({ match, analysis }: Props) {
  const [open, setOpen] = useState(false)

  const pHome = Math.round(match.prob_home * 100)
  const pDraw = Math.round(match.prob_draw * 100)
  const pAway = Math.round(match.prob_away * 100)

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      {/* Top row: teams + phase */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-baseline gap-1 flex-wrap min-w-0">
          <span className="font-bold text-base text-gray-900 truncate">{match.home_team}</span>
          <span className="text-sm text-gray-400 mx-0.5">vs</span>
          <span className="font-bold text-base text-gray-900 truncate">{match.away_team}</span>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs font-semibold text-blue-600">{match.phase}</p>
          <p className="text-xs text-gray-500">
            {new Date(match.date + 'T12:00:00').toLocaleDateString('es-ES', {
              day: 'numeric',
              month: 'short',
            })}{' '}
            · {match.kickoff} CET
          </p>
        </div>
      </div>

      {/* Badges */}
      <div className="mb-3">
        <Badges has_value_bet={match.has_value_bet} confidence={match.confidence} />
      </div>

      {/* Probability bar */}
      <ProbabilityBar
        probHome={match.prob_home}
        probDraw={match.prob_draw}
        probAway={match.prob_away}
      />

      {/* Labels + percentages + button */}
      <div className="flex items-end justify-between mt-2">
        <div className="flex justify-between text-xs text-gray-500 flex-1 mr-4">
          <div>
            <p>{match.home_team.split(' ')[0]}</p>
            <p className="font-bold text-sm text-blue-600">{pHome}%</p>
          </div>
          <div className="text-center">
            <p>Empate</p>
            <p className="font-bold text-sm text-gray-400">{pDraw}%</p>
          </div>
          <div className="text-right">
            <p>{match.away_team.split(' ')[0]}</p>
            <p className="font-bold text-sm text-red-600">{pAway}%</p>
          </div>
        </div>

        {analysis && (
          <button
            onClick={() => setOpen(o => !o)}
            aria-label={open ? 'Cerrar análisis' : 'Ver análisis'}
            className="text-sm text-gray-700 border border-gray-300 rounded-md px-3 py-1.5 flex items-center gap-1 hover:bg-gray-50 shrink-0 transition-colors"
          >
            <span>{open ? 'Cerrar análisis' : 'Ver análisis'}</span>
            <span className="text-xs">{open ? '∧' : '∨'}</span>
          </button>
        )}
      </div>

      {/* Inline analysis panel */}
      {open && analysis && (
        <div className="mt-4 border-t border-gray-100 pt-2">
          <AnalysisPanel match={match} analysis={analysis} />
        </div>
      )}
    </div>
  )
}
