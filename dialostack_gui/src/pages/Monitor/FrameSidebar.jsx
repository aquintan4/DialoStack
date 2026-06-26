/** Monitor side panel: user emotion meter plus the active task's frame, with copy and edit-in-Builder actions. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Angry, Annoyed, Check, Copy, Frown, Layers, Meh, ScanFace, Smile, Sparkles } from 'lucide-react'
import { emptySlot, writeHandoff, HANDOFF_TO_BUILDER } from '../../lib/frames'

function inferType(value) {
  if (typeof value === 'boolean') return 'bool'
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'float'
  if (Array.isArray(value)) return 'list_str'
  return 'str'
}

// Appearance per emotion: icon + text and bar color
const EMOTIONS = {
  happy:    { icon: Smile,    text: 'text-green-400',  bar: 'bg-green-500',  label: 'Happy'      },
  surprise: { icon: Sparkles, text: 'text-brand-400',  bar: 'bg-brand-500',  label: 'Surprised'  },
  neutral:  { icon: Meh,      text: 'text-slate-400',  bar: 'bg-slate-500',  label: 'Neutral'    },
  sad:      { icon: Frown,    text: 'text-blue-400',   bar: 'bg-blue-500',   label: 'Sad'        },
  fear:     { icon: Annoyed,  text: 'text-orange-400', bar: 'bg-orange-500', label: 'Afraid'     },
  disgust:  { icon: Annoyed,  text: 'text-orange-400', bar: 'bg-orange-500', label: 'Disgusted'  },
  angry:    { icon: Angry,    text: 'text-red-400',    bar: 'bg-red-500',    label: 'Angry'      },
}

/** User emotion meter (data from /user_emotion, vision_io). */
function EmotionMeter({ emotion }) {
  const cfg = (emotion && EMOTIONS[emotion.emotion]) || null
  const pct = emotion ? Math.round(emotion.confidence * 100) : 0
  const Icon = cfg?.icon ?? ScanFace

  return (
    <div className="px-4 py-3 border-b border-app-border">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2.5">
        User emotion
      </h2>
      {emotion && cfg ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className={`flex items-center gap-1.5 text-sm font-medium ${cfg.text}`}>
              <Icon size={15} />
              {cfg.label}
            </span>
            <span className="text-xs text-slate-400 font-mono">{pct}%</span>
          </div>
          <div className="h-1.5 bg-app-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${cfg.bar}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-slate-600"
          title="Shown as soon as something publishes {emotion, confidence} on /user_emotion">
          <ScanFace size={14} />
          No data on <span className="font-mono">/user_emotion</span>
        </div>
      )}
    </div>
  )
}

/** Frame actions: copy it or open it as a schema in the Builder. */
function FrameActions({ frame }) {
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  function copyFrame() {
    navigator.clipboard.writeText(JSON.stringify(frame, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function openInBuilder() {
    const slots = Object.entries(frame).map(([name, value]) => ({
      ...emptySlot(),
      name,
      type: inferType(value),
    }))
    // Handoff to the Builder: opens in slot_filling mode with these slots.
    writeHandoff(HANDOFF_TO_BUILDER, {
      kind: 'slot_filling',
      state: { slots: slots.length ? slots : [emptySlot()] },
    })
    navigate('/builder')
  }

  const btnCls = `w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg
    text-xs text-slate-400 hover:text-slate-200 bg-app-800 hover:bg-app-700
    border border-app-border transition-colors`

  return (
    <div className="px-3 py-2.5 border-t border-app-border space-y-1.5 flex-shrink-0">
      <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider">
        Task result
      </p>
      <button onClick={copyFrame} className={btnCls}
        title="Copy the data gathered in the dialogue (slot to value) as JSON">
        {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
        {copied ? 'Result copied ✓' : 'Copy result (JSON)'}
      </button>
      <button onClick={openInBuilder} className={btnCls}
        title="Turn this task's frame into an editable schema (infers the value types) and open it in the Frame Builder">
        <Layers size={12} />
        Edit frame in the Builder
      </button>
    </div>
  )
}

/** Monitor side panel: user emotion + active task frame. */
export function FrameSidebar({ frame, fsmState, turns, emotion }) {
  if (!frame) {
    return (
      <div className="w-64 border-l border-app-border bg-app-950/60 flex flex-col flex-shrink-0">
        <EmotionMeter emotion={emotion} />
        <div className="px-4 py-3 border-b border-app-border">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Frame</h2>
        </div>
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-slate-600 text-center">No active task</p>
        </div>
      </div>
    )
  }

  const entries = Object.entries(frame)

  return (
    <div className="w-64 border-l border-app-border bg-app-950/60 flex flex-col flex-shrink-0 overflow-hidden">
      <EmotionMeter emotion={emotion} />
      <div className="px-4 py-3 border-b border-app-border flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Frame</h2>
        <div className="flex items-center gap-2">
          {fsmState && (
            <span className="text-xs text-brand-400 font-mono truncate max-w-[80px]">{fsmState}</span>
          )}
          {turns > 0 && (
            <span className="text-xs text-slate-600">T{turns}</span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {entries.length === 0 ? (
          <p className="text-xs text-slate-600 text-center py-4">Empty frame</p>
        ) : (
          entries.map(([key, value]) => (
            <div key={key} className="bg-app-800 border border-app-border rounded-lg px-3 py-2">
              <div className="flex items-center justify-between gap-1">
                <span className="text-xs font-mono text-slate-400 truncate">{key}</span>
                <span className={`text-xs flex-shrink-0 ${value != null ? 'text-green-400' : 'text-slate-600'}`}>
                  {value != null ? '●' : '○'}
                </span>
              </div>
              {value != null && (
                <p className="text-xs text-slate-300 mt-1 font-mono break-all leading-relaxed">
                  {String(value)}
                </p>
              )}
            </div>
          ))
        )}
      </div>

      <FrameActions frame={frame} />
    </div>
  )
}
