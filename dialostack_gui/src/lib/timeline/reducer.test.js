/** Tests for the Monitor timeline reducer: transcription, transcribing state, barge-in and task tracking. */
import { describe, it, expect } from 'vitest'
import { timelineReducer as r, initialTimelineState } from './reducer'

const run = (actions, state = initialTimelineState) => actions.reduce(r, state)
const kinds = (s) => s.events.map((e) => e.kind)
const users = (s) => s.events.filter((e) => e.kind === 'user')
const robots = (s) => s.events.filter((e) => e.kind === 'robot')

describe('transcription and latency', () => {
  it('adds a user bubble and measures latency since the last voice', () => {
    const s = run([
      { type: 'vad', value: 0.9, now: 1000 },
      { type: 'transcription', text: 'hola', now: 1500 },
    ])
    expect(users(s)).toHaveLength(1)
    expect(users(s)[0]).toMatchObject({ text: 'hola', transcriptionMs: 500, bargeIn: false })
  })

  it('ignores the echo of an already-rendered typed message', () => {
    const s = run([
      { type: 'localUserMessage', text: 'pedido', now: 1000 },
      { type: 'transcription', text: 'pedido', now: 1200 }, // echo within the window
    ])
    expect(users(s)).toHaveLength(1) // not duplicated
  })
})

describe('"transcribing" state', () => {
  it('turns on when speech stops and turns off when the transcription arrives', () => {
    let s = run([{ type: 'vad', value: 0.9, now: 1000 }])
    expect(s.userTalking).toBe(true)
    expect(s.transcribing).toBe(false)

    s = r(s, { type: 'vadDecay' })
    expect(s.userTalking).toBe(false)
    expect(s.transcribing).toBe(true)

    s = r(s, { type: 'transcription', text: 'x', now: 2000 })
    expect(s.transcribing).toBe(false)
  })

  it('FULL VOICE FLOW: vad -> decay -> transcription creates the bubble', () => {
    let s = run([{ type: 'vad', value: 0.9, now: 1000 }])
    expect(s.userTalking).toBe(true)
    expect(s.transcribing).toBe(false)
    // the user stops talking -> the VAD timer decays
    s = r(s, { type: 'vadDecay' })
    expect(s.userTalking).toBe(false)
    expect(s.transcribing).toBe(true)
    // the STT transcription arrives (seconds later)
    s = r(s, { type: 'transcription', text: 'hola robot', now: 3000 })
    expect(s.events.filter((e) => e.kind === 'user')).toHaveLength(1)
    expect(s.events[0].text).toBe('hola robot')
    expect(s.transcribing).toBe(false)
  })

  it('the keyboard signal (/user_speaking) does NOT turn on "transcribing"', () => {
    // The Composer publishes user_speaking=true while there is text and false on send.
    // That edge must not trigger "transcribing": there is no STT from the keyboard.
    let s = run([{ type: 'userSpeaking', value: true, now: 1000 }])
    expect(s.userTalking).toBe(true)
    s = r(s, { type: 'userSpeaking', value: false, now: 1100 })
    expect(s.transcribing).toBe(false)
  })

  it('the safety timeout turns off "transcribing" and forgets the voice', () => {
    let s = run([{ type: 'vad', value: 0.9, now: 1000 }, { type: 'vadDecay' }])
    expect(s.transcribing).toBe(true)
    s = r(s, { type: 'transcribeTimeout' })
    expect(s.transcribing).toBe(false)
    expect(s._lastVoiceAt).toBe(null)
  })
})

