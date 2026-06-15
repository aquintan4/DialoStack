import { DIALOG_ACTION, DIALOG_ACTION_TYPE } from '../../../lib/ros'

/** Initial draft of the launch form. */
export const LAUNCH_DEFAULT = { task_description: '', dialog_mode: '', domain: '', max_turns: 10 }

export const MODES = [
  { value: '',             label: 'Auto-detect' },
  { value: 'slot_filling', label: 'Slot filling - collect data' },
  { value: 'quiz',         label: 'Quiz - evaluate the user' },
  { value: 'explanation',  label: 'Explanation - explain a topic' },
]

export const MODE_LABEL = { '': 'auto', slot_filling: 'slot filling', quiz: 'quiz', explanation: 'explanation' }

/**
 * Validates an optional JSON field. Returns null if empty or valid, or an error
 * message if it does not parse / does not match the expected shape ('object'|'array').
 */
export function jsonFieldError(text, expected) {
  if (!text.trim()) return null
  let parsed
  try {
    parsed = JSON.parse(text)
  } catch {
    return 'Invalid JSON'
  }
  if (expected === 'object' && (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))) {
    return 'Must be a JSON object'
  }
  if (expected === 'array' && !Array.isArray(parsed)) {
    return 'Must be a JSON array'
  }
  return null
}

/**
 * `ros2 action send_goal` command equivalent to a goal. The goal is sent as JSON
 * (a subset of YAML, which is what the ros2 CLI parses), with shell-safe single
 * quotes in case the user text contains them.
 */
export function ros2Command(goal) {
  const json = JSON.stringify(goal)
  const shellSafe = `'${json.replace(/'/g, "'\\''")}'`
  return `ros2 action send_goal --feedback ${DIALOG_ACTION} ${DIALOG_ACTION_TYPE} ${shellSafe}`
}
