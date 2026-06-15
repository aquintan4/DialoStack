/** Chat bubbles and timeline separators for the Dialogue Monitor (user, robot, task start/end, session). */
import { memo } from 'react'
import { User, Zap } from 'lucide-react'

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('es-ES', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function formatMs(ms) {
  if (ms == null) return null
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

/** Animated equalizer bars - used in the bubble that is currently speaking. */
export function SpeakingBars() {
  return (
    <span className="flex items-end gap-0.5 h-3.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-0.5 bg-brand-400 rounded-full animate-pulse-slow"
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
    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-blue-600
      flex items-center justify-center flex-shrink-0 mt-0.5 shadow-md shadow-brand-600/20 p-[3px]">
      <img src="/robot-avatar.png" alt="" className="w-full h-full object-contain" />
    </div>
  )
}

export function UserAvatar() {
  return (
    <div className="w-7 h-7 rounded-lg bg-app-700 border border-app-border
      flex items-center justify-center flex-shrink-0 mt-0.5">
      <User size={13} className="text-slate-400" />
    </div>
  )
}

export const UserBubble = memo(function UserBubble({ event, tags }) {
  const show = (k) => tags?.[k] !== false   // no config: everything visible
  const showBarge = show('interruptions') && event.bargeIn
  const showTime = show('time')
  const transcriptionLabel = show('transcription') ? formatMs(event.transcriptionMs) : null

  return (
    <div className="flex justify-end gap-2 animate-slide-up">
      <div className="max-w-[70%] space-y-1">
        <div className={`relative px-4 py-3 rounded-2xl rounded-tr-sm
          ${event.bargeIn
            ? 'bg-red-900/40 border border-red-500/50'
            : 'bg-gradient-to-br from-brand-600 to-brand-700 border border-brand-500/40'}`}>
          {showBarge && (
            <div className="flex items-center gap-1 mb-1.5">
              <Zap size={11} className="text-red-400" />
              <span className="text-xs text-red-400 font-medium">Barge-in</span>
            </div>
          )}
          <p className="text-sm text-slate-50 leading-relaxed break-words whitespace-pre-wrap">{event.text}</p>
        </div>
        {(showTime || transcriptionLabel) && (
          <div className="flex items-center justify-end gap-2 pr-1">
            {/* microphone transcription: analogous to the robot's inference bolt */}
            {transcriptionLabel && (
              <span className="text-xs text-slate-500 bg-app-800 border border-app-border px-1.5 py-0.5 rounded"
                title="Transcription: from when you stopped speaking until the text appeared">
                🎙️ {transcriptionLabel}
              </span>
            )}
            {showTime && <span className="text-xs text-slate-600">{formatTime(event.timestamp)}</span>}
          </div>
        )}
      </div>
      <UserAvatar />
    </div>
  )
})

export const RobotBubble = memo(function RobotBubble({ event, speaking = false, tags }) {
  const show = (k) => tags?.[k] !== false   // no config: everything visible
  const processingLabel = show('inference') ? formatMs(event.processingMs) : null
  const speakLabel = show('speech') ? formatMs(event.speakDurationMs) : null
  const interruptedAtLabel = formatMs(event.interruptedAtMs)
  const showInterrupted = show('interruptions') && event.interrupted
  const showCutOff = show('speech') && event.interrupted && interruptedAtLabel
  const showTime = show('time')
  const showMetaRow =
    showTime || processingLabel || (speakLabel && !speaking) || showCutOff || speaking

  const bubbleCls = event.interrupted
    ? 'bg-red-900/20 border-red-700/40'
    : speaking
      ? 'bg-app-800 border-brand-500/50 shadow-[0_0_16px_rgba(15,165,202,0.18)]'
      : 'bg-app-800 border-app-border'

  return (
    <div className="flex justify-start gap-2 animate-slide-up">
      <RobotAvatar />
      <div className="max-w-[70%] space-y-1">
        <div className={`px-4 py-3 rounded-2xl rounded-tl-sm border transition-all duration-300 ${bubbleCls}`}>
          {showInterrupted && (
            <div className="flex items-center gap-1 mb-1.5">
              <Zap size={11} className="text-red-400" />
              <span className="text-xs text-red-400 font-medium">
                Interrupted{interruptedAtLabel && ` · at ${interruptedAtLabel}`} - unfinished message
              </span>
            </div>
          )}
          <p className={`text-sm leading-relaxed break-words whitespace-pre-wrap ${event.interrupted ? 'text-slate-300' : 'text-slate-200'}`}>
            {event.text}
          </p>
        </div>
        {showMetaRow && (
          <div className="flex items-center gap-2 pl-1">
            {showTime && <span className="text-xs text-slate-600">{formatTime(event.timestamp)}</span>}
            {/* inference bolt and speech speaker coexist: both are valuable metrics */}
            {processingLabel && (
              <span className="text-xs text-slate-500 bg-app-800 border border-app-border px-1.5 py-0.5 rounded"
                title="Inference: from the user's transcription until the response">
                ⚡ {processingLabel}
              </span>
            )}
            {speakLabel && !speaking && !event.interrupted && (
              <span className="text-xs text-slate-500 bg-app-800 border border-app-border px-1.5 py-0.5 rounded"
                title="Speech duration">
                🔊 {speakLabel}
              </span>
            )}
            {showCutOff && (
              <span className="text-xs text-red-400/80 bg-red-900/20 border border-red-700/40 px-1.5 py-0.5 rounded"
                title="Spoke for this long before being interrupted">
                🔊 {interruptedAtLabel} (cut off)
              </span>
            )}
            {speaking && (
              <span className="flex items-center gap-1.5 text-xs text-brand-400 font-medium animate-fade-in">
                <SpeakingBars />
                Speaking…
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
})

/** Separator bar for task start. */
export function TaskStartBar({ event }) {
  return (
    <div className="flex items-center gap-3 py-2 animate-fade-in">
      <div className="flex-1 h-px bg-brand-600/40" />
      <span className="flex items-center gap-2 px-3 py-1 rounded-full border border-brand-600/40
        bg-brand-glow text-xs font-medium text-brand-400 flex-shrink-0">
        ▶ Task started
        <span className="text-slate-600">{formatTime(event.timestamp)}</span>
      </span>
      <div className="flex-1 h-px bg-brand-600/40" />
    </div>
  )
}

/** Separator bar for task end with the final status. */
export function TaskEndBubble({ event }) {
  const cancelled = !event.success && /cancel/i.test(event.reason || '')
  const cfg = event.success
    ? { line: 'bg-green-700/40', pill: 'bg-green-900/30 border-green-700/50 text-green-400',
        label: `✓ Task completed · ${event.totalTurns} turns` }
    : cancelled
      ? { line: 'bg-yellow-700/40', pill: 'bg-yellow-900/30 border-yellow-700/50 text-yellow-400',
          label: `⊘ Task cancelled · ${event.totalTurns} turns` }
      : { line: 'bg-red-700/40', pill: 'bg-red-900/30 border-red-700/50 text-red-400',
          label: `✗ Task failed · ${event.reason || 'no detail'}` }

  return (
    <div className="flex items-center gap-3 py-2 animate-fade-in">
      <div className={`flex-1 h-px ${cfg.line}`} />
      <span className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium flex-shrink-0 ${cfg.pill}`}>
        {cfg.label}
        <span className="text-slate-600">{formatTime(event.timestamp)}</span>
      </span>
      <div className={`flex-1 h-px ${cfg.line}`} />
    </div>
  )
}

export function SessionSeparator({ timestamp }) {
  return (
    <div className="flex items-center gap-3 py-3 animate-fade-in">
      <div className="flex-1 h-px bg-app-border" />
      <span className="text-xs text-slate-600 flex-shrink-0 font-medium">
        New session · {formatTime(timestamp)}
      </span>
      <div className="flex-1 h-px bg-app-border" />
    </div>
  )
}
