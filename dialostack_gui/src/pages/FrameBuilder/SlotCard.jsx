/** Editable card for a single slot: name, type, canonical values, numeric range and condition. */
import { useState } from 'react'
import { GripVertical, Link2, Trash2, X, Plus } from 'lucide-react'
import { Select } from '../../components/ui'
import { SLOT_TYPES, NUMERIC_TYPES, LOWER_OPS, UPPER_OPS } from '../../lib/frames'

const rangeInputCls = `bg-app-700 border border-app-border rounded-lg px-2 py-1
  text-xs text-slate-300 placeholder-slate-600 focus:outline-none
  focus:border-brand-600 font-mono w-20`

const rangeSelectCls = `bg-app-700 border border-app-border rounded-lg px-2 py-1 w-full
  text-xs text-slate-300 focus:outline-none focus:border-brand-600 cursor-pointer font-mono`

// Slot fields edited by each RangeInputs instance (see VALUE_RANGE/CONDITION_RANGE in frames.js).
const VALUE_FIELDS = { min_op: 'min_op', min: 'min', max_op: 'max_op', max: 'max' }
const CONDITION_FIELDS = { min_op: 'cond_min_op', min: 'cond_min', max_op: 'cond_max_op', max: 'cond_max' }

/** Same rule as the engine (DialogFrame._parse_bounds): reject an empty range. */
function rangeError(slot, f) {
  const lo = Number(slot[f.min])
  const hi = Number(slot[f.max])
  if (String(slot[f.min] ?? '').trim() === '' || String(slot[f.max] ?? '').trim() === '') return null
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return 'Bounds must be numbers'
  const inclusive = (slot[f.min_op] ?? '>=') === '>=' && (slot[f.max_op] ?? '<=') === '<='
  if (lo > hi || (lo === hi && !inclusive)) return 'Empty range: no value can satisfy it'
  return null
}

/** Lower and upper bound, each an operator + a number; either side may stay empty. */
function RangeInputs({ slot, fields, onField }) {
  const error = rangeError(slot, fields)
  const side = (ops, opField, valField, placeholder, fallback) => (
    <>
      <Select
        value={slot[opField] ?? fallback}
        onChange={(e) => onField(opField, e.target.value)}
        className={rangeSelectCls}
        wrapClassName="w-16"
      >
        {ops.map((o) => <option key={o.value} value={o.value}>{o.value}</option>)}
      </Select>
      <input
        type="number"
        placeholder={placeholder}
        value={slot[valField] ?? ''}
        onChange={(e) => onField(valField, e.target.value)}
        className={rangeInputCls}
      />
    </>
  )
  return (
    <>
      {side(LOWER_OPS, fields.min_op, fields.min, 'min', '>=')}
      <span className="text-xs text-slate-600">and</span>
      {side(UPPER_OPS, fields.max_op, fields.max, 'max', '<=')}
      {error && <span className="text-xs text-red-400">{error}</span>}
    </>
  )
}

const compactSelectCls = `bg-app-700 border border-app-border rounded-lg px-2 py-1.5
  text-sm text-slate-300 focus:outline-none focus:border-brand-600
  focus:ring-1 focus:ring-brand-600/30 cursor-pointer w-full`