describe('barge-in', () => {
  it('the backend /barge_in event marks the robot bubble and tags the next user turn', () => {
    const s = run([
      { type: 'robotUtterance', text: 'respuesta larga', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'bargeIn', spokenMs: 990, now: 2000 },   // the backend confirms the cut-off
      { type: 'transcription', text: 'para', now: 2500 },
    ])
    expect(robots(s)[0].interrupted).toBe(true)
    expect(robots(s)[0].interruptedAtMs).toBe(990)     // authoritative, reported by the robot
    expect(users(s)[0].bargeIn).toBe(true)
  })

  it('does NOT infer barge-in from VAD while the robot is speaking (no backend event)', () => {
    // This is the spurious case the old timing-based logic produced on ordinary
    // turns: VAD pulses + isSpeaking still true must NOT count as a barge-in.
    const s = run([
      { type: 'robotUtterance', text: 'r', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'vad', value: 0.9, now: 2000 },
      { type: 'transcription', text: 'hola', now: 2200 },
    ])
    expect(robots(s)[0].interrupted).toBe(false)
    expect(users(s)[0].bargeIn).toBe(false)
  })

  it('with no TTS playing there is no barge-in', () => {
    const s = run([
      { type: 'robotUtterance', text: 'r', now: 1000 },
      { type: 'vad', value: 0.9, now: 2000 },
      { type: 'transcription', text: 'hola', now: 2200 },
    ])
    expect(robots(s)[0].interrupted).toBe(false)
    expect(users(s)[0].bargeIn).toBe(false)
  })

  it('is robust to the /barge_in event arriving after isSpeaking already went false', () => {
    // Topics have no cross-ordering guarantee: the GUI may see speech end first.
    const s = run([
      { type: 'robotUtterance', text: 'r', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'isSpeaking', value: false, now: 1900 },
      { type: 'bargeIn', spokenMs: 880, now: 1950 },
      { type: 'transcription', text: 'para', now: 2200 },
    ])
    expect(robots(s)[0].interrupted).toBe(true)
    expect(robots(s)[0].interruptedAtMs).toBe(880)
    expect(users(s)[0].bargeIn).toBe(true)
  })

  it('a typed (keyboard) interruption is tagged through the same generic path', () => {
    // The Composer publishes /user_speaking; the backend turns the real cut-off
    // into /barge_in, so a typed interruption is marked exactly like any other
    // source (vision, or a future modality). The mechanism is source-agnostic.
    const s = run([
      { type: 'robotUtterance', text: 'explicación larga', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'bargeIn', spokenMs: 700, now: 1700 },           // backend confirms the cut
      { type: 'localUserMessage', text: 'espera', now: 1900 }, // optimistic typed bubble
    ])
    expect(robots(s)[0].interrupted).toBe(true)
    expect(users(s)[0].bargeIn).toBe(true)
  })

  it('a barge-in not followed by a transcription does not leak onto a later turn', () => {
    const s = run([
      { type: 'robotUtterance', text: 'r1', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'bargeIn', spokenMs: 500, now: 1500 },     // cut, but the user said nothing
      { type: 'isSpeaking', value: false, now: 1510 },
      { type: 'robotUtterance', text: 'r2', now: 3000 }, // the robot moves on
      { type: 'transcription', text: 'hola', now: 4000 },// ordinary reply, not a barge-in
    ])
    expect(robots(s)[0].interrupted).toBe(true)          // r1 really was cut
    expect(robots(s)[1].interrupted).toBe(false)
    expect(users(s)[0].bargeIn).toBe(false)
  })
})

describe('robot speech', () => {
  it('on TTS end records the duration in the robot last bubble', () => {
    const s = run([
      { type: 'robotUtterance', text: 'r', now: 1000 },
      { type: 'isSpeaking', value: true, now: 1010 },
      { type: 'isSpeaking', value: false, now: 3010 },
    ])
    expect(robots(s)[0].speakDurationMs).toBe(2000)
    expect(s.isSpeaking).toBe(false)
    expect(s.speakingId).toBe(null)
  })
})

describe('task tracking (own and external)', () => {
  it('feedback from a new goal opens a start bar and marks the task as running', () => {
    const s = run([
      { type: 'feedback', goalId: 'g1', fbState: 'collecting', turns: 1, frameJson: '{}', now: 1000 },
    ])
    expect(kinds(s)).toContain('task_start')
    expect(s.taskRunning).toBe(true)
    expect(s.fsmState).toBe('collecting')
  })

  it('detects an external task by the "executing" status without waiting for feedback', () => {
    const s = run([
      { type: 'status', items: [{ goalId: 'gx', status: 2 }], now: 1000 },
    ])
    expect(s.taskRunning).toBe(true)
    expect(kinds(s)).not.toContain('task_start') // the bar arrives with the feedback
  })

  it('the terminal state of a tracked goal closes the task', () => {
    const s = run([
      { type: 'status', items: [{ goalId: 'gx', status: 2 }], now: 1000 },
      { type: 'status', items: [{ goalId: 'gx', status: 4 }], now: 2000 },
    ])
    expect(s.taskRunning).toBe(false)
    const end = s.events.find((e) => e.kind === 'task_end')
    expect(end).toMatchObject({ success: true })
  })

  it('does not draw a ghost bar for a goal that ended before being tracked', () => {
    const s = run([
      { type: 'status', items: [{ goalId: 'viejo', status: 4 }], now: 1000 },
    ])
    expect(kinds(s)).not.toContain('task_end')
    expect(s.taskRunning).toBe(false)
  })
})

