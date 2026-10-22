import { ChevronDown, ChevronUp, Plus, X } from 'lucide-react'
import { emptyStep } from '../../../lib/frames'

const inputCls = `w-full bg-app-700 border border-app-border rounded-md px-2.5 py-1.5
  text-xs placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors`

/**
 * Ordered step editor (procedure mode). Shared by the Frame Builder and the
 * LaunchDrawer. Each step has its instruction and an optional check (what the
 * user should observe or report once it is done).
 */
export function StepsEditor({ steps, onChange }) {
  const update = (i, field, value) =>
    onChange(steps.map((s, idx) => (idx === i ? { ...s, [field]: value } : s)))
  const remove = (i) => onChange(steps.filter((_, idx) => idx !== i))
  const add = () => onChange([...steps, emptyStep()])
  const move = (i, delta) => {
    const j = i + delta
    if (j < 0 || j >= steps.length) return
    const next = [...steps]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }

  const iconBtn = 'text-slate-600 hover:text-slate-300 disabled:opacity-30 disabled:hover:text-slate-600 transition-colors'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Procedure steps
        </h2>
        <button
          onClick={add}
          className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400 transition-colors"
        >
          <Plus size={13} />
          Add
        </button>
      </div>

      {steps.length === 0 && (
        <p className="text-xs text-slate-600 italic">No steps - add at least one.</p>
      )}

      {steps.map((s, i) => (
        <div key={i} className="bg-app-800 border border-app-border rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">Step {i + 1}</span>
            <div className="flex items-center gap-1.5">
              <button onClick={() => move(i, -1)} disabled={i === 0} title="Move up" className={iconBtn}>
                <ChevronUp size={13} />
              </button>
              <button onClick={() => move(i, 1)} disabled={i === steps.length - 1} title="Move down" className={iconBtn}>
                <ChevronDown size={13} />
              </button>
              <button onClick={() => remove(i)} title="Remove" className="text-slate-600 hover:text-red-400 transition-colors">
                <X size={12} />
              </button>
            </div>
          </div>
          <textarea
            rows={2}
            value={s.step}
            onChange={(e) => update(i, 'step', e.target.value)}
            placeholder="Roll your shoulders back slowly five times"
            className={`${inputCls} text-slate-200 resize-none`}
          />
          <input
            type="text"
            value={s.check}
            onChange={(e) => update(i, 'check', e.target.value)}
            placeholder="Check (optional): what the user should see or report, e.g. no pain"
            className={`${inputCls} text-slate-300`}
          />
        </div>
      ))}
    </div>
  )
}
