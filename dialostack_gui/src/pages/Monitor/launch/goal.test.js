import { describe, it, expect } from 'vitest'
import { ros2Command, jsonFieldError } from './goal'

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
