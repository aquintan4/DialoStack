/**
 * Data layer for the Builder "frames".
 *
 * A frame is the structured payload of a dialogue. The goal has TWO independent
 * payload fields and each mode (kind) uses the ones that apply to it:
 *
 *   frame_schema_json   { "slots": [...] }                      - slot_filling only
 *   resources_json      [{ name, description, content }, ...]   - every mode, different role:
 *       - slot_filling: reference material (CONTEXT, optional)
 *       - explanation:  the material to explain (main)
 *       - quiz:         question bank, content = "[{question,answer}]"
 *       - procedure:    ordered steps, content = "[{step,check?}]"
 *       - roleplay:     the scene, content = "{scenario,role,user_goal?,criteria,max_exchanges?}"
 *
 * Model: "resources" is an orthogonal DIMENSION, not a mode. Each kind declares
 * which dimensions it edits (KIND_FIELDS) and each dimension knows how to
 * compile/parse its JSON. ONLY pure functions live here; the UI duplicates nothing.
 */

// ==== LOCALSTORAGE KEYS (single source in lib/storageKeys.js) ====
import { STORAGE } from './storageKeys'
export const LIBRARY_KEY = STORAGE.frames                  // library of saved frames
export const HANDOFF_TO_BUILDER = STORAGE.handoffToBuilder // Launcher -> Builder { kind, state }
export const INJECT_TO_LAUNCH = STORAGE.injectToLaunch     // Builder -> Launcher { kind, state }

// ==== SLOT TYPES (slot_filling) ====
export const SLOT_TYPES = [
  { value: 'str',      label: 'Text (str)' },
  { value: 'int',      label: 'Integer (int)' },
  { value: 'float',    label: 'Decimal (float)' },
  { value: 'bool',     label: 'Boolean (bool)' },
  { value: 'list_str', label: 'List (list_str)' },
]
const TYPE_VALUES = SLOT_TYPES.map((t) => t.value)
export const NUMERIC_TYPES = ['int', 'float']

// Numeric bounds (int/float slots). The UI edits an operator + a value per
// side; the engine schema uses one key per operator (JSON Schema naming).
export const LOWER_OPS = [{ value: '>=', key: 'minimum' }, { value: '>', key: 'exclusive_minimum' }]
export const UPPER_OPS = [{ value: '<=', key: 'maximum' }, { value: '<', key: 'exclusive_maximum' }]

// The same range editor is used twice per slot: for the slot's own value and
// for a numeric condition on its parent (engine keys prefixed "condition_").
const VALUE_RANGE = { min_op: 'min_op', min: 'min', max_op: 'max_op', max: 'max', prefix: '' }
const CONDITION_RANGE = {
  min_op: 'cond_min_op', min: 'cond_min', max_op: 'cond_max_op', max: 'cond_max', prefix: 'condition_',
}

/** Engine bound keys of one range, e.g. { minimum: 18, exclusive_maximum: 120 }. */
function rangeToJSON(s, f) {
  const out = {}
  for (const [ops, op, raw] of [[LOWER_OPS, s[f.min_op], s[f.min]], [UPPER_OPS, s[f.max_op], s[f.max]]]) {
    const value = Number(raw)
    if (String(raw ?? '').trim() === '' || !Number.isFinite(value)) continue
    out[f.prefix + (ops.find((o) => o.value === op) || ops[0]).key] = value
  }
  return out
}

/** Inverse of rangeToJSON: UI fields from an engine slot definition. */
function rangeFromJSON(s, f) {
  const side = (ops) => {
    const hit = ops.find((o) => typeof s?.[f.prefix + o.key] === 'number')
    return hit ? [hit.value, String(s[f.prefix + hit.key])] : [ops[0].value, '']
  }
  const [minOp, min] = side(LOWER_OPS)
  const [maxOp, max] = side(UPPER_OPS)
  return { [f.min_op]: minOp, [f.min]: min, [f.max_op]: maxOp, [f.max]: max }
}

