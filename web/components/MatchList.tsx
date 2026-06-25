'use client'

import { useState } from 'react'
import type { Match, Analysis } from '@/lib/data'
import { formatDateLabel } from '@/lib/utils'
import FilterTabs, { type Filter } from './FilterTabs'
import MatchCard from './MatchCard'

type Props = {
  matches: Match[]
  analyses: Record<string, Analysis>
}

function filterMatches(matches: Match[], filter: Filter): Match[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  return matches.filter(m => {
    const matchDate = new Date(m.date + 'T00:00:00')

    if (filter === 'today') {
      return matchDate.toDateString() === today.toDateString()
    }
    if (filter === '3days') {
      const limit = new Date(today)
      limit.setDate(limit.getDate() + 3)
      return matchDate >= today && matchDate <= limit
    }
    if (filter === 'groups') {
      return m.phase.toLowerCase().includes('grupo') ||
             m.phase.toLowerCase().includes('jornada')
    }
    if (filter === 'knockout') {
      return (
        m.phase.toLowerCase().includes('octavos') ||
        m.phase.toLowerCase().includes('cuartos') ||
        m.phase.toLowerCase().includes('semis') ||
        m.phase.toLowerCase().includes('semifinal') ||
        m.phase.toLowerCase().includes('final')
      )
    }
    return true
  })
}

function defaultFilter(matches: Match[]): Filter {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const hasToday = matches.some(
    m => new Date(m.date + 'T00:00:00').toDateString() === today.toDateString()
  )
  return hasToday ? 'today' : '3days'
}

export default function MatchList({ matches, analyses }: Props) {
  const [filter, setFilter] = useState<Filter>(() => defaultFilter(matches))
  const filtered = filterMatches(matches, filter)

  // Group by date
  const byDate = filtered.reduce<Record<string, Match[]>>((acc, m) => {
    if (!acc[m.date]) acc[m.date] = []
    acc[m.date].push(m)
    return acc
  }, {})
  const dates = Object.keys(byDate).sort()

  return (
    <div>
      <FilterTabs active={filter} onChange={setFilter} />

      <div className="mt-4 space-y-6">
        {dates.length === 0 && (
          <div className="py-12 text-center text-sm text-gray-400">
            No hay partidos disponibles. El pipeline se ejecuta dos veces al día.
          </div>
        )}

        {dates.map(date => (
          <div key={date}>
            <p className="text-sm font-semibold text-gray-500 pb-3">
              {formatDateLabel(date)},{' '}
              {new Date(date + 'T12:00:00').toLocaleDateString('es-ES', {
                day: 'numeric',
                month: 'short',
              })}
            </p>
            <div className="space-y-3">
              {byDate[date].map(m => (
                <MatchCard key={m.id} match={m} analysis={analyses[m.id] ?? null} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Decorative CTA */}
      {filtered.length > 0 && (
        <div className="flex justify-center mt-8">
          <button className="text-sm text-gray-600 border border-gray-300 rounded-full px-5 py-2 hover:bg-gray-50 transition-colors flex items-center gap-1.5">
            Me gusta, dame el mapa completo
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 16 16"
              fill="currentColor"
              className="w-3.5 h-3.5"
            >
              <path
                fillRule="evenodd"
                d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}
