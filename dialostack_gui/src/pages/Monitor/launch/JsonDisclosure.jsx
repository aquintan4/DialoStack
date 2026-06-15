/** Collapsible JSON textarea with inline validation, plus the "Open in Builder" link. */
import { ChevronDown, ChevronUp, Layers } from 'lucide-react'

/** Discreet "Open in Builder" button reused on each advanced surface. */
export function EditInBuilderLink({ onClick }) {
  return (
    <button
      onClick={onClick}
      title="Edit visually in the Frame Builder"
      className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-brand-400 transition-colors flex-shrink-0"
    >
      <Layers size={11} />
      Open in Builder ↗
    </button>
  )
}

/** Collapsible section with a JSON textarea and inline validation (+ optional action). */
export function JsonDisclosure({ label, open, onToggle, value, onChange, error, rows, placeholder, action }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={onToggle}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {label}
          {value.trim() && !error && <span className="text-brand-500 text-[10px]">●</span>}
          {error && <span className="text-red-400 text-[10px]">{error}</span>}
        </button>
        {action}
      </div>
      {open && (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          spellCheck={false}
          placeholder={placeholder}
          className={`mt-2 w-full bg-app-800 border rounded-lg px-3 py-2
            text-xs text-slate-300 font-mono placeholder-slate-600 focus:outline-none
            transition-colors resize-none ${
              error ? 'border-red-700/60 focus:border-red-600' : 'border-app-border focus:border-brand-600'
            }`}
        />
      )}
    </div>
  )
}