/**
 * Condition keys of one UI slot: equality or numeric range on the parent.
 * condition_slot is kept even when the test is incomplete, so the engine
 * rejects the schema with a clear error instead of silently dropping it.
 */
function conditionToJSON(s) {
  if (!s.condition_slot) return {}
  const test = s.condition_mode === 'range'
    ? rangeToJSON(s, CONDITION_RANGE)
    : (s.condition_value ? { condition_value: s.condition_value } : {})
  return { condition_slot: s.condition_slot, ...test }
}

const hasConditionRange = (s) =>
  [...LOWER_OPS, ...UPPER_OPS].some((o) => typeof s?.[CONDITION_RANGE.prefix + o.key] === 'number')

// ==== EMPTY ELEMENTS PER DIMENSION ====
export const emptySlot = () => ({
  name: '', type: 'str', canonical_values: [], condition_slot: '', condition_value: '',
  min_op: '>=', min: '', max_op: '<=', max: '',
  condition_mode: 'equals', cond_min_op: '>=', cond_min: '', cond_max_op: '<=', cond_max: '',
})
export const emptyQuestion = () => ({ question: '', answer: '' })
export const emptyStep = () => ({ step: '', check: '' })
export const emptyScene = () => ({ scenario: '', role: '', user_goal: '', criteria: [''], max_exchanges: '' })
export const emptyResource = () => ({ name: '', description: '', content: '' })

// ==== COMPILERS AND PARSERS PER DIMENSION ====

function buildSlotsJSON(slots) {
  const clean = (slots || [])
    .filter((s) => s.name.trim())
    .map((s) => ({
      name: s.name.trim(),
      type: TYPE_VALUES.includes(s.type) ? s.type : 'str',
      ...(s.canonical_values.filter((v) => v.trim()).length > 0
        ? { canonical_values: s.canonical_values.filter((v) => v.trim()) }
        : {}),
      ...conditionToJSON(s),
      ...(NUMERIC_TYPES.includes(s.type) ? rangeToJSON(s, VALUE_RANGE) : {}),
    }))
  return JSON.stringify({ slots: clean }, null, 2)
}

function buildQuizJSON(questions) {
  const items = (questions || [])
    .filter((q) => q.question.trim() && q.answer.trim())
    .map((q) => ({ question: q.question.trim(), answer: q.answer.trim() }))
  return JSON.stringify(
    [{ name: 'questions', description: 'Quiz question bank', content: JSON.stringify(items) }],
    null, 2,
  )
}

function buildStepsJSON(steps) {
  const items = (steps || [])
    .filter((s) => s.step.trim())
    .map((s) => (s.check.trim() ? { step: s.step.trim(), check: s.check.trim() } : { step: s.step.trim() }))
  return JSON.stringify(
    [{ name: 'steps', description: 'Procedure steps', content: JSON.stringify(items) }],
    null, 2,
  )
}

/**
 * Engine payload of one roleplay scene, or null while scenario/role are empty.
 * Shared with the launcher (goal.js) so both pack the scene the same way.
 */
export function sceneToJSON(scene) {
  if (!scene?.scenario?.trim() || !scene?.role?.trim()) return null
  const max = Number(scene.max_exchanges)
  return {
    scenario: scene.scenario.trim(),
    role: scene.role.trim(),
    ...(scene.user_goal?.trim() ? { user_goal: scene.user_goal.trim() } : {}),
    criteria: (scene.criteria || []).map((c) => c.trim()).filter(Boolean),
    ...(Number.isInteger(max) && max > 0 ? { max_exchanges: max } : {}),
  }
}

function buildSceneJSON(scenes) {
  const scene = sceneToJSON(scenes?.[0])
  return JSON.stringify(
    scene ? [{ name: 'scene', description: 'Roleplay scene', content: JSON.stringify(scene) }] : [],
    null, 2,
  )
}

