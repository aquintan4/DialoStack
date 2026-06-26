import { useState } from 'react'
import { Plus } from 'lucide-react'
import { SlotCard } from '../SlotCard'
import { emptySlot } from '../../../lib/frames'

/**
 * Slots editor (slot_filling mode): drag-reorderable list with the constraint
 * that a dependent slot never sits above its condition.
 */
export function SlotsEditor({ slots, onChange }) {
  const [dragIndex, setDragIndex] = useState(null)

  const addSlot = () => onChange([...slots, emptySlot()])
  const updateSlot = (i, updated) => onChange(slots.map((s, idx) => (idx === i ? updated : s)))
  const removeSlot = (i) => onChange(slots.filter((_, idx) => idx !== i))

  // A dependent slot must sit below the slot it depends on.
  function isValidOrder(list) {
    const pos = new Map(list.map((s, i) => [s.name.trim(), i]))
    return list.every((s, i) => {
      if (!s.condition_slot) return true
      const parentIdx = pos.get(s.condition_slot)
      return parentIdx === undefined || parentIdx < i
    })
  }

  function handleDragEnter(i) {
    if (dragIndex === null || dragIndex === i) return
    const next = [...slots]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(i, 0, moved)
    if (!isValidOrder(next)) return
    onChange(next)
    setDragIndex(i)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Slots</h2>
        <button
          onClick={addSlot}
          className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400 transition-colors"
        >
          <Plus size={13} />
          Add slot
        </button>
      </div>

      <div className="space-y-2">
        {slots.map((slot, i) => (
          <SlotCard
            key={i}
            slot={slot}
            index={i}
            allSlots={slots}
            onChange={(updated) => updateSlot(i, updated)}
            onRemove={() => removeSlot(i)}
            onDragStart={setDragIndex}
            onDragEnter={handleDragEnter}
            onDragEnd={() => setDragIndex(null)}
            isDragging={dragIndex === i}
          />
        ))}
      </div>
    </div>
  )
}
