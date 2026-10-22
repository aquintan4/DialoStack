import { Plus, X } from 'lucide-react'
import { Field, inputCls } from '../../../components/ui'
import { emptyScene } from '../../../lib/frames'

/**
 * Roleplay scene editor (roleplay mode). Shared by the Frame Builder and the
 * LaunchDrawer. Edits a one-item dimension: the scene the robot acts out and
 * the criteria the user is scored on (1-5 each) when it ends.
 */
export function SceneEditor({ scenes, onChange }) {
  const scene = scenes?.[0] ?? emptyScene()
  const update = (patch) => onChange([{ ...scene, ...patch }])
  const criteria = scene.criteria?.length ? scene.criteria : ['']
  const setCriterion = (i, value) => update({ criteria: criteria.map((c, idx) => (idx === i ? value : c)) })
  const removeCriterion = (i) => update({ criteria: criteria.filter((_, idx) => idx !== i) })

  return (
    <div className="space-y-3">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Roleplay scene</h2>

      <Field label="Scenario" hint="The situation the user wants to practise">
        <textarea rows={2} value={scene.scenario} onChange={(e) => update({ scenario: e.target.value })}
          placeholder="Job interview for a robotics internship"
          className={`${inputCls} resize-none`} />
      </Field>
      <Field label="Robot's character" hint="Who the robot plays and how it behaves">
        <input type="text" value={scene.role} onChange={(e) => update({ role: e.target.value })}
          placeholder="The HR interviewer: demanding but kind"
          className={inputCls} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <Field label="User's goal" hint="Optional: what the user tries to achieve in the scene">
            <input type="text" value={scene.user_goal} onChange={(e) => update({ user_goal: e.target.value })}
              placeholder="Get the internship"
              className={inputCls} />
          </Field>
        </div>
        <Field label="Max. exchanges" hint="User turns before the scene closes (empty = 10, capped by Max. turns)">
          <input type="number" min={1} max={50} value={scene.max_exchanges}
            onChange={(e) => update({ max_exchanges: e.target.value })}
            placeholder="10"
            className={inputCls} />
        </Field>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400 font-medium">Evaluation criteria (scored 1-5)</span>
          <button onClick={() => update({ criteria: [...criteria, ''] })}
            className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400 transition-colors">
            <Plus size={13} />
            Add
          </button>
        </div>
        {criteria.map((c, i) => (
          <div key={i} className="flex items-center gap-2">
            <input type="text" value={c} onChange={(e) => setCriterion(i, e.target.value)}
              placeholder={i === 0 ? 'Answers clearly' : 'Gives concrete examples'}
              className={inputCls} />
            <button onClick={() => removeCriterion(i)} disabled={criteria.length === 1} title="Remove"
              className="text-slate-600 hover:text-red-400 disabled:opacity-30 disabled:hover:text-slate-600 transition-colors">
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
