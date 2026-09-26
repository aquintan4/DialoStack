/** Chat bubbles and timeline separators for the Dialogue Monitor (user, robot, task start/end, session). */
import { memo } from 'react'
import { Bot, Trash2, User, VolumeX, Zap } from 'lucide-react'
import { formatMs, formatTime } from '../../lib/formatters'

/** Monospace metric chip under a bubble (e.g. "llm 0.8s"). */
function Metric({ label, value, title, tone = 'text-slate-500' }) {
  return (
    <span className={`font-mono text-[11px] ${tone}`} title={title}>
      <span className="text-slate-600">{label}</span> {value}
    </span>
  )
}

/** Hover-revealed per-bubble controls: toggle "noise" and delete. */
function BubbleActions({ event, onDelete, onToggleNoise }) {
  if (!onDelete && !onToggleNoise) return null
  return (
    <div className="self-center flex items-center gap-0.5 opacity-0 group-hover:opacity-100
      focus-within:opacity-100 transition-opacity flex-shrink-0">
      {onToggleNoise && (
        <button onClick={() => onToggleNoise(event.id)}
          title={event.noise ? 'Unmark as noise' : 'Mark as noise'}
          className={`p-1 rounded hover:bg-app-700 transition-colors ${
            event.noise ? 'text-amber-400' : 'text-slate-600 hover:text-amber-400'}`}>
          <VolumeX size={13} />
        </button>
      )}
      {onDelete && (
        <button onClick={() => onDelete(event.id)}
          title="Delete bubble"
          className="p-1 rounded text-slate-600 hover:text-red-400 hover:bg-app-700 transition-colors">
          <Trash2 size={13} />
        </button>
      )}
    </div>
  )
}

