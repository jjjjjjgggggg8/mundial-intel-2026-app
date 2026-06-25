import { getMatches, getAnalyses } from '@/lib/data'
import MatchList from '@/components/MatchList'

export default function HomePage() {
  const matches = getMatches()
  const analyses = getAnalyses()

  return (
    <main className="max-w-2xl mx-auto px-4 pb-16">
      {/* Header */}
      <div className="flex flex-col gap-3 pt-6 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Mundial Intel 2026</h1>
          <p className="text-xs text-gray-500 mt-0.5">Análisis · Picks · Value bets</p>
        </div>
      </div>

      {/* Match list with filters */}
      <MatchList matches={matches} analyses={analyses} />
    </main>
  )
}
