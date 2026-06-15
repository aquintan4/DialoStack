/**
 * Pure reducer for the Monitor timeline.
 *
 * All logic (bubbles, barge-in, "transcribing", own/external task detection,
 * metrics) lives here as pure transitions: no `Date.now` and no timers. Time
 * enters through the actions (`now`) and timer firings are actions (`vadDecay`,
 * `transcribeTimeout`) scheduled by the hook. This way it is tested without
 * React or ROS.
 *
 * State conventions:
 *   - Public fields: the ones the UI consumes (events, isSpeaking, ...).
 *   - Fields with `_`: internal bookkeeping (former refs), not exposed.
 */

export const VAD_DECAY_MS = 900       // debounce of the VAD "user talking"
export const TRANSCRIBE_TIMEOUT = 15000  // safety timeout if STT returns nothing

export const initialTimelineState = {
  // public
  events: [],
  isSpeaking: false,
  speakingId: null,
  userTalking: false,
  transcribing: false,
  emotion: null,
  fsmState: null,
  currentFrame: null,
  taskTurns: 0,
  taskRunning: false,
  // internal
  _nextId: 0,
  _wasTalking: false,
  _wasVad: false,
  _vadActive: false,
  _boolActive: false,
  _lastVoiceAt: null,
  _lastUserAt: null,
  _lastRobotId: null,
  _lastGoalId: null,
  _speakStartAt: null,
  _bargeInPending: false,
  _interruptedMarked: null,
  _localEcho: null,        // { text, until }
  _seenGoals: [],
  _endedGoals: [],
  _turns: 0,
}

// ==== PURE HELPERS ====

const lastRobotIndex = (events) => {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].kind === 'robot') return i
  return -1
}

/**
 * Recomputes "user talking" and the "transcribing" transition.
 *
 * userTalking = mic (VAD) OR bool signal (/user_speaking: keyboard / lips).
 * "transcribing" is triggered ONLY by the VAD: only after real mic voice do we
 * expect an STT transcription. The keyboard moves userTalking but does NOT
 * imply STT in progress - that is why typing must not turn on "transcribing".
 */
function talkingPatch(s) {
  const talking = s._vadActive || s._boolActive
  let transcribing = s.transcribing
  if (s._vadActive && !s._wasVad) transcribing = false        // mic voice (re)starts
  else if (!s._vadActive && s._wasVad) transcribing = true    // mic voice ends -> STT
  return { userTalking: talking, _wasTalking: talking, _wasVad: s._vadActive, transcribing }
}

/**
 * If the user speaks while the robot is talking, marks its last bubble as
 * interrupted (with the cut-off time). Returns a patch or null.
 */
function bargeInPatch(s, now) {
  const robotId = s._lastRobotId
  if (!robotId || !s.isSpeaking || s._interruptedMarked === robotId) return null
  const at = s._speakStartAt != null ? now - s._speakStartAt : null
  return {
    _interruptedMarked: robotId,
    _bargeInPending: true,
    events: s.events.map((e) => (e.id === robotId ? { ...e, interrupted: true, interruptedAtMs: at } : e)),
  }
}

const withBargeIn = (s, now) => {
  const patch = bargeInPatch(s, now)
  return patch ? { ...s, ...patch } : s
}

const taskRunning = (seen, ended) => seen.some((g) => !ended.includes(g))

// ==== TRANSITIONS ====

function reduceTranscription(s, { text, now }) {
  // Echo of an already-rendered typed message -> ignore.
  if (s._localEcho && s._localEcho.text === text && now < s._localEcho.until) {
    return { ...s, _localEcho: null }
  }
  const bargeIn = s._bargeInPending || s.isSpeaking
  let st = withBargeIn({ ...s, _bargeInPending: false }, now)
  const id = `e${st._nextId + 1}`
  const transcriptionMs = st._lastVoiceAt != null ? now - st._lastVoiceAt : null
  st = {
    ...st,
    _nextId: st._nextId + 1,
    events: [...st.events, { id, kind: 'user', text, timestamp: now, bargeIn, transcriptionMs }],
    _lastUserAt: now,
    _lastVoiceAt: null,
    _vadActive: false,
    _wasTalking: false,
    _wasVad: false,
    transcribing: false,
  }
  return { ...st, ...talkingPatch(st) }
}

function reduceVad(s, { value, now }) {
  if (value < 0.5) return s
  const base = { ...s, _vadActive: true, _lastVoiceAt: now }
  return withBargeIn({ ...base, ...talkingPatch(base) }, now)
}

function reduceVadDecay(s) {
  const base = { ...s, _vadActive: false }
  return { ...base, ...talkingPatch(base) }
}

function reduceUserSpeaking(s, { value, now }) {
  const base = { ...s, _boolActive: value, _lastVoiceAt: value ? now : s._lastVoiceAt }
  const st = { ...base, ...talkingPatch(base) }
  return value ? withBargeIn(st, now) : st
}