/** Animated equalizer bars - used in the bubble that is currently speaking. */
export function SpeakingBars() {
  return (
    <span className="flex items-end gap-0.5 h-3.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-0.5 bg-brand-400 animate-pulse-slow"
          style={{
            height: `${[10, 14, 8][i]}px`,
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </span>
  )
}

export function RobotAvatar() {
  return (
    <div className="w-7 h-7 rounded bg-app-800 border border-app-border
      flex items-center justify-center flex-shrink-0 mt-0.5">
      <Bot size={14} className="text-brand-400" />
    </div>
  )
}

export function UserAvatar() {
  return (
    <div className="w-7 h-7 rounded bg-app-800 border border-app-border
      flex items-center justify-center flex-shrink-0 mt-0.5">
      <User size={13} className="text-slate-400" />
    </div>
  )
}

export const UserBubble = memo(function UserBubble({ event, tags, onDelete, onToggleNoise }) {
  const show = (k) => tags?.[k] !== false   // no config: everything visible
  const noise = event.noise
  const showBarge = !noise && show('interruptions') && event.bargeIn
  const showTime = !noise && show('time')
  const transcriptionLabel = !noise && show('transcription') ? formatMs(event.transcriptionMs) : null

  const bubbleCls = noise
    ? 'bg-app-800/40 border border-app-border/60'
    : event.bargeIn
      ? 'bg-red-950/40 border border-red-800/70'
      : 'bg-app-700 border border-app-500/60'

  return (
    <div className={`group flex justify-end gap-2 animate-slide-up ${
      noise ? 'opacity-40 hover:opacity-80 transition-opacity' : ''}`}>
      <BubbleActions event={event} onDelete={onDelete} onToggleNoise={onToggleNoise} />
      <div className="max-w-[70%] space-y-1">
        <div className={`relative px-3.5 py-2.5 rounded ${bubbleCls}`}>
          {showBarge && (
            <div className="flex items-center gap-1 mb-1.5">
              <Zap size={11} className="text-red-400" />
              <span className="text-xs text-red-400 font-medium">Barge-in</span>
            </div>
          )}
          <p className={`leading-relaxed break-words whitespace-pre-wrap ${
            noise ? 'flex items-center gap-1.5 text-xs text-slate-400' : 'text-sm text-slate-100'}`}>
            {noise && <VolumeX size={11} className="text-slate-500 flex-shrink-0" />}
            {event.text}
          </p>
        </div>
        {(showTime || transcriptionLabel) && (
          <div className="flex items-center justify-end gap-3 pr-0.5">
            {/* microphone transcription: analogous to the robot's inference bolt */}
            {transcriptionLabel && (
              <Metric label="stt" value={transcriptionLabel}
                title="Transcription: from when you stopped speaking until the text appeared" />
            )}
            {showTime && <span className="font-mono text-[11px] text-slate-600">{formatTime(event.timestamp)}</span>}
          </div>
        )}
      </div>
      <UserAvatar />
    </div>
  )
})

export const RobotBubble = memo(function RobotBubble({ event, speaking = false, tags, onDelete, onToggleNoise }) {
  const show = (k) => tags?.[k] !== false   // no config: everything visible
  const noise = event.noise
  const processingLabel = !noise && show('inference') ? formatMs(event.processingMs) : null
  const speakLabel = !noise && show('speech') ? formatMs(event.speakDurationMs) : null
  const interruptedAtLabel = formatMs(event.interruptedAtMs)
  const showInterrupted = !noise && show('interruptions') && event.interrupted
  const showCutOff = !noise && show('speech') && event.interrupted && interruptedAtLabel
  const showTime = !noise && show('time')
  const showMetaRow =
    showTime || processingLabel || (speakLabel && !speaking) || showCutOff || speaking

  const bubbleCls = noise
    ? 'bg-app-800/40 border-app-border/60'
    : event.interrupted
      ? 'bg-red-900/20 border-red-700/40'
      : speaking
        ? 'bg-app-900 border-brand-600'
        : 'bg-app-900 border-app-border'

  return (
    <div className={`group flex justify-start gap-2 animate-slide-up ${
      noise ? 'opacity-40 hover:opacity-80 transition-opacity' : ''}`}>
      <RobotAvatar />
      <div className="max-w-[70%] space-y-1">
        <div className={`px-3.5 py-2.5 rounded border transition-colors ${bubbleCls}`}>
          {showInterrupted && (
            <div className="flex items-center gap-1 mb-1.5">
              <Zap size={11} className="text-red-400" />
              <span className="text-xs text-red-400 font-medium">
                Interrupted{interruptedAtLabel && ` · at ${interruptedAtLabel}`} - unfinished message
              </span>
            </div>
          )}
          <p className={`leading-relaxed break-words whitespace-pre-wrap ${
            noise ? 'flex items-center gap-1.5 text-xs text-slate-400'
                  : `text-sm ${event.interrupted ? 'text-slate-300' : 'text-slate-200'}`}`}>
            {noise && <VolumeX size={11} className="text-slate-500 flex-shrink-0" />}
            {event.text}
          </p>
        </div>
        {showMetaRow && (
          <div className="flex items-center gap-3 pl-0.5">
            {showTime && <span className="font-mono text-[11px] text-slate-600">{formatTime(event.timestamp)}</span>}
            {/* inference bolt and speech speaker coexist: both are valuable metrics */}
            {processingLabel && (
              <Metric label="llm" value={processingLabel}
                title="Inference: from the user's transcription until the response" />
            )}
            {speakLabel && !speaking && !event.interrupted && (
              <Metric label="tts" value={speakLabel} title="Speech duration" />
            )}
            {showCutOff && (
              <Metric label="tts" value={`${interruptedAtLabel} (cut off)`} tone="text-red-400/80"
                title="Spoke for this long before being interrupted" />
            )}
            {speaking && (
              <span className="flex items-center gap-1.5 font-mono text-[11px] text-brand-400">
                <SpeakingBars />
                speaking
              </span>
            )}
          </div>
        )}
      </div>
      <BubbleActions event={event} onDelete={onDelete} onToggleNoise={onToggleNoise} />
    </div>
  )
})

/** Plain rule with a monospace label - shared by all timeline separators. */
function Separator({ label, time, tone = 'text-slate-500', line = 'bg-app-border' }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className={`flex-1 h-px ${line}`} />
      <span className={`flex items-center gap-2 font-mono text-[11px] flex-shrink-0 ${tone}`}>
        {label}
        {time && <span className="text-slate-600">{formatTime(time)}</span>}
      </span>
      <div className={`flex-1 h-px ${line}`} />
    </div>
  )
}

/** Separator bar for task start. */
export function TaskStartBar({ event }) {
  return <Separator label="task started" time={event.timestamp} tone="text-slate-400" line="bg-app-500" />
}

/** Separator bar for task end with the final status. */
export function TaskEndBubble({ event }) {
  const cancelled = !event.success && /cancel/i.test(event.reason || '')
  const cfg = event.success
    ? { tone: 'text-green-400', line: 'bg-green-800/60', label: `task completed · ${event.totalTurns} turns` }
    : cancelled
      ? { tone: 'text-yellow-400', line: 'bg-yellow-800/60', label: `task cancelled · ${event.totalTurns} turns` }
      : { tone: 'text-red-400', line: 'bg-red-800/60', label: `task failed · ${event.reason || 'no detail'}` }
  return <Separator label={cfg.label} time={event.timestamp} tone={cfg.tone} line={cfg.line} />
}

export function SessionSeparator({ timestamp }) {
  return <Separator label="new session" time={timestamp} tone="text-slate-600" />
}
