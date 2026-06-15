import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useTopic } from './useTopic'
import { TOPICS } from '../lib/ros'
import {
  timelineReducer, initialTimelineState, VAD_DECAY_MS, TRANSCRIBE_TIMEOUT,
} from '../lib/timeline/reducer'

/**
 * Dialogue timeline: subscribes to the stack topics and translates them into
 * reducer actions (`lib/timeline/reducer.js`). Only the IO and timer plumbing
 * lives here; all the logic (barge-in, transcribing, task detection, metrics)
 * is pure and testable in the reducer.
 */
export function useDialogTimeline() {
  const [state, dispatch] = useReducer(timelineReducer, initialTimelineState)
  const vadDecayRef = useRef(null)

  useTopic(TOPICS.transcription.name, TOPICS.transcription.type, (msg) => {
    clearTimeout(vadDecayRef.current)
    dispatch({ type: 'transcription', text: msg.data, now: Date.now() })
  })

  // /user_vad: the decay (debounce) is scheduled here and re-armed on every
  // voice pulse; its firing is a reducer action.
  useTopic(TOPICS.userVad.name, TOPICS.userVad.type, (msg) => {
    if (msg.data < 0.5) return
    dispatch({ type: 'vad', value: msg.data, now: Date.now() })
    clearTimeout(vadDecayRef.current)
    vadDecayRef.current = setTimeout(() => dispatch({ type: 'vadDecay' }), VAD_DECAY_MS)
  })

  useTopic(TOPICS.userSpeaking.name, TOPICS.userSpeaking.type, (msg) =>
    dispatch({ type: 'userSpeaking', value: msg.data, now: Date.now() }))

  useTopic(TOPICS.userEmotion.name, TOPICS.userEmotion.type, (msg) =>
    dispatch({ type: 'emotion', data: msg.data }))

  useTopic(TOPICS.robotUtterance.name, TOPICS.robotUtterance.type, (msg) =>
    dispatch({ type: 'robotUtterance', text: msg.data, now: Date.now() }))

  useTopic(TOPICS.isSpeaking.name, TOPICS.isSpeaking.type, (msg) =>
    dispatch({ type: 'isSpeaking', value: msg.data, now: Date.now() }))

  useTopic(TOPICS.dialogFeedback.name, TOPICS.dialogFeedback.type, (msg) =>
    dispatch({
      type: 'feedback',
      goalId: JSON.stringify(msg.goal_id?.uuid ?? msg.goal_id),
      fbState: msg.feedback?.state,
      turns: msg.feedback?.turns,
      frameJson: msg.feedback?.current_frame_json,
      now: Date.now(),
    }))

  useTopic(TOPICS.dialogStatus.name, TOPICS.dialogStatus.type, (msg) =>
    dispatch({
      type: 'status',
      now: Date.now(),
      items: (msg.status_list ?? []).map((s) => ({
        status: s.status,
        goalId: JSON.stringify(s.goal_info?.goal_id?.uuid),
      })),
    }))

  // "transcribing" safety cap: armed on entering the state and cancelled on
  // leaving it - governed by the flag, not by scattered calls.
  useEffect(() => {
    if (!state.transcribing) return
    const t = setTimeout(() => dispatch({ type: 'transcribeTimeout' }), TRANSCRIBE_TIMEOUT)
    return () => clearTimeout(t)
  }, [state.transcribing])

  useEffect(() => () => clearTimeout(vadDecayRef.current), [])

  const pushLocalUserMessage = useCallback(
    (text) => dispatch({ type: 'localUserMessage', text, now: Date.now() }), [])
  const clearTimeline = useCallback(() => dispatch({ type: 'clear' }), [])

  const {
    events, isSpeaking, speakingId, userTalking, transcribing, emotion,
    fsmState, currentFrame, taskTurns, taskRunning,
  } = state

  return {
    events, isSpeaking, speakingId, userTalking, transcribing, emotion,
    fsmState, currentFrame, taskTurns, taskRunning, clearTimeline, pushLocalUserMessage,
  }
}