function reduceEmotion(s, { data }) {
  try {
    const parsed = JSON.parse(data)
    if (parsed && typeof parsed.emotion === 'string') {
      return { ...s, emotion: { emotion: parsed.emotion, confidence: Number(parsed.confidence) || 0 } }
    }
  } catch { /* non-JSON payload */ }
  return s
}

function reduceRobotUtterance(s, { text, now }) {
  const id = `e${s._nextId + 1}`
  const processingMs = s._lastUserAt != null ? now - s._lastUserAt : null
  return {
    ...s,
    _nextId: s._nextId + 1,
    _lastRobotId: id,
    events: [...s.events, { id, kind: 'robot', text, timestamp: now, processingMs, speakDurationMs: null, interrupted: false }],
  }
}

function reduceIsSpeaking(s, { value, now }) {
  const speakingId = value ? s._lastRobotId : null
  if (value) {
    return { ...s, isSpeaking: true, speakingId, _speakStartAt: now }
  }
  let events = s.events
  if (s._speakStartAt != null) {
    const idx = lastRobotIndex(events)
    if (idx !== -1) {
      events = events.slice()
      events[idx] = { ...events[idx], speakDurationMs: now - s._speakStartAt }
    }
  }
  return { ...s, isSpeaking: false, speakingId, _speakStartAt: null, events }
}

function reduceFeedback(s, { goalId, fbState, turns, frameJson, now }) {
  let events = s.events
  let nextId = s._nextId
  if (goalId !== s._lastGoalId) {
    nextId += 1
    events = [...events, { id: `e${nextId}`, kind: 'task_start', timestamp: now }]
  }
  const seen = s._seenGoals.includes(goalId) ? s._seenGoals : [...s._seenGoals, goalId]
  let currentFrame = s.currentFrame
  try {
    const parsed = JSON.parse(frameJson)
    if (parsed && typeof parsed === 'object') currentFrame = parsed
  } catch { /* frame incomplete mid-turn */ }
  return {
    ...s,
    events,
    _nextId: nextId,
    _lastGoalId: goalId,
    _seenGoals: seen,
    fsmState: fbState,
    taskTurns: turns,
    _turns: turns,
    currentFrame,
    taskRunning: taskRunning(seen, s._endedGoals),
  }
}

function reduceStatus(s, { items, now }) {
  let events = s.events
  let nextId = s._nextId
  let fsmState = s.fsmState
  const seen = s._seenGoals.slice()
  const ended = s._endedGoals.slice()

  for (const it of items ?? []) {
    const { goalId, status } = it
    if (status < 4) {
      // Live goal (1/2/3): "in progress" even if feedback has not arrived yet.
      if (!ended.includes(goalId) && !seen.includes(goalId)) seen.push(goalId)
      continue
    }
    // Terminal (4/5/6): end bar only for goals we are tracking.
    if (!seen.includes(goalId) || ended.includes(goalId)) continue
    ended.push(goalId)
    nextId += 1
    events = [...events, {
      id: `e${nextId}`,
      kind: 'task_end',
      success: status === 4,
      totalTurns: s._turns,
      reason: status === 5 ? 'cancelled' : status === 6 ? 'aborted by the engine' : '',
      timestamp: now,
    }]
    if (goalId === s._lastGoalId) fsmState = null
  }
  return { ...s, events, _nextId: nextId, _seenGoals: seen, _endedGoals: ended, fsmState, taskRunning: taskRunning(seen, ended) }
}

function reduceLocalUserMessage(s, { text, now }) {
  const bargeIn = s._bargeInPending || s.isSpeaking
  const st = withBargeIn({ ...s, _bargeInPending: false }, now)
  const id = `e${st._nextId + 1}`
  return {
    ...st,
    _nextId: st._nextId + 1,
    transcribing: false,
    _lastVoiceAt: null,
    _lastUserAt: now,
    _localEcho: { text, until: now + 3000 },
    events: [...st.events, { id, kind: 'user', text, timestamp: now, bargeIn }],
  }
}

function reduceClear(s) {
  return {
    ...s,
    events: [],
    speakingId: null,
    fsmState: null,
    currentFrame: null,
    taskTurns: 0,
    transcribing: false,
    _wasTalking: false,
    _wasVad: false,
    _lastVoiceAt: null,
    _lastUserAt: null,
    _lastRobotId: null,
    _lastGoalId: null,
  }
}

const HANDLERS = {
  transcription: reduceTranscription,
  vad: reduceVad,
  vadDecay: reduceVadDecay,
  userSpeaking: reduceUserSpeaking,
  transcribeTimeout: (s) => ({ ...s, transcribing: false, _lastVoiceAt: null }),
  emotion: reduceEmotion,
  robotUtterance: reduceRobotUtterance,
  isSpeaking: reduceIsSpeaking,
  feedback: reduceFeedback,
  status: reduceStatus,
  localUserMessage: reduceLocalUserMessage,
  clear: reduceClear,
}

export function timelineReducer(state, action) {
  const handler = HANDLERS[action.type]
  return handler ? handler(state, action) : state
}
