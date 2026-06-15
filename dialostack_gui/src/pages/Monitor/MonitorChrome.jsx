/** Monitor chrome: context banner, empty-state placeholder, and the floating new-task button. */
import { Info, Plus, SlidersHorizontal } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useEngine } from '../../contexts/EngineContext'

/**
 * Thin, non-blocking banner under the header: invites starting the engine or
 * launching a task without preventing viewing the chat (useful for debugging
 * the transcription with no active task).
 */
export function ContextBanner({ isActive, onLaunch }) {
  const navigate = useNavigate()
  const { engineState } = useEngine()
  if (isActive) return null

  // The criterion is the ENGINE state (the "Engine active" badge), not the ROS connection.
  const engineDown = engineState.state !== 'running'

  return (
    <div className="flex items-center justify-center gap-2 px-6 py-1.5 border-b
      border-app-border/60 bg-app-900/60 flex-shrink-0 text-xs text-slate-600">
      <Info size={12} className="flex-shrink-0" />
      {engineDown ? (
        <>
          The engine is not running.
          <button
            onClick={() => navigate('/config')}
            className="flex items-center gap-1 text-brand-500 hover:text-brand-400 font-medium transition-colors"
          >
            <SlidersHorizontal size={11} />
            Go to Configuration →
          </button>
        </>
      ) : (
        <>
          No active task - the chat keeps showing transcriptions.
          <button
            onClick={onLaunch}
            className="text-brand-500 hover:text-brand-400 font-medium transition-colors"
          >
            Launch task →
          </button>
        </>
      )}
    </div>
  )
}

/** Empty-chat placeholder - informative, without blocking the composer or the indicators. */
export function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-8 opacity-80">
      <div className="relative">
        <div className="absolute inset-0 rounded-full bg-brand-500/15 blur-2xl scale-150" />
        <img src="/robot-avatar.png" alt="" className="relative w-14 h-14 opacity-80" />
      </div>
      <p className="text-xs text-slate-600 max-w-[260px] leading-relaxed">
        No activity yet - talk to the microphone, type below
        or launch a task. Everything that goes through the topics will appear here.
      </p>
    </div>
  )
}

/**
 * Floating primary action above the message bar. Disabled (subtle gray) if the
 * engine is not running or if there is already a task in progress.
 */
export function NewTaskButton({ isActive, externalActive, engineRunning, onLaunch }) {
  const disabled = isActive || !engineRunning
  const title = externalActive
    ? 'There is a task in progress launched from another application'
    : isActive
      ? 'There is already a task in progress - cancel it to launch another'
      : engineRunning
        ? 'Launch a new task'
        : 'The engine is not running - start it first'

  return (
    <div className="relative flex-shrink-0">
      <div className="absolute -top-14 inset-x-0 flex justify-center pointer-events-none">
        <button
          onClick={() => !disabled && onLaunch()}
          disabled={disabled}
          title={title}
          className={`pointer-events-auto flex items-center gap-2 px-5 py-2.5 rounded-full
            text-sm font-semibold transition-all shadow-xl shadow-black/40 ${
              disabled
                ? 'bg-app-800/90 border border-app-border text-slate-500 cursor-not-allowed'
                : `bg-gradient-to-r from-brand-600 to-blue-600 hover:from-brand-500
                   hover:to-blue-500 text-white glow-blue`
            }`}
        >
          {isActive ? (
            <>
              <span className="w-2 h-2 rounded-full bg-brand-400 animate-pulse" />
              Task running…
            </>
          ) : (
            <>
              <Plus size={15} />
              New task
            </>
          )}
        </button>
      </div>
    </div>
  )
}
