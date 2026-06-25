import 'server-only'
import fs from 'fs'
import path from 'path'

export type Match = {
  id: string
  phase: string
  date: string
  kickoff: string
  home_team: string
  away_team: string
  venue: string
  has_value_bet: boolean
  confidence: 'high' | 'medium' | 'low' | null
  prob_home: number
  prob_draw: number
  prob_away: number
  updated_at: string
}

export type AsianHandicapLine = {
  prob_home_covers: number
  prob_away_covers: number
  prob_push: number
  is_asian: boolean
}

export type AsianTotalLine = {
  prob_over: number
  prob_under: number
  prob_push: number
  is_asian: boolean
}

export type GoalRange = {
  label: string
  min_goals: number
  max_goals: number
  prob: number
}

export type TopScorer = {
  name: string
  position: string
  prob_anytime_scorer: number
  lambda_goals: number
}

export type Analysis = {
  elo_home: number
  elo_away: number
  elo_advantage: number
  probs: {
    home_win: number
    draw: number
    away_win: number
    over_0_5: number
    over_1_5: number
    over_2_5: number
    over_3_5: number
    btts: number
    expected_goals_home: number
    expected_goals_away: number
  }
  top_scorelines: Array<{ score: string; prob: number }>
  high_prob_events: Array<{ event: string; prob: number }>
  asian_handicap?: Record<string, AsianHandicapLine>
  asian_total?: Record<string, AsianTotalLine>
  goal_ranges?: GoalRange[]
  top_scorers?: {
    home: TopScorer[]
    away: TopScorer[]
  }
  value_bets: Array<{
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
  }>
  gemini_analysis: string | null
  odds_updated_at: string | null
}

export function getMatches(): Match[] {
  try {
    const filePath = path.join(process.cwd(), 'public', 'data', 'matches.json')
    const raw = fs.readFileSync(filePath, 'utf-8')
    const matches: Match[] = JSON.parse(raw)
    return matches.sort((a, b) => {
      const dateA = new Date(`${a.date}T${a.kickoff}:00`)
      const dateB = new Date(`${b.date}T${b.kickoff}:00`)
      return dateA.getTime() - dateB.getTime()
    })
  } catch {
    return []
  }
}

export function getAnalyses(): Record<string, Analysis> {
  try {
    const filePath = path.join(process.cwd(), 'public', 'data', 'analyses.json')
    const raw = fs.readFileSync(filePath, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

export function getAnalysis(id: string): Analysis | null {
  const analyses = getAnalyses()
  return analyses[id] ?? null
}

export function getMatch(id: string): Match | null {
  const matches = getMatches()
  return matches.find(m => m.id === id) ?? null
}
