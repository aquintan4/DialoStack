import { describe, it, expect } from 'vitest'
import { ros2Command, jsonFieldError, buildGoal, buildResourcesJson } from './goal'

describe('ros2Command', () => {
  const goal = { task_description: 'order coffee', dialog_mode: 'slot_filling', max_turns: 10 }

  it('generates a command with the action and the goal as JSON', () => {
    const cmd = ros2Command(goal)
    expect(cmd).toContain('ros2 action send_goal --feedback /dialog/execute_task')
    expect(cmd).toContain('ros2_dialog_interfaces/action/DialogTask')
    // the goal is wrapped in single quotes
    expect(cmd).toMatch(/'\{.*\}'/)
  })

  it('escapes single quotes in the text shell-safely', () => {
    const cmd = ros2Command({ task_description: "l'addition" })
    // ' becomes '\'' (close the quoting, escaped quote, reopen)
    expect(cmd).toContain("l'\\''addition")
  })
})

describe('jsonFieldError', () => {
  it('accepts empty (optional field)', () => {
    expect(jsonFieldError('', 'object')).toBeNull()
    expect(jsonFieldError('   ', 'array')).toBeNull()
  })

  it('detects invalid JSON', () => {
    expect(jsonFieldError('{no', 'object')).toMatch(/invalid/i)
  })

  it('enforces the expected shape (object vs array)', () => {
    expect(jsonFieldError('[]', 'object')).toMatch(/object/i)
    expect(jsonFieldError('{}', 'array')).toMatch(/array/i)
    expect(jsonFieldError('{"slots":[]}', 'object')).toBeNull()
    expect(jsonFieldError('[{"name":"x"}]', 'array')).toBeNull()
  })
})

describe('buildResourcesJson', () => {
  const form = (mode) => ({ dialog_mode: mode })

  it('packs the quiz question bank into a single "questions" resource', () => {
    const out = buildResourcesJson({
      form: form('quiz'),
      quizQuestions: [{ question: 'Q1', answer: 'A1' }, { question: ' ', answer: '' }],
    })
    const parsed = JSON.parse(out)
    expect(parsed).toHaveLength(1)
    expect(parsed[0].name).toBe('questions')
    expect(JSON.parse(parsed[0].content)).toEqual([{ question: 'Q1', answer: 'A1' }]) // blanks dropped
  })

  it('returns "" for quiz with no complete questions, and the raw resources otherwise', () => {
    expect(buildResourcesJson({ form: form('quiz'), quizQuestions: [] })).toBe('')
    expect(buildResourcesJson({ form: form('slot_filling'), resources: '  [{"name":"x"}] ' }))
      .toBe('[{"name":"x"}]')
  })
})

describe('buildGoal', () => {
  it('trims and normalises the draft into a DialogTask goal', () => {
    const goal = buildGoal({
      form: { task_description: '  order coffee ', dialog_mode: 'slot_filling', domain: ' cafe ', max_turns: 0, skip_intro: true },
      frameSchema: ' {"slots":[]} ',
      resources: '',
      quizQuestions: [],
    })
    expect(goal).toMatchObject({
      task_description: 'order coffee',
      dialog_mode: 'slot_filling',
      domain: 'cafe',
      frame_schema_json: '{"slots":[]}',
      max_turns: 10,            // 0 -> default 10
      skip_intro: true,
      initial_frame_json: '',
    })
  })
})
