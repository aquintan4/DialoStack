/** Tag filter: button + popover to choose which metric tags are shown in the chat bubbles. */
import { Tags } from 'lucide-react'
import { Toggle } from '../../components/ui'
import { usePopover } from '../../hooks/usePopover'

// Tags that can be hidden in the chat bubbles. `key` must match what
// UserBubble/RobotBubble check in ChatBubble.jsx.
export const TAG_DEFS = [
  { key: 'time', label: 'Time', sample: '12:00:00' },
  { key: 'transcription', label: 'Transcription', sample: '🎙️ 1.2s' },
  { key: 'inference', label: 'Inference (LLM)', sample: '⚡ 0.8s' },
  { key: 'speech', label: 'Speech (TTS)', sample: '🔊 2.1s' },
  { key: 'interruptions', label: 'Interruptions', sample: '⚡ Barge-in' },
]

export const DEFAULT_TAGS = Object.fromEntries(TAG_DEFS.map((t) => [t.key, true]))

/**
 * Button + popover to choose which tags are shown in the chat. The Monitor
 * governs the state (persisted); here it is only rendered and toggled.
 */
export function TagFilter({ value, onChange }) {
  const { open, setOpen, ref } = usePopover()
  const hidden = TAG_DEFS.filter((t) => value?.[t.key] === false).length

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Show or hide chat tags"
        className={`flex items-center gap-1.5 text-xs px-2.5 py-2 rounded-lg border transition-all ${
          open || hidden > 0
            ? 'text-brand-400 bg-brand-glow border-brand-600/40'
            : 'text-slate-500 hover:text-slate-300 hover:bg-app-700 border-transparent hover:border-app-border'
        }`}
      >
        <Tags size={13} />
        Tags
        {hidden > 0 && (
          <span className="text-[10px] font-semibold bg-brand-600/30 text-brand-300 rounded-full px-1.5 leading-4">
            {hidden}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-60 z-50 p-1.5 rounded-xl
          bg-app-800 border border-app-border shadow-xl shadow-black/50 animate-fade-in">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] text-slate-600 uppercase tracking-wide">
            Visible tags
          </p>
          {TAG_DEFS.map((t) => (
            <div key={t.key} className="flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-app-700">
              <div className="min-w-0">
                <span className="text-sm text-slate-300">{t.label}</span>
                <span className="block text-[11px] text-slate-600 truncate">{t.sample}</span>
              </div>
              <Toggle
                value={value?.[t.key] !== false}
                onChange={(v) => onChange({ ...value, [t.key]: v })}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
