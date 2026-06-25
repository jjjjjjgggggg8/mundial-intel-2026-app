type BarColor = 'blue' | 'gray' | 'red' | 'green' | 'indigo' | 'yellow'

type Props = {
  label: string
  value: number        // 0–1 for pct, or 0–1 for scoreline prob
  displayValue: string // e.g. "47%" or "1-1 (14%)"
  color?: BarColor
}

const colorMap: Record<BarColor, string> = {
  blue:   'bg-blue-600',
  gray:   'bg-gray-400',
  red:    'bg-red-500',
  green:  'bg-green-600',
  indigo: 'bg-indigo-500',
  yellow: 'bg-yellow-500',
}

export default function HorizontalBar({
  label,
  value,
  displayValue,
  color = 'blue',
}: Props) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-700 w-36 shrink-0">{label}</span>
      <div className="bg-gray-100 flex-1 h-2 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${colorMap[color]}`}
          style={{ width: `${Math.min(value * 100, 100).toFixed(1)}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-gray-800 w-20 text-right shrink-0">
        {displayValue}
      </span>
    </div>
  )
}
