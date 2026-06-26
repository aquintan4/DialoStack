/**
 * Shared time/duration formatting for the Monitor and the session export.
 * Single source so the chat bubbles and the exported files stay consistent.
 */

/** "1.2s" / "450ms", or null when there is no value (callers skip the label). */
export function formatMs(ms) {
  if (ms == null || !Number.isFinite(ms)) return null
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

/** Wall-clock HH:MM:SS. Default locale es-ES (the Monitor); export uses en-GB. */
export function formatTime(timestamp, locale = 'es-ES') {
  if (timestamp == null) return ''
  return new Date(timestamp).toLocaleTimeString(locale, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
