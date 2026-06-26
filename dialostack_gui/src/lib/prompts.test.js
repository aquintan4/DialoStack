/** Tests for prompt-override validation, placeholder extraction and prompt grouping. */
import { describe, it, expect } from 'vitest'
import { validateOverride, placeholders, groupPrompts } from './prompts'

const DEFAULT = 'TASK: "{task}". Output: {{"mode": "x"}}'  // uses {task}; literal braces are doubled

describe('placeholders', () => {
  it('extracts only the real placeholders (ignores doubled braces)', () => {
    expect([...placeholders(DEFAULT)]).toEqual(['task'])
  })
})

describe('validateOverride - the safety net', () => {
  it('accepts using the same placeholder', () => {
    expect(validateOverride('Classify "{task}".', DEFAULT)).toBeNull()
  })

  it('accepts removing a placeholder (fixed text)', () => {
    expect(validateOverride('Text without variables.', DEFAULT)).toBeNull()
  })

  it('always allows {language}', () => {
    expect(validateOverride('In {language}: {task}', DEFAULT)).toBeNull()
  })

  it('REJECTS an unknown placeholder (would cause a KeyError at runtime)', () => {
    expect(validateOverride('Hi {user}', DEFAULT)).toMatch(/not available/i)
  })

  it('REJECTS a loose unbalanced brace', () => {
    expect(validateOverride('Text with a loose brace { here', DEFAULT)).toMatch(/braces/i)
  })

  it('REJECTS literal JSON without doubling (like the engine does)', () => {
    // {"mode": 1} has balanced braces but "mode" is not a valid placeholder
    expect(validateOverride('Return {"mode": 1}', DEFAULT)).not.toBeNull()
  })

  it('keeps correctly doubled literal braces valid', () => {
    expect(validateOverride('Return {{"ok": true}} for {task}', DEFAULT)).toBeNull()
  })
})

describe('groupPrompts', () => {
  it('groups the known keys and sends the rest to "Other"', () => {
    const groups = groupPrompts(['classify_task_mode', 'quiz_opening', 'clave_rara'])
    const other = groups.find((g) => g.label === 'Other')
    expect(other.keys).toEqual(['clave_rara'])
    expect(groups.find((g) => g.label === 'General').keys).toContain('classify_task_mode')
  })
})
