/**
 * Serialization of a Monitor session to CSV / JSON / Markdown.
 *
 * Works over `timeline.events` (the same array the chat renders), so it needs
 * NO capture: it exports what is already on screen, including the metrics only
 * the GUI computes (STT latency, inference, TTS, barge-in).
 *
 * Everything is pure functions except `buildExport`, which receives the date
 * from the UI.
 */

import { fileStamp } from './download'

const formatMs = (ms) => {
  if (ms == null || !isFinite(ms)) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

const isoTime = (ts) => (ts != null ? new Date(ts).toISOString() : '')
const clockTime = (ts) =>
  ts != null ? new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''

/** Basic stats over an array of ms (drops nulls). null if no data. */
function stats(arr) {
  const v = arr.filter((x) => typeof x === 'number' && isFinite(x))
  if (!v.length) return null
  const sorted = [...v].sort((a, b) => a - b)
  const sum = v.reduce((a, b) => a + b, 0)
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
  return {
    n: v.length,
    mean: Math.round(sum / v.length),
    median: Math.round(median),
    min: Math.round(sorted[0]),
    max: Math.round(sorted[sorted.length - 1]),
  }
}

/** Aggregated summary of a list of turns (user/robot events). */
export function summarize(turns) {
  const users = turns.filter((t) => t.kind === 'user')
  const robots = turns.filter((t) => t.kind === 'robot')
  const ts = turns.map((t) => t.timestamp).filter((x) => x != null)
  return {
    userTurns: users.length,
    robotTurns: robots.length,
    bargeIns: users.filter((t) => t.bargeIn).length + robots.filter((t) => t.interrupted).length,
    durationMs: ts.length ? Math.max(...ts) - Math.min(...ts) : 0,
    stt: stats(users.map((t) => t.transcriptionMs)),
    inference: stats(robots.map((t) => t.processingMs)),
    tts: stats(robots.map((t) => t.speakDurationMs)),
  }
}

/**
 * Splits the timeline into per-task segments (delimited by task_start). Turns
 * before any task form a "No task" segment.
 */
export function segmentByTask(events) {
  const groups = []
  let current = null
  const ensure = () => { if (!current) current = { taskStart: null, taskEnd: null, raw: [] } }

  for (const e of events) {
    if (e.kind === 'task_start') {
      if (current) groups.push(current)
      current = { taskStart: e, taskEnd: null, raw: [] }
    } else if (e.kind === 'task_end') {
      ensure()
      current.taskEnd = e
    } else if (e.kind === 'user' || e.kind === 'robot') {
      ensure()
      current.raw.push(e)
    }
  }
  if (current) groups.push(current)

  let taskNo = 0
  return groups
    .filter((g) => g.taskStart || g.raw.length)
    .map((g) => {
      const isTask = !!g.taskStart
      if (isTask) taskNo += 1
      const turns = g.raw
      const startedAt = g.taskStart?.timestamp ?? turns[0]?.timestamp ?? null
      const endedAt = g.taskEnd?.timestamp ?? turns[turns.length - 1]?.timestamp ?? startedAt
      return {
        taskNo: isTask ? taskNo : null,
        label: isTask ? `Task ${taskNo}` : 'No task',
        isTask,
        startedAt,
        endedAt,
        success: g.taskEnd?.success ?? null,
        reason: g.taskEnd?.reason ?? '',
        reportedTurns: g.taskEnd?.totalTurns ?? null,
        turns,
        summary: summarize(turns),
      }
    })
}

// ==== CSV ====

const csvCell = (v) => {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function toCSV(segments) {
  const allTurns = segments.flatMap((s) => s.turns)
  const t0 = Math.min(...allTurns.map((t) => t.timestamp).filter((x) => x != null), Infinity)
  const header = [
    'task', 'n', 'time_iso', 't_rel_ms', 'speaker', 'text',
    'stt_ms', 'inference_ms', 'tts_ms', 'barge_in', 'interrupted',
  ]
  const rows = []
  let n = 0
  for (const seg of segments) {
    for (const t of seg.turns) {
      n += 1
      rows.push([
        seg.taskNo ?? '',
        n,
        isoTime(t.timestamp),
        t.timestamp != null && isFinite(t0) ? t.timestamp - t0 : '',
        t.kind,
        csvCell(t.text),
        t.kind === 'user' ? Math.round(t.transcriptionMs ?? NaN) || '' : '',
        t.kind === 'robot' ? Math.round(t.processingMs ?? NaN) || '' : '',
        t.kind === 'robot' ? Math.round(t.speakDurationMs ?? NaN) || '' : '',
        t.bargeIn ? 1 : 0,
        t.interrupted ? 1 : 0,
      ].join(','))
    }
  }
  return [header.join(','), ...rows].join('\n')
}

// ==== MARKDOWN ====

const fmtStats = (s, icon) => (s ? `${icon} mean ${formatMs(s.mean)} · median ${formatMs(s.median)} (n=${s.n})` : null)

function summaryLines(s) {
  const lines = [
    `${s.userTurns} user turns · ${s.robotTurns} robot turns · ${s.bargeIns} barge-ins · duration ${formatMs(s.durationMs)}`,
    fmtStats(s.stt, '🎙️ STT:'),
    fmtStats(s.inference, '⚡ Inference:'),
    fmtStats(s.tts, '🔊 TTS:'),
  ].filter(Boolean)
  return lines
}

function toMarkdown(segments, overall, exportedAtIso) {
  const out = [`# DialoStack session`, `_Exported: ${exportedAtIso}_`, '']
  const taskCount = segments.filter((s) => s.isTask).length
  const ok = segments.filter((s) => s.success === true).length
  out.push(`**Summary** — ${taskCount} tasks (${ok} completed)`)
  summaryLines(overall).forEach((l) => out.push(`- ${l}`))
  out.push('')

  for (const seg of segments) {
    const tag = seg.isTask
      ? seg.success === true ? '✓ completed'
        : seg.success === false ? `✗ ${seg.reason || 'failed'}`
          : 'in progress'
      : ''
    out.push(`## ${seg.label}${seg.isTask ? ` (${tag}${seg.reportedTurns != null ? ` · ${seg.reportedTurns} turns` : ''})` : ''}`)
    for (const t of seg.turns) {
      const who = t.kind === 'user' ? '🧑 **User:**' : '🤖 **Robot:**'
      const tags = t.kind === 'user'
        ? [t.transcriptionMs != null ? `🎙️ ${formatMs(t.transcriptionMs)}` : null, t.bargeIn ? '⚡ barge-in' : null]
        : [t.processingMs != null ? `⚡ ${formatMs(t.processingMs)}` : null,
           t.speakDurationMs != null ? `🔊 ${formatMs(t.speakDurationMs)}` : null,
           t.interrupted ? '✂️ interrupted' : null]
      const suffix = tags.filter(Boolean).length ? `  · ${tags.filter(Boolean).join(' · ')}` : ''
      out.push(`- \`${clockTime(t.timestamp)}\` ${who} ${JSON.stringify(t.text)}${suffix}`)
    }
    out.push('')
  }
  return out.join('\n')
}

// ==== ENTRY POINT ====

/**
 * Builds the three formats at once. `date` comes from the UI (new Date()).
 * Returns { json, csv, markdown, filenameBase, isEmpty }.
 */
export function buildExport(events, date) {
  const segments = segmentByTask(events)
  const allTurns = segments.flatMap((s) => s.turns)
  const taskSegs = segments.filter((s) => s.isTask)
  const overall = {
    ...summarize(allTurns),
    tasks: taskSegs.length,
    tasksSucceeded: taskSegs.filter((s) => s.success === true).length,
  }
  const exportedAtIso = date.toISOString()

  const json = JSON.stringify(
    { exportedAt: exportedAtIso, summary: overall, tasks: segments },
    null, 2,
  )

  return {
    isEmpty: allTurns.length === 0,
    filenameBase: `dialostack-session-${fileStamp(date)}`,
    json,
    csv: toCSV(segments),
    markdown: toMarkdown(segments, overall, exportedAtIso),
  }
}
