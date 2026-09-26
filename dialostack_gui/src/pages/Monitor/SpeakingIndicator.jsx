/** Transient "speaking"/"transcribing" bubbles for the user and a robot-side speaking indicator. */
import { RobotAvatar, SpeakingBars, UserAvatar } from './ChatBubble'

/** User "Speaking..." bubble - shown while the VAD detects voice (or the GUI
    marks keyboard speech) and disappears when the transcription arrives. */
export function UserSpeakingIndicator({ isActive }) {
  if (!isActive) return null

  return (
    <div className="flex justify-end gap-2 animate-fade-in">
      <div className="flex items-center gap-2.5 px-3.5 py-2 rounded
        bg-app-700 border border-brand-600">
        <span className="font-mono text-[11px] text-slate-300">speaking</span>
        <SpeakingBars />
      </div>
      <UserAvatar />
    </div>
  )
}

/** "Transcribing..." bubble - shown from when the user stops speaking until the
    transcription arrives, so the STT processing gap does not look like the
    message was lost. */
export function UserTranscribingIndicator({ isActive }) {
  if (!isActive) return null

  return (
    <div className="flex justify-end gap-2 animate-fade-in">
      <div className="flex items-center gap-2 px-3.5 py-2 rounded
        bg-app-800 border border-app-border">
        <span className="font-mono text-[11px] text-slate-400">transcribing</span>
        <span className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1 h-1 bg-slate-400 animate-pulse"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </span>
      </div>
      <UserAvatar />
    </div>
  )
}

export function SpeakingIndicator({ isActive }) {
  if (!isActive) return null

  return (
    <div className="flex justify-start gap-2 animate-fade-in">
      <RobotAvatar />
      <div className="flex items-center gap-2.5 px-3.5 py-2 rounded bg-app-900 border border-brand-600">
        <div className="flex items-end gap-0.5 h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-0.5 bg-brand-400 animate-pulse-slow"
              style={{
                height: `${[12, 16, 10][i]}px`,
                animationDelay: `${i * 0.15}s`,
              }}
            />
          ))}
        </div>
        <span className="font-mono text-[11px] text-brand-400">speaking</span>
      </div>
    </div>
  )
}
