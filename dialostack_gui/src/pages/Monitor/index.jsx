/** Dialogue Monitor page: chat timeline, task state, frame sidebar, and the launch drawer. */
import { useEffect, useRef } from 'react'
import { Trash2, X } from 'lucide-react'
import { useActionClient } from '../../hooks/useActionClient'
import { useROS } from '../../contexts/ROSContext'
import { useEngine } from '../../contexts/EngineContext'
import { DIALOG_ACTION, DIALOG_ACTION_TYPE } from '../../lib/ros'
import { UserBubble, RobotBubble, TaskEndBubble, TaskStartBar, SessionSeparator } from './ChatBubble'
import { SpeakingIndicator, UserSpeakingIndicator, UserTranscribingIndicator } from './SpeakingIndicator'
import { FrameSidebar } from './FrameSidebar'
import { LaunchDrawer } from './LaunchDrawer'
import { Composer } from './Composer'
import { TagFilter, DEFAULT_TAGS } from './TagFilter'
import { ExportMenu } from './ExportMenu'
import { ContextBanner, EmptyState, NewTaskButton } from './MonitorChrome'
import { usePersistentState } from '../../hooks/usePersistentState'
import { readHandoff, INJECT_TO_LAUNCH } from '../../lib/frames'
import { STORAGE } from '../../lib/storageKeys'

const BUBBLES = {
  user: UserBubble,
  robot: RobotBubble,
  task_start: TaskStartBar,
  task_end: TaskEndBubble,
}

export function Monitor({ timeline, launchOpen, setLaunchOpen }) {
  const {
    events, isSpeaking, speakingId, userTalking, transcribing, emotion,
    fsmState, currentFrame, taskTurns, taskRunning, clearTimeline, pushLocalUserMessage,
  } = timeline
  const { status: rosStatus } = useROS()
  const { engineState } = useEngine()
  const { sendGoal, cancelGoal, goalStatus } = useActionClient(DIALOG_ACTION, DIALOG_ACTION_TYPE)
  const [tags, setTags] = usePersistentState(STORAGE.monitorTags, DEFAULT_TAGS)

  const bottomRef = useRef(null)
  // Task launched by this GUI: we have the goal and can cancel it.
  const ownActive = goalStatus === 'active'
  // Task in progress, own or from an external app: blocks launching another.
  const isActive = ownActive || taskRunning
  // We only monitor it (launched by another application): we do not offer to cancel it.
  const externalActive = isActive && !ownActive

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, isSpeaking, userTalking, transcribing])

  // If the Builder left a frame to inject ("Use in launch"), open the drawer;
  // it takes care of consuming and clearing it when it opens.
  useEffect(() => {
    if (readHandoff(INJECT_TO_LAUNCH)) setLaunchOpen(true)
  }, [setLaunchOpen])

  const messageCount = events.filter((e) => e.kind === 'user' || e.kind === 'robot').length

  return (
    <div className="flex flex-col h-full">

      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-app-border bg-app-900 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-sm font-semibold text-slate-100">Dialogue Monitor</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {messageCount === 0 ? 'No activity' : `${messageCount} messages`}
            </p>
          </div>
          {isActive && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full
              bg-brand-glow border border-brand-600/40 text-xs text-brand-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
              {externalActive ? 'Active task (external)' : 'Active task'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <ExportMenu events={events} />
          <TagFilter value={tags} onChange={setTags} />
          {events.length > 0 && (
            <button
              onClick={clearTimeline}
              title="Clear conversation"
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300
                px-2.5 py-2 rounded-lg hover:bg-app-700 border border-transparent
                hover:border-app-border transition-all"
            >
              <Trash2 size={13} />
              Clear
            </button>
          )}
          {ownActive && (
            <button
              onClick={cancelGoal}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-900/30
                border border-red-700/50 text-red-400 text-xs font-medium
                hover:bg-red-900/50 transition-colors"
            >
              <X size={13} />
              Cancel task
            </button>
          )}
        </div>
      </div>

      {/* Non-blocking contextual banner */}
      <ContextBanner isActive={isActive} onLaunch={() => setLaunchOpen(true)} />

      {/* Content row: chat + sidebar */}
      <div className="flex flex-1 overflow-hidden">

        {/* Chat column */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 flex flex-col">
            {events.length === 0 && !userTalking && !transcribing ? (
              <EmptyState />
            ) : (
              <>
                {events.map((event) => {
                  if (event.kind === 'session_separator') {
                    return <SessionSeparator key={event.id} timestamp={event.timestamp} />
                  }
                  const Bubble = BUBBLES[event.kind]
                  if (!Bubble) return null
                  return (
                    <Bubble
                      key={event.id}
                      event={event}
                      tags={tags}
                      speaking={event.kind === 'robot' && event.id === speakingId}
                    />
                  )
                })}
                <UserSpeakingIndicator isActive={userTalking} />
                <UserTranscribingIndicator isActive={transcribing && !userTalking} />
                {/* Fallback: the TTS plays without an associated bubble (e.g. test audio) */}
                <SpeakingIndicator isActive={isSpeaking && !speakingId} />
                <div ref={bottomRef} />
              </>
            )}
          </div>

          <NewTaskButton
            isActive={isActive}
            externalActive={externalActive}
            engineRunning={engineState.state === 'running'}
            onLaunch={() => setLaunchOpen(true)}
          />

          {/* Keyboard input */}
          <Composer rosStatus={rosStatus} onLocalMessage={pushLocalUserMessage} />
        </div>

        {/* Frame sidebar */}
        <FrameSidebar frame={currentFrame} fsmState={fsmState} turns={taskTurns} emotion={emotion} />
      </div>

      {/* Launch drawer */}
      <LaunchDrawer
        open={launchOpen}
        onClose={() => setLaunchOpen(false)}
        onSend={sendGoal}
        isActive={isActive}
        rosStatus={rosStatus}
      />
    </div>
  )
}