describe('task ownership (own vs external)', () => {
  it('claims the next goal as own after a GUI launch (markOwnLaunch)', () => {
    const s = run([
      { type: 'ownLaunch' },
      { type: 'feedback', goalId: 'g1', fbState: 'collecting', turns: 1, frameJson: '{}', now: 1000 },
    ])
    expect(s.ownGoalId).toBe('g1')
    expect(s.activeGoalId).toBe('g1')
    expect(s.taskRunning).toBe(true)
  })

  it('a goal seen without a launch is external (activeGoalId set, ownGoalId null)', () => {
    const s = run([
      { type: 'status', items: [{ goalId: 'gx', status: 2 }], now: 1000 },
    ])
    expect(s.activeGoalId).toBe('gx')
    expect(s.ownGoalId).toBe(null)
  })

  it('ownership survives a clear and activeGoalId drops when the goal ends', () => {
    let s = run([
      { type: 'ownLaunch' },
      { type: 'status', items: [{ goalId: 'g1', status: 2 }], now: 1000 },
    ])
    expect(s.ownGoalId).toBe('g1')
    s = r(s, { type: 'clear' })
    expect(s.ownGoalId).toBe('g1')      // a still-running own task must not look external
    expect(s.activeGoalId).toBe('g1')
    s = r(s, { type: 'status', items: [{ goalId: 'g1', status: 4 }], now: 2000 })
    expect(s.activeGoalId).toBe(null)
    expect(s.taskRunning).toBe(false)
  })

  it('only the first new goal after a launch is claimed as own', () => {
    const s = run([
      { type: 'ownLaunch' },
      { type: 'feedback', goalId: 'g1', fbState: 'x', turns: 1, frameJson: '{}', now: 1000 },
      { type: 'feedback', goalId: 'g1', fbState: 'y', turns: 2, frameJson: '{}', now: 1100 },
    ])
    expect(s.ownGoalId).toBe('g1')      // not re-claimed on later feedback of the same goal
    expect(s._pendingOwn).toBe(false)
  })
})

describe('bubble curation (delete / noise)', () => {
  const base = [
    { type: 'robotUtterance', text: 'r', now: 1000 },
    { type: 'transcription', text: 'u', now: 1200 },
  ]

  it('deletes a single bubble by id', () => {
    let s = run(base)
    const userId = users(s)[0].id
    s = r(s, { type: 'deleteEvent', id: userId })
    expect(users(s)).toHaveLength(0)
    expect(robots(s)).toHaveLength(1)   // the rest is untouched
  })

  it('toggles the noise flag on and off', () => {
    let s = run(base)
    const userId = users(s)[0].id
    s = r(s, { type: 'toggleNoise', id: userId })
    expect(users(s)[0].noise).toBe(true)
    s = r(s, { type: 'toggleNoise', id: userId })
    expect(users(s)[0].noise).toBe(false)
  })
})

describe('clear', () => {
  it('empties the events and the frame, but keeps the incremental id', () => {
    const before = run([
      { type: 'robotUtterance', text: 'r', now: 1000 },
      { type: 'transcription', text: 'u', now: 1200 },
    ])
    const after = r(before, { type: 'clear' })
    expect(after.events).toHaveLength(0)
    expect(after.currentFrame).toBe(null)
    // the next event does not reuse an already-emitted id
    const next = r(after, { type: 'robotUtterance', text: 'r2', now: 2000 })
    expect(next.events[0].id).toBe('e3')
  })
})