function buildResourcesJSON(resources) {
  const items = (resources || [])
    .filter((r) => r.name.trim() && r.content.trim())
    .map((r) => ({ name: r.name.trim(), description: r.description.trim(), content: r.content }))
  return JSON.stringify(items, null, 2)
}

function slotsFromJSON(parsed) {
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.slots)) return null
  return parsed.slots.map((s) => ({
    name: String(s?.name ?? ''),
    type: TYPE_VALUES.includes(s?.type) ? s.type : 'str',
    canonical_values: Array.isArray(s?.canonical_values) ? s.canonical_values.map(String) : [],
    condition_slot: String(s?.condition_slot ?? ''),
    condition_value: String(s?.condition_value ?? ''),
    ...rangeFromJSON(s, VALUE_RANGE),
    condition_mode: hasConditionRange(s) ? 'range' : 'equals',
    ...rangeFromJSON(s, CONDITION_RANGE),
  }))
}

// Same criterion as the engine's QuizStrategy._parse_questions: the first resource
// whose content is a list of {question/q, answer/a} is the bank.
function questionsFromJSON(parsed) {
  if (!Array.isArray(parsed)) return null
  for (const r of parsed) {
    const content = (r?.content ?? '').toString().trim()
    if (!content) continue
    let data
    try { data = JSON.parse(content) } catch { continue }
    if (!Array.isArray(data)) continue
    const items = data
      .map((e) => ({ question: String(e?.question ?? e?.q ?? ''), answer: String(e?.answer ?? e?.a ?? '') }))
      .filter((q) => q.question.trim())
    if (items.length) return items
  }
  return null
}

// Same criterion as the engine's ProcedureStrategy._parse_steps: the first
// resource whose content is a list of steps (strings or {step/instruction, check}).
function stepsFromJSON(parsed) {
  if (!Array.isArray(parsed)) return null
  for (const r of parsed) {
    const content = (r?.content ?? '').toString().trim()
    if (!content) continue
    let data
    try { data = JSON.parse(content) } catch { continue }
    if (!Array.isArray(data)) continue
    const items = data
      .map((e) => (typeof e === 'string'
        ? { step: e, check: '' }
        : { step: String(e?.step ?? e?.instruction ?? ''), check: String(e?.check ?? '') }))
      .filter((s) => s.step.trim())
    if (items.length) return items
  }
  return null
}

// Same criterion as the engine's RoleplayStrategy._parse_scene: the first
// resource whose content is an object with scenario and role.
function sceneFromJSON(parsed) {
  if (!Array.isArray(parsed)) return null
  for (const r of parsed) {
    let data
    try { data = JSON.parse((r?.content ?? '').toString()) } catch { continue }
    if (!data || typeof data !== 'object' || Array.isArray(data)) continue
    if (!String(data.scenario ?? '').trim() || !String(data.role ?? '').trim()) continue
    const criteria = (Array.isArray(data.criteria) ? data.criteria : [])
      .map((c) => String((c && typeof c === 'object' ? c.name : c) ?? ''))
      .filter((c) => c.trim())
    return [{
      scenario: String(data.scenario),
      role: String(data.role),
      user_goal: String(data.user_goal ?? ''),
      criteria: criteria.length ? criteria : [''],
      max_exchanges: Number(data.max_exchanges) > 0 ? String(data.max_exchanges) : '',
    }]
  }
  return null
}

function resourcesFromJSON(parsed) {
  if (!Array.isArray(parsed)) return null
  return parsed
    .filter((r) => r && typeof r === 'object')
    .map((r) => ({
      name: String(r.name ?? ''),
      description: String(r.description ?? ''),
      content: String(r.content ?? ''),
    }))
}

/**
 * Dimension table: how each one is compiled/parsed and what its empty element
 * is. `field` is the goal field it goes to by default (resources/questions
 * share resources_json, so the field is set in KIND_FIELDS, not here).
 */
