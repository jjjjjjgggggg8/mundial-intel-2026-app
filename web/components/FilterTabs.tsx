'use client'

export type Filter = 'today' | '3days' | 'groups' | 'knockout'

type Props = {
  active: Filter
  onChange: (f: Filter) => void
}

const tabs: { id: Filter; label: string }[] = [
  { id: 'today',    label: 'Hoy' },
  { id: '3days',    label: '3 días' },
  { id: 'groups',   label: 'Grupos' },
  { id: 'knockout', label: 'Eliminatorias' },
]

export default function FilterTabs({ active, onChange }: Props) {
  return (
    <div className="flex gap-1.5 overflow-x-auto flex-nowrap pb-0.5">
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={
            tab.id === active
              ? 'px-3 py-1.5 rounded-full text-sm font-medium bg-white border border-gray-300 shadow-sm text-gray-800 whitespace-nowrap shrink-0'
              : 'px-3 py-1.5 rounded-full text-sm text-gray-500 whitespace-nowrap shrink-0 hover:text-gray-700'
          }
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
