type Props = {
  probHome: number
  probDraw: number
  probAway: number
}

export default function ProbabilityBar({ probHome, probDraw, probAway }: Props) {
  const total = probHome + probDraw + probAway || 1
  const pct = (v: number) => `${((v / total) * 100).toFixed(1)}%`

  return (
    <div className="flex h-2 rounded-full overflow-hidden w-full">
      <div className="bg-blue-600 h-full" style={{ width: pct(probHome) }} />
      <div className="bg-gray-400 h-full" style={{ width: pct(probDraw) }} />
      <div className="bg-red-600 h-full" style={{ width: pct(probAway) }} />
    </div>
  )
}