export function SlotCard({
  slot, index, allSlots, onChange, onRemove,
  onDragStart, onDragEnter, onDragEnd, isDragging,
}) {
  const eligibleParents = allSlots.filter((s, i) => i !== index && s.name.trim())
  const dependent = Boolean(slot.condition_slot)
  const parent = allSlots.find((s) => s.name === slot.condition_slot)
  const parentNumeric = Boolean(parent && NUMERIC_TYPES.includes(parent.type))
  const rangeCondition = slot.condition_mode === 'range'
  // Dragging is only armed when grabbing the handle, to avoid interfering with
  // text selection in the card's inputs.
  const [armed, setArmed] = useState(false)

  function handleField(field, value) {
    onChange({ ...slot, [field]: value })
  }

  function addCanonical() {
    handleField('canonical_values', [...slot.canonical_values, ''])
  }

  function updateCanonical(i, val) {
    const updated = [...slot.canonical_values]
    updated[i] = val
    handleField('canonical_values', updated)
  }

  function removeCanonical(i) {
    handleField('canonical_values', slot.canonical_values.filter((_, idx) => idx !== i))
  }

  return (
    <div
      draggable={armed}
      onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; onDragStart(index) }}
      onDragEnter={() => onDragEnter(index)}
      onDragOver={(e) => e.preventDefault()}
      onDragEnd={() => { setArmed(false); onDragEnd() }}
      className={`bg-app-800 border rounded-xl p-4 space-y-3 animate-slide-up transition-all ${
        isDragging ? 'border-brand-500/60 opacity-60 shadow-lg' : 'border-app-border'
      }`}
    >
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span
          title={dependent
            ? `Drag to reorder - it will always stay below "${slot.condition_slot}"`
            : 'Drag to reorder'}
          onMouseDown={() => setArmed(true)}
          onMouseUp={() => setArmed(false)}
          className="text-slate-600 hover:text-slate-400 cursor-grab active:cursor-grabbing flex-shrink-0"
        >
          <GripVertical size={14} />
        </span>
        {dependent && (
          <span title={`Depends on "${slot.condition_slot}"`} className="text-brand-500/70 flex-shrink-0">
            <Link2 size={12} />
          </span>
        )}
        <span className="text-xs text-slate-600 font-mono w-5 text-center flex-shrink-0">
          {index + 1}
        </span>

        {/* Name */}
        <input
          type="text"
          placeholder="slot_name"
          value={slot.name}
          onChange={(e) => handleField('name', e.target.value)}
          className="flex-1 bg-app-700 border border-app-border rounded-lg px-3 py-1.5
            text-sm text-slate-200 placeholder-slate-600 focus:outline-none
            focus:border-brand-600 focus:ring-1 focus:ring-brand-600/30 font-mono"
        />

        {/* Type */}
        <Select
          value={slot.type}
          onChange={(e) => handleField('type', e.target.value)}
          className={compactSelectCls}
          wrapClassName="w-40 flex-shrink-0"
        >
          {SLOT_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </Select>

        {/* Remove */}
        <button
          onClick={onRemove}
          className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20
            rounded-lg transition-colors flex-shrink-0"
        >
          <Trash2 size={14} />
        </button>
      </div>

      {/* Canonical values */}
      <div className="pl-7 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600">Canonical values</span>
          <button
            onClick={addCanonical}
            className="text-xs text-brand-500 hover:text-brand-400 flex items-center gap-0.5
              transition-colors"
          >
            <Plus size={11} />
            add
          </button>
        </div>

        {slot.canonical_values.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {slot.canonical_values.map((val, i) => (
              <div key={i} className="flex items-center gap-1 bg-app-700 border border-app-border
                rounded-md pl-2 pr-1 py-0.5">
                <input
                  type="text"
                  value={val}
                  onChange={(e) => updateCanonical(i, e.target.value)}
                  placeholder="value"
                  className="bg-transparent text-xs text-slate-300 placeholder-slate-600
                    focus:outline-none w-20 font-mono"
                />
                <button
                  onClick={() => removeCanonical(i)}
                  className="text-slate-600 hover:text-slate-400 transition-colors"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Numeric range (int/float only) */}
        {NUMERIC_TYPES.includes(slot.type) && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-600">Range</span>
            <RangeInputs slot={slot} fields={VALUE_FIELDS} onField={handleField} />
          </div>
        )}

        {/* Condition */}
        {eligibleParents.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-600">Condition</span>
            <Select
              value={slot.condition_slot}
              onChange={(e) => handleField('condition_slot', e.target.value)}
              className="bg-app-700 border border-app-border rounded-lg px-2 py-1 w-full
                text-xs text-slate-300 focus:outline-none focus:border-brand-600 cursor-pointer"
              wrapClassName="w-32"
            >
              <option value="">none</option>
              {eligibleParents.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </Select>

            {/* Numeric parents can also be tested against a range (>, <, between). */}
            {slot.condition_slot && (parentNumeric || rangeCondition) && (
              <Select
                value={slot.condition_mode ?? 'equals'}
                onChange={(e) => handleField('condition_mode', e.target.value)}
                className={rangeSelectCls}
                wrapClassName="w-24"
              >
                <option value="equals">equals</option>
                <option value="range">in range</option>
              </Select>
            )}

            {slot.condition_slot && rangeCondition && (
              <>
                <RangeInputs slot={slot} fields={CONDITION_FIELDS} onField={handleField} />
                {!parentNumeric && (
                  <span className="text-xs text-red-400">Range conditions need an int or float parent</span>
                )}
              </>
            )}

            {slot.condition_slot && !rangeCondition && (
              <>
                <span className="text-xs text-slate-600">=</span>
                <input
                  type="text"
                  placeholder="value"
                  value={slot.condition_value}
                  onChange={(e) => handleField('condition_value', e.target.value)}
                  className="bg-app-700 border border-app-border rounded-lg px-2 py-1
                    text-xs text-slate-300 placeholder-slate-600 focus:outline-none
                    focus:border-brand-600 font-mono w-24"
                />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
