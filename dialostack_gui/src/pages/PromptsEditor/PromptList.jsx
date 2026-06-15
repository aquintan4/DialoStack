import { RotateCcw, Search } from 'lucide-react'

/**
 * Left column of the prompts editor: header (title + toolbar + toast +
 * "reset all"), filter and grouped list with a "modified" dot.
 * Presentational: all state and handlers live in the container.
 */
export function PromptList({
  toolbar, toast, overrideCount, onResetAll,
  filter, onFilterChange, groups, selected, onSelect, isOverridden,
}) {
  const visible = (keys) => keys.filter((k) => k.includes(filter.trim().toLowerCase()))

  return (
    <div className="flex flex-col w-[38%] border-r border-app-border overflow-hidden">
      <div className="px-5 py-4 border-b border-app-border bg-app-900 flex-shrink-0">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-sm font-semibold text-slate-100 flex-shrink-0">Prompts</h1>
          {toolbar}
        </div>
        {toast && <p className="mt-2 text-[11px] text-brand-400">{toast}</p>}
        {overrideCount > 0 && (
          <button
            onClick={onResetAll}
            className="flex items-center gap-1 mt-2 text-[11px] text-slate-500 hover:text-red-400 transition-colors"
          >
            <RotateCcw size={11} />
            Reset all ({overrideCount})
          </button>
        )}
        <div className="relative mt-3">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
          <input
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            placeholder="Filter…"
            className="w-full bg-app-800 border border-app-border rounded-lg pl-8 pr-3 py-1.5
              text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {groups.map((g) => {
          const keys = visible(g.keys)
          if (!keys.length) return null
          return (
            <div key={g.label}>
              <p className="px-1 mb-1 text-[10px] font-semibold text-slate-600 uppercase tracking-wider">
                {g.label}
              </p>
              <div className="space-y-0.5">
                {keys.map((key) => (
                  <button
                    key={key}
                    onClick={() => onSelect(key)}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg
                      text-xs font-mono transition-colors ${
                        selected === key
                          ? 'bg-brand-glow border border-brand-600/40 text-brand-300'
                          : 'text-slate-400 hover:bg-app-700 hover:text-slate-200 border border-transparent'
                      }`}
                  >
                    <span className="truncate">{key}</span>
                    {isOverridden(key) && (
                      <span title="Modified" className="w-1.5 h-1.5 rounded-full bg-brand-400 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
