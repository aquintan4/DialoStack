/** ROS 2 stack start/stop control with an integrated log viewer. */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, Play, RefreshCw, Square } from 'lucide-react'
import { useConfig } from '../../contexts/ConfigContext'
import { useEngine } from '../../contexts/EngineContext'
import { ENGINE_STATUS } from '../../lib/status'
import { api } from '../../lib/api'

const LOG_POLL_MS = 3000

export function EnginePanel() {
  const { config } = useConfig()
  const { engineState, lastError, startEngine, stopEngine } = useEngine()
  const { state, pid } = engineState
  const s = ENGINE_STATUS[state] ?? ENGINE_STATUS.stopped
  const [logOpen, setLogOpen] = useState(false)
  const [logText, setLogText] = useState('')

  useEffect(() => {
    if (!logOpen) return
    let active = true
    async function fetchLog() {
      try {
        const data = await api.engineLog()
        if (active) setLogText(data.log ?? '')
      } catch {
        // GUI server unreachable - retried on the next cycle
      }
    }
    fetchLog()
    const id = setInterval(fetchLog, LOG_POLL_MS)
    return () => { active = false; clearInterval(id) }
  }, [logOpen])

  return (
    <div className={`border rounded-xl bg-app-900 overflow-hidden ${s.border}`}>
      <div className="flex items-center justify-between px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-slate-200">DialoStack Engine</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
            <span className={`text-xs font-medium ${s.text}`}>{s.label}</span>
            {pid && <span className="text-xs text-slate-600 font-mono ml-1">PID {pid}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {state === 'starting' && (
            <span className="flex items-center gap-2 text-sm text-slate-400 px-3 py-2">
              <Loader2 size={14} className="animate-spin" /> Starting...
            </span>
          )}
          {state === 'running' && (
            <button onClick={stopEngine}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm
                bg-red-900/30 border border-red-700/50 text-red-400 hover:bg-red-900/50 transition-colors">
              <Square size={13} /> Stop engine
            </button>
          )}
          {(state === 'stopped' || state === 'error') && (
            <button onClick={() => startEngine(config)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm
                bg-brand-600 hover:bg-brand-700 text-white font-medium transition-colors glow-blue">
              {state === 'error'
                ? <><RefreshCw size={13} /> Retry</>
                : <><Play size={13} /> Start engine</>}
            </button>
          )}
          <button onClick={() => setLogOpen(o => !o)}
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-app-700 transition-colors"
            title="View log">
            {logOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {state === 'running' && !logOpen && (
        <p className="px-5 pb-3 text-xs text-slate-600 border-t border-green-700/20 pt-2.5">
          To apply changes, stop and start the engine again.
        </p>
      )}
      {state === 'error' && !logOpen && (
        <p className="px-5 pb-3 text-xs text-red-400/70 border-t border-red-700/20 pt-2.5">
          {lastError || 'Check that ROS 2 is available and the workspace is built.'}{' '}
          Press <span className="font-mono">▼</span> to view the log.
        </p>
      )}
      {logOpen && (
        <div className="border-t border-app-border px-4 py-3">
          <pre className="text-[11px] text-slate-400 font-mono leading-relaxed overflow-x-auto
            max-h-48 overflow-y-auto whitespace-pre-wrap break-all">
            {logText || '(no log yet)'}
          </pre>
        </div>
      )}
    </div>
  )
}
