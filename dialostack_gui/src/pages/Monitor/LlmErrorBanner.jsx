/** Dismissible banner shown when an LLM inference fails (from /llm/error). */
import { AlertTriangle, X } from 'lucide-react'

// Short, human summary. Code takes precedence (most specific); fall back to the
// transport-level error_type. Unknown codes still render as "HTTP <code>".
function summarise({ code, errorType }) {
  const byCode = {
    400: 'bad request', 401: 'unauthorized (API key?)', 403: 'forbidden',
    404: 'model not found', 408: 'request timeout', 429: 'rate limit / quota',
    500: 'provider internal error', 502: 'bad gateway',
    503: 'service unavailable', 504: 'gateway timeout',
  }
  if (code && byCode[code]) return byCode[code]
  if (code) return `HTTP ${code}`
  const byType = {
    timeout: 'timed out',
    connection: "can't reach the provider",
    api: 'provider API error',
    http: 'HTTP error',
  }
  return byType[errorType] || 'inference error'
}

export function LlmErrorBanner({ error, onDismiss }) {
  if (!error) return null
  const target = [error.provider, error.model].filter(Boolean).join('/') || 'LLM'

  return (
    <div className="flex items-start gap-2.5 mx-6 mt-3 px-3.5 py-2.5 rounded-lg
      bg-red-950/40 border border-red-800/50 flex-shrink-0">
      <AlertTriangle size={15} className="text-red-400 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-red-300">
          LLM error · <span className="font-mono">{target}</span>
          <span className="ml-1.5 text-red-400/90">— {summarise(error)}</span>
        </p>
        {error.message && (
          <p className="text-[11px] text-red-400/70 mt-0.5 break-words line-clamp-2">{error.message}</p>
        )}
        <p className="text-[11px] text-slate-500 mt-0.5">
          The dialogue is using the deterministic fallback until the model responds.
        </p>
      </div>
      <button
        onClick={onDismiss}
        title="Dismiss"
        className="p-1 -m-1 rounded text-red-400/60 hover:text-red-300 transition-colors flex-shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  )
}
