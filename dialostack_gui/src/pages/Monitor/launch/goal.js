import { DIALOG_ACTION, DIALOG_ACTION_TYPE } from '../../../lib/ros'
import { sceneToJSON } from '../../../lib/frames'

/** Initial draft of the launch form. */
export const LAUNCH_DEFAULT = { task_description: '', dialog_mode: '', domain: '', max_turns: 10, skip_intro: false }

export const MODES = [
  { value: '',             label: 'Auto-detect' },
  { value: 'slot_filling', label: 'Slot filling - collect data' },
  { value: 'quiz',         label: 'Quiz - evaluate the user' },
  { value: 'explanation',  label: 'Explanation - explain a topic' },
  { value: 'procedure',    label: 'Procedure - guide step by step' },
  { value: 'roleplay',     label: 'Roleplay - practise a scene, get scored' },
]

export const MODE_LABEL = {
  '': 'auto', slot_filling: 'slot filling', quiz: 'quiz', explanation: 'explanation', procedure: 'procedure',
  roleplay: 'roleplay',
}

// Modes whose payload is edited in the drawer itself (not as raw resources JSON).
export const PACKED_MODES = ['quiz', 'procedure', 'roleplay']

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
 * Resources payload for a goal. Quiz mode packs the question bank into a single
 * "questions" resource, procedure mode its steps into a "steps" resource and
 * roleplay mode its scene into a "scene" resource; the other modes pass the raw
 * resources JSON. Pure, so it is shared by the launch
 * (send) and the copy (ros2 command / JSON) paths.
 */
export function buildResourcesJson({ form, resources, quizQuestions, procedureSteps, roleplayScene }) {
  if (form.dialog_mode === 'quiz') {
    const items = (quizQuestions || []).filter((q) => q.question.trim() && q.answer.trim())
    return items.length
      ? JSON.stringify([{ name: 'questions', description: 'Quiz question bank', content: JSON.stringify(items) }])
      : ''
  }
  if (form.dialog_mode === 'procedure') {
    const items = (procedureSteps || [])
      .filter((s) => s.step.trim())
      .map((s) => (s.check.trim() ? { step: s.step.trim(), check: s.check.trim() } : { step: s.step.trim() }))
    return items.length
      ? JSON.stringify([{ name: 'steps', description: 'Procedure steps', content: JSON.stringify(items) }])
      : ''
  }
  if (form.dialog_mode === 'roleplay') {
    const scene = sceneToJSON(roleplayScene?.[0])
    return scene
      ? JSON.stringify([{ name: 'scene', description: 'Roleplay scene', content: JSON.stringify(scene) }])
      : ''
  }
  return (resources || '').trim()
}

/** The DialogTask goal built from the launch-form draft (single source). */
export function buildGoal({ form, frameSchema, resources, quizQuestions, procedureSteps, roleplayScene }) {
  return {
    task_description: form.task_description.trim(),
    frame_schema_json: (frameSchema || '').trim(),
    initial_frame_json: '',
    max_turns: Number(form.max_turns) || 10,
    dialog_mode: form.dialog_mode,
    resources_json: buildResourcesJson({ form, resources, quizQuestions, procedureSteps, roleplayScene }),
    domain: form.domain.trim(),
    skip_intro: Boolean(form.skip_intro),
  }
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
