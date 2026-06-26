/** Tests for session export: task segmentation, latency stats and JSON/CSV/Markdown output. */
import { describe, it, expect } from 'vitest'
import { segmentByTask, summarize, buildExport } from './sessionExport'

const sample = [
  { id: 'e1', kind: 'user', text: 'hello', timestamp: 1000, transcriptionMs: 400 },
  { id: 'e2', kind: 'task_start', timestamp: 1100 },
  { id: 'e3', kind: 'user', text: 'a coffee', timestamp: 1200, transcriptionMs: 600, bargeIn: true },
  { id: 'e4', kind: 'robot', text: 'sure', timestamp: 1500, processingMs: 300, speakDurationMs: 800 },
  { id: 'e5', kind: 'task_end', timestamp: 2000, success: true, totalTurns: 1 },
]

describe('segmentByTask', () => {
  it('separates the turns before the task from the ones inside it', () => {
    const segs = segmentByTask(sample)
    expect(segs).toHaveLength(2)
    expect(segs[0]).toMatchObject({ isTask: false, label: 'No task' })
    expect(segs[1]).toMatchObject({ isTask: true, label: 'Task 1', success: true, reportedTurns: 1 })
    expect(segs[1].turns).toHaveLength(2)
  })
})

describe('summarize', () => {
  it('counts turns, barge-ins and latency statistics', () => {
    const s = summarize(sample.filter((e) => e.kind === 'user' || e.kind === 'robot'))
    expect(s).toMatchObject({ userTurns: 2, robotTurns: 1, bargeIns: 1 })
    expect(s.stt).toMatchObject({ n: 2, mean: 500 })       // (400+600)/2
    expect(s.inference).toMatchObject({ n: 1, mean: 300 })
  })
})

describe('buildExport', () => {
  const ex = buildExport(sample, new Date('2026-06-14T10:00:00Z'))

  it('generates the three formats and a timestamped name', () => {
    expect(ex.isEmpty).toBe(false)
    expect(ex.filenameBase).toMatch(/^dialostack-session-\d{8}-\d{6}$/)
    expect(() => JSON.parse(ex.json)).not.toThrow()
    expect(ex.csv.split('\n')[0]).toContain('stt_ms')
    expect(ex.markdown).toContain('## Task 1')
  })

  it('a timeline with no turns is marked as empty', () => {
    expect(buildExport([], new Date()).isEmpty).toBe(true)
  })

  it('excludes bubbles flagged as noise from every format and the stats', () => {
    const withNoise = [
      ...sample,
      { id: 'e6', kind: 'user', text: 'cough cough', timestamp: 2200, transcriptionMs: 100, noise: true },
    ]
    const out = buildExport(withNoise, new Date('2026-06-14T10:00:00Z'))
    expect(JSON.parse(out.json).summary.userTurns).toBe(2)   // noise user turn not counted
    expect(out.markdown).not.toContain('cough cough')
    expect(out.csv).not.toContain('cough cough')
  })
})
