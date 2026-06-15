/** Tests for the frames data layer: compile/parse round-trips and goal-field mapping per mode. */
import { describe, it, expect } from 'vitest'
import { compileFields, parseDimension, stateFromFields, kindFields } from './frames'

const fieldByGoal = (kind, state, goalField) =>
  compileFields(kind, state).find((f) => f.field === goalField)

describe('compileFields: goal fields per mode', () => {
  it('slot_filling produces frame_schema_json + resources_json (optional resources)', () => {
    const fields = compileFields('slot_filling', { slots: [], resources: [] })
    expect(fields.map((f) => f.field)).toEqual(['frame_schema_json', 'resources_json'])
    expect(fields.find((f) => f.field === 'resources_json').optional).toBe(true)
  })

  it('explanation produces only resources_json (main)', () => {
    const fields = compileFields('explanation', { resources: [] })
    expect(fields.map((f) => f.field)).toEqual(['resources_json'])
    expect(fields[0].optional).toBe(false)
  })

  it('quiz produces only resources_json (question bank)', () => {
    expect(compileFields('quiz', { questions: [] }).map((f) => f.field)).toEqual(['resources_json'])
  })
})

describe('round-trip compile/parse per dimension', () => {
  it('slots preserves types, canonical values and conditions', () => {
    const slots = [
      { name: 'size', type: 'str', canonical_values: ['s', 'l'], condition_slot: '', condition_value: '' },
      { name: 'detail', type: 'str', canonical_values: [], condition_slot: 'size', condition_value: 'l' },
    ]
    const json = fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json
    expect(parseDimension('slots', json)).toEqual(slots)
  })

  it('quiz compresses questions into a resource and recovers them', () => {
    const questions = [{ question: '2+2?', answer: '4' }]
    const json = fieldByGoal('quiz', { questions }, 'resources_json').json
    expect(parseDimension('questions', json)).toEqual(questions)
  })

  it('generic resources are preserved', () => {
    const resources = [{ name: 'doc', description: 'd', content: 'texto' }]
    const json = fieldByGoal('explanation', { resources }, 'resources_json').json
    expect(parseDimension('resources', json)).toEqual(resources)
  })

  it('slot_filling with context resources: both fields round-trip', () => {
    const state = {
      slots: [{ name: 'drink', type: 'str', canonical_values: [], condition_slot: '', condition_value: '' }],
      resources: [{ name: 'menu', description: 'menu', content: 'coffee, tea' }],
    }
    const fields = compileFields('slot_filling', state)
    const schema = fields.find((f) => f.field === 'frame_schema_json')
    const res = fields.find((f) => f.field === 'resources_json')
    expect(parseDimension('slots', schema.json)).toEqual(state.slots)
    expect(parseDimension('resources', res.json)).toEqual(state.resources)
  })
})

describe('parseDimension: defensive', () => {
  it('invalid JSON returns null', () => {
    expect(parseDimension('slots', '{no json')).toBeNull()
  })
  it('empty text returns the empty dimension', () => {
    expect(parseDimension('questions', '')).toEqual([{ question: '', answer: '' }])
  })
})

describe('stateFromFields: rebuild state from the launcher fields', () => {
  it('slot_filling rebuilds slots + resources', () => {
    const { state, ok } = stateFromFields('slot_filling', {
      frame_schema_json: '{"slots":[{"name":"x","type":"str"}]}',
      resources_json: '[{"name":"m","description":"","content":"c"}]',
    })
    expect(ok).toBe(true)
    expect(state.slots[0].name).toBe('x')
    expect(state.resources[0].name).toBe('m')
  })

  it('marks ok=false if some field fails to parse', () => {
    const { ok } = stateFromFields('explanation', { resources_json: '{roto' })
    expect(ok).toBe(false)
  })
})

describe('kindFields', () => {
  it('exposes the dimensions of each mode', () => {
    expect(kindFields('slot_filling').map((f) => f.key)).toEqual(['slots', 'resources'])
    expect(kindFields('quiz').map((f) => f.key)).toEqual(['questions'])
  })
})
