/** Tests for the frames data layer: compile/parse round-trips and goal-field mapping per mode. */
import { describe, it, expect } from 'vitest'
import { compileFields, parseDimension, stateFromFields, kindFields, emptySlot } from './frames'

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

  it('procedure produces only resources_json (steps)', () => {
    expect(compileFields('procedure', { steps: [] }).map((f) => f.field)).toEqual(['resources_json'])
  })
})

describe('round-trip compile/parse per dimension', () => {
  it('slots preserves types, canonical values and conditions', () => {
    const slots = [
      { ...emptySlot(), name: 'size', canonical_values: ['s', 'l'] },
      { ...emptySlot(), name: 'detail', condition_slot: 'size', condition_value: 'l' },
    ]
    const json = fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json
    expect(parseDimension('slots', json)).toEqual(slots)
  })

  it('numeric bounds round-trip with their operators', () => {
    const slots = [
      { ...emptySlot(), name: 'age', type: 'int', min_op: '>=', min: '18', max_op: '<', max: '120' },
      { ...emptySlot(), name: 'temp', type: 'float', min_op: '>', min: '0.5' },
    ]
    const json = fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json
    const compiled = JSON.parse(json).slots
    expect(compiled[0]).toMatchObject({ minimum: 18, exclusive_maximum: 120 })
    expect(compiled[1]).toMatchObject({ exclusive_minimum: 0.5 })
    expect(compiled[1]).not.toHaveProperty('maximum')
    expect(parseDimension('slots', json)).toEqual(slots)
  })

  it('bounds are dropped for non-numeric types and invalid numbers', () => {
    const slots = [
      { ...emptySlot(), name: 'city', type: 'str', min: '3' },
      { ...emptySlot(), name: 'n', type: 'int', min: 'abc', max: '10' },
    ]
    const compiled = JSON.parse(fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json).slots
    expect(compiled[0]).not.toHaveProperty('minimum')
    expect(compiled[1]).not.toHaveProperty('minimum')
    expect(compiled[1].maximum).toBe(10)
  })

  it('slots saved before bounds existed still compile', () => {
    const legacy = [{ name: 'n', type: 'int', canonical_values: [], condition_slot: '', condition_value: '' }]
    const compiled = JSON.parse(fieldByGoal('slot_filling', { slots: legacy, resources: [] }, 'frame_schema_json').json).slots
    expect(compiled[0]).toEqual({ name: 'n', type: 'int' })
  })

  it('numeric conditions round-trip as condition_<bound> keys', () => {
    const slots = [
      { ...emptySlot(), name: 'age', type: 'int' },
      {
        ...emptySlot(), name: 'pension', type: 'bool', condition_slot: 'age',
        condition_mode: 'range', cond_min_op: '>', cond_min: '64', cond_max_op: '<', cond_max: '100',
      },
    ]
    const json = fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json
    expect(JSON.parse(json).slots[1]).toEqual({
      name: 'pension', type: 'bool', condition_slot: 'age',
      condition_exclusive_minimum: 64, condition_exclusive_maximum: 100,
    })
    expect(parseDimension('slots', json)).toEqual(slots)
  })

  it('equality conditions ignore leftover range fields', () => {
    const slots = [{
      ...emptySlot(), name: 'detail', condition_slot: 'size', condition_value: 'l', cond_min: '5',
    }]
    const compiled = JSON.parse(fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json).slots
    expect(compiled[0]).toEqual({ name: 'detail', type: 'str', condition_slot: 'size', condition_value: 'l' })
  })

  it('an incomplete condition keeps condition_slot so the engine reports it', () => {
    const slots = [{ ...emptySlot(), name: 'x', condition_slot: 'age', condition_mode: 'range' }]
    const compiled = JSON.parse(fieldByGoal('slot_filling', { slots, resources: [] }, 'frame_schema_json').json).slots
    expect(compiled[0]).toEqual({ name: 'x', type: 'str', condition_slot: 'age' })
  })

  it('quiz compresses questions into a resource and recovers them', () => {
    const questions = [{ question: '2+2?', answer: '4' }]
    const json = fieldByGoal('quiz', { questions }, 'resources_json').json
    expect(parseDimension('questions', json)).toEqual(questions)
  })

  it('procedure packs steps into a resource and recovers them', () => {
    const steps = [{ step: 'Open the box', check: '' }, { step: 'Plug it in', check: 'green light' }]
    const json = fieldByGoal('procedure', { steps }, 'resources_json').json
    expect(parseDimension('steps', json)).toEqual(steps)
  })

  it('procedure parses the engine formats: plain strings and the instruction key', () => {
    const json = JSON.stringify([{ name: 'steps', content: JSON.stringify(['A', { instruction: 'B', check: 'c' }, '']) }])
    expect(parseDimension('steps', json)).toEqual([{ step: 'A', check: '' }, { step: 'B', check: 'c' }])
  })

  it('roleplay packs the scene into a resource and recovers it', () => {
    const scene = [{ scenario: 'Interview', role: 'HR', user_goal: 'Get it', criteria: ['Clear', 'Examples'], max_exchanges: '8' }]
    const json = fieldByGoal('roleplay', { scene }, 'resources_json').json
    expect(parseDimension('scene', json)).toEqual(scene)
  })

  it('roleplay parses criteria objects and drops a bad max_exchanges', () => {
    const content = JSON.stringify({ scenario: 'S', role: 'R', criteria: [{ name: 'A' }, ''], max_exchanges: 'x' })
    expect(parseDimension('scene', JSON.stringify([{ name: 'scene', content }]))).toEqual([
      { scenario: 'S', role: 'R', user_goal: '', criteria: ['A'], max_exchanges: '' },
    ])
  })

  it('generic resources are preserved', () => {
    const resources = [{ name: 'doc', description: 'd', content: 'texto' }]
    const json = fieldByGoal('explanation', { resources }, 'resources_json').json
    expect(parseDimension('resources', json)).toEqual(resources)
  })

  it('slot_filling with context resources: both fields round-trip', () => {
    const state = {
      slots: [{ ...emptySlot(), name: 'drink' }],
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
    expect(kindFields('procedure').map((f) => f.key)).toEqual(['steps'])
    expect(kindFields('roleplay').map((f) => f.key)).toEqual(['scene'])
  })
})
