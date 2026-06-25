import Link from 'next/link'
import { getMatch, getAnalysis } from '@/lib/data'
import ProbabilityBar from '@/components/ProbabilityBar'
import AnalysisPanel from '@/components/AnalysisPanel'

type Props = {
  params: { id: string }
}

function Badges({
  has_value_bet,
  confidence,
}: {
  has_value_bet: boolean
  confidence: string | null
}) {
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

export default function MatchPage({ params }: Props) {
  const match = getMatch(params.id)
  const analysis = getAnalysis(params.id)

  if (!match) {
    return (
      <main className="max-w-2xl mx-auto px-4 pt-8">
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1 mb-6"
        >
          ← Volver a todos los partidos
        </Link>
        <div className="text-center py-16">
          <p className="text-gray-500 text-sm">
            Análisis no disponible para este partido.
          </p>
          <p className="text-gray-400 text-xs mt-1">
            El pipeline se ejecuta dos veces al día.
          </p>
        </div>
      </main>
    )
  }

  const pHome = Math.round(match.prob_home * 100)
  const pDraw = Math.round(match.prob_draw * 100)
  const pAway = Math.round(match.prob_away * 100)

  const matchDateFmt = new Date(match.date + 'T12:00:00').toLocaleDateString('es-ES', {
    day: 'numeric',
    month: 'short',
  })

  return (
    <main className="max-w-2xl mx-auto px-4 pb-16">
      {/* Back link */}
      <div className="pt-5 pb-4">
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          ← Volver a todos los partidos
        </Link>
      </div>

      {/* Match header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900">
          {match.home_team} vs {match.away_team}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {match.phase} · {matchDateFmt} · {match.kickoff} CET · {match.venue}
        </p>
        <div className="mt-2">
          <Badges
            has_value_bet={match.has_value_bet}
            confidence={match.confidence}
          />
        </div>
      </div>

      {/* Probability bar */}
      <div className="mb-1">
        <ProbabilityBar
          probHome={match.prob_home}
          probDraw={match.prob_draw}
          probAway={match.prob_away}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-500 mt-1.5 mb-6">
        <span>
          <span className="font-bold text-sm text-blue-600">{pHome}%</span>
          {' '}{match.home_team}
        </span>
        <span>
          Empate{' '}
          <span className="font-bold text-sm text-gray-400">{pDraw}%</span>
        </span>
        <span>
          {match.away_team}{' '}
          <span className="font-bold text-sm text-red-600">{pAway}%</span>
        </span>
      </div>

      {/* Analysis or no-data state */}
      {analysis ? (
        <AnalysisPanel match={match} analysis={analysis} />
      ) : (
        <div className="py-8 text-center text-sm text-gray-400">
          Análisis en proceso. El pipeline se ejecuta dos veces al día.
        </div>
      )}

      {/* Page footer */}
      <p className="text-xs text-gray-400 text-center mt-10 pb-4">
        Herramienta de análisis, no garantía de resultado.
      </p>
    </main>
  )
}
