/** Monitor chrome: context banner, empty-state placeholder, and the floating task button (new / stop). */
import { Info, Loader2, Plus, SlidersHorizontal, Square } from 'lucide-react'
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
    <div className="flex items-center gap-2 px-6 py-1.5 border-b
      border-app-border bg-app-950 flex-shrink-0 text-xs text-slate-500">
      <Info size={12} className="flex-shrink-0" />
      {engineDown ? (
        <>
          The engine is not running.
          <button
            onClick={() => navigate('/config')}
            className="flex items-center gap-1 text-slate-300 hover:text-slate-100 underline underline-offset-2 decoration-slate-600 transition-colors"
          >
            <SlidersHorizontal size={11} />
            Open Configuration
          </button>
        </>
      ) : (
        <>
          No active task - the chat keeps showing transcriptions.
          <button
            onClick={onLaunch}
            className="text-slate-300 hover:text-slate-100 underline underline-offset-2 decoration-slate-600 transition-colors"
          >
            Launch task
          </button>
        </>
      )}
    </div>
  )
}

/** Empty-chat placeholder - informative, without blocking the composer or the indicators. */
export function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-1.5 text-center p-8">
      <p className="text-sm text-slate-500">No activity</p>
      <p className="text-xs text-slate-600 max-w-[300px] leading-relaxed">
        Speak to the microphone, type below or launch a task.
        Traffic on the dialogue topics is shown here.
      </p>
    </div>
  )
}

/**
 * Floating primary action above the message bar. One button, one place:
 * - idle: "New task" (disabled if the engine is not running)
 * - own task running: "Stop task"; after the click it shows "Stopping" until
 *   the engine reports the goal as finished
 * - task launched by another application: disabled, monitor only
 */
export function TaskButton({ isActive, externalActive, cancelling, engineRunning, onLaunch, onStop }) {
  const ownActive = isActive && !externalActive

  let label, icon, onClick, disabled, title, tone
  if (ownActive && cancelling) {
    label = 'Stopping'
    icon = <Loader2 size={14} className="animate-spin" />
    disabled = true
    title = 'Waiting for the engine to confirm the task was cancelled'
    tone = 'bg-app-900 border-red-900/70 text-red-400/80 cursor-wait'
  } else if (ownActive) {
    label = 'Stop task'
    icon = <Square size={12} className="fill-current" />
    onClick = onStop
    title = 'Cancel the running task: the robot stops speaking and listening at once'
    tone = 'bg-app-900 border-red-800 text-red-400 hover:bg-red-950/60 hover:text-red-300'
  } else if (externalActive) {
    label = 'Task running (external)'
    icon = <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
    disabled = true
    title = 'The running task was launched from another application'
    tone = 'bg-app-900 border-app-border text-slate-500 cursor-not-allowed'
  } else {
    label = 'New task'
    icon = <Plus size={15} />
    onClick = onLaunch
    disabled = !engineRunning
    title = engineRunning ? 'Launch a new task' : 'The engine is not running - start it first'
    tone = disabled
      ? 'bg-app-900 border-app-border text-slate-500 cursor-not-allowed'
      : 'bg-brand-600 border-brand-500 hover:bg-brand-500 text-white'
  }

  return (
    <div className="relative flex-shrink-0">
      <div className="absolute -top-14 inset-x-0 flex justify-center pointer-events-none">
        <button
          onClick={() => !disabled && onClick?.()}
          disabled={disabled}
          title={title}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-2 rounded border
            whitespace-nowrap text-[13px] font-medium transition-colors shadow-md shadow-black/25 ${tone}`}
        >
          {icon}
          {label}
        </button>
      </div>
    </div>
  )
}
