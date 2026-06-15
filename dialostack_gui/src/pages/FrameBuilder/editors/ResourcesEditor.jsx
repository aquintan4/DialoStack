import { Plus, Trash2 } from 'lucide-react'
import { emptyResource } from '../../../lib/frames'

/**
 * Reference resources editor (explanation mode). Each resource has a name, a
 * short description and the content the engine injects as a [CONTEXT] block in
 * the prompts.
 */
export function ResourcesEditor({ resources, onChange }) {
  const update = (i, field, value) =>
    onChange(resources.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)))
  const remove = (i) => onChange(resources.filter((_, idx) => idx !== i))
  const add = () => onChange([...resources, emptyResource()])

  const inputCls = `w-full bg-app-700 border border-app-border rounded-md px-2.5 py-1.5
    text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors`

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Reference resources
        </h2>
        <button
          onClick={add}
          className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400 transition-colors"
        >
          <Plus size={13} />
          Add resource
        </button>
      </div>

      {resources.length === 0 && (
        <p className="text-xs text-slate-600 italic">No resources - add the material to explain.</p>
      )}

      {resources.map((r, i) => (
        <div key={i} className="bg-app-800 border border-app-border rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={r.name}
              onChange={(e) => update(i, 'name', e.target.value)}
              placeholder="name (e.g. instructions)"
              className={`${inputCls} font-mono flex-1`}
            />
            <button
              onClick={() => remove(i)}
              className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors flex-shrink-0"
            >
              <Trash2 size={14} />
            </button>
          </div>
          <input
            type="text"
            value={r.description}
            onChange={(e) => update(i, 'description', e.target.value)}
            placeholder="short description (optional)"
            className={inputCls}
          />
          <textarea
            rows={4}
            value={r.content}
            onChange={(e) => update(i, 'content', e.target.value)}
            placeholder="Content the robot will explain..."
            className={`${inputCls} resize-none leading-relaxed`}
          />
        </div>
      ))}
    </div>
  )
}