const DIMENSIONS = {
  slots:     { build: buildSlotsJSON,     parse: slotsFromJSON,     empty: emptySlot },
  resources: { build: buildResourcesJSON, parse: resourcesFromJSON, empty: emptyResource },
  questions: { build: buildQuizJSON,      parse: questionsFromJSON, empty: emptyQuestion },
  steps:     { build: buildStepsJSON,     parse: stepsFromJSON,     empty: emptyStep },
  scene:     { build: buildSceneJSON,     parse: sceneFromJSON,     empty: emptyScene },
}

// ==== MODES AND THE GOAL FIELDS EACH ONE PRODUCES ====
// key = editable dimension; field = goal field; optional = omitted from the goal
// if empty (slot_filling resources are optional context).
const KIND_FIELDS = {
  slot_filling: [
    { key: 'slots',     field: 'frame_schema_json', label: 'Slots',     optional: false },
    { key: 'resources', field: 'resources_json',    label: 'Resources', optional: true },
  ],
  explanation: [
    { key: 'resources', field: 'resources_json', label: 'Resources', optional: false },
  ],
  quiz: [
    { key: 'questions', field: 'resources_json', label: 'Questions', optional: false },
  ],
  procedure: [
    { key: 'steps', field: 'resources_json', label: 'Steps', optional: false },
  ],
  roleplay: [
    { key: 'scene', field: 'resources_json', label: 'Scene', optional: false },
  ],
}

export const FRAME_KINDS = [
  { value: 'slot_filling', label: 'Slot filling', desc: 'Collect structured data (+ optional context resources)' },
  { value: 'quiz',         label: 'Quiz',         desc: 'Question bank with its answer' },
  { value: 'explanation',  label: 'Explanation',  desc: 'Reference material to explain' },
  { value: 'procedure',    label: 'Procedure',    desc: 'Ordered steps to guide the user through' },
  { value: 'roleplay',     label: 'Roleplay',     desc: 'A scene the robot acts out, and the rubric to score the user' },
]

export const kindMeta = (kind) => FRAME_KINDS.find((k) => k.value === kind) ?? FRAME_KINDS[0]
export const kindFields = (kind) => KIND_FIELDS[kind] ?? KIND_FIELDS.slot_filling

// ==== STATE, COMPILATION AND PARSING ====

export const emptyDimension = (key) => [DIMENSIONS[key].empty()]

/** Initial editable state of a mode: one empty entry per dimension. */
export function emptyState(kind) {
  const out = {}
  for (const f of kindFields(kind)) out[f.key] = emptyDimension(f.key)
  return out
}

/** Compiles the state into the list of goal fields: [{ key, field, label, json }]. */
export function compileFields(kind, state) {
  return kindFields(kind).map((f) => ({
    key: f.key,
    field: f.field,
    label: f.label,
    optional: f.optional,
    json: DIMENSIONS[f.key].build(state?.[f.key]),
  }))
}

/**
 * Parses a dimension's JSON into its editable items, or null if it does not fit.
 * Empty text -> empty dimension (not an error).
 */
export function parseDimension(key, text) {
  if (!text || !text.trim()) return emptyDimension(key)
  let parsed
  try { parsed = JSON.parse(text) } catch { return null }
  const items = DIMENSIONS[key].parse(parsed)
  if (!items) return null
  return items.length ? items : emptyDimension(key)
}

/**
 * Builds a mode's state from the JSON texts of its fields.
 * `texts` maps goal field -> JSON. Returns { state, ok }: ok=false if some
 * field fails to parse (the state uses the empty dimension for those).
 */
export function stateFromFields(kind, texts) {
  const state = {}
  let ok = true
  for (const f of kindFields(kind)) {
    const items = parseDimension(f.key, texts?.[f.field] ?? '')
    if (items === null) { ok = false; state[f.key] = emptyDimension(f.key) }
    else state[f.key] = items
  }
  return { state, ok }
}

// ==== HANDOFF HELPERS (read/write of the localStorage channel) ====

export function readHandoff(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function writeHandoff(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* ignore */ }
}

export function clearHandoff(key) {
  try { localStorage.removeItem(key) } catch { /* ignore */ }
}
