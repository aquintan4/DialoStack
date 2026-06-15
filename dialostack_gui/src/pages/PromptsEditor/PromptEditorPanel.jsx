import { AlertTriangle, Check, RotateCcw } from 'lucide-react'

const monoCls = `w-full bg-app-800 border rounded-lg px-3 py-2 font-mono text-xs
  leading-relaxed text-slate-200 placeholder-slate-600 focus:outline-none resize-none transition-colors`

/**
 * Right column: editor for the selected prompt (allowed placeholders,
 * textarea with live validation and a status footer). Presentational.
 */
export function PromptEditorPanel({ selected, draft, onDraftChange, error, allowed, overridden, modified, onReset }) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-app-950/60">
      {selected && (
        <>
          <div className="px-5 py-4 border-b border-app-border bg-app-900 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <h2 className="text-sm font-mono font-semibold text-slate-100 truncate">{selected}</h2>
                {modified && (
                  <span className="text-[10px] text-brand-400 bg-brand-glow border border-brand-600/40 px-1.5 py-0.5 rounded-full flex-shrink-0">
                    modified
                  </span>
                )}
              </div>
              {overridden && (
                <button
                  onClick={onReset}
                  className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-200
                    hover:bg-app-700 px-2.5 py-1.5 rounded-lg border border-transparent hover:border-app-border transition-all"
                >
                  <RotateCcw size={12} />
                  Reset
                </button>
              )}
            </div>

            {/* Allowed placeholders */}
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              <span className="text-[11px] text-slate-600">Placeholders:</span>
              {allowed.length ? allowed.map((p) => (
                <span key={p} className="text-[10px] font-mono text-slate-400 bg-app-800 border border-app-border px-1.5 py-0.5 rounded">
                  {`{${p}}`}
                </span>
              )) : (
                <span className="text-[11px] text-slate-600 italic">none (fixed text)</span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-hidden p-5 flex flex-col">
            <textarea
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              spellCheck={false}
              className={`${monoCls} flex-1 ${error ? 'border-red-700/60 focus:border-red-600' : 'border-app-border focus:border-brand-600'}`}
            />
            {error ? (
              <p className="mt-2 flex items-start gap-1.5 text-xs text-red-400">
                <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
                {error} <span className="text-slate-600">- it will not be saved until you fix it.</span>
              </p>
            ) : (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-600">
                <Check size={13} className="text-green-500/70" />
                Literal braces are doubled (<span className="font-mono">{'{{'}</span> <span className="font-mono">{'}}'}</span>). Changes apply when the engine (re)starts.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
