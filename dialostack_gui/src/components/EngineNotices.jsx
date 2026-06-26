/** Global floating notices about the engine: auto-stop on inactivity and start failures. */
import { AlertOctagon, Play, PowerOff, SlidersHorizontal, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useEngine } from '../contexts/EngineContext'
import { useConfig } from '../contexts/ConfigContext'

function NoticeCard({ tone, icon: Icon, title, children, actions, onDismiss }) {
  const border = tone === 'error' ? 'border-red-700/50' : 'border-yellow-700/50'
  const iconBox = tone === 'error'
    ? 'bg-red-900/30 border-red-700/40 text-red-400'
    : 'bg-yellow-900/30 border-yellow-700/40 text-yellow-400'

  return (
    <div className={`bg-app-900 border ${border} rounded-xl shadow-2xl shadow-black/50 overflow-hidden`}>
      <div className="flex items-start gap-3 p-4">
        <div className={`w-9 h-9 rounded-lg border flex items-center justify-center flex-shrink-0 ${iconBox}`}>
          <Icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-200">{title}</p>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{children}</p>
        </div>
        <button
          onClick={onDismiss}
          className="p-1 rounded-md text-slate-600 hover:text-slate-300 hover:bg-app-700
            transition-colors flex-shrink-0"
        >
          <X size={14} />
        </button>
      </div>
      <div className="flex gap-2 px-4 pb-4">{actions}</div>
    </div>
  )
}

const primaryBtn = `flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700
  text-white text-xs font-medium transition-colors`
const ghostBtn = `px-4 py-2 rounded-lg text-xs text-slate-500 hover:text-slate-300
  hover:bg-app-700 transition-colors`

/**
 * Global floating engine notices: automatic stop on inactivity and
 * start failures (LLM provider unavailable, etc.).
 */
export function EngineNotices() {
  const { autoStopped, dismissAutoStop, lastError, clearError, startEngine } = useEngine()
  const { config } = useConfig()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  if (!autoStopped && !lastError) return null

  return (
    <div className="fixed bottom-5 right-5 z-50 w-96 space-y-3 animate-pop-in">
      {lastError && (
        <NoticeCard
          tone="error"
          icon={AlertOctagon}
          title="Could not start the engine"
          onDismiss={clearError}
          actions={
            <>
              {pathname !== '/config' && (
                <button onClick={() => { clearError(); navigate('/config') }} className={primaryBtn}>
                  <SlidersHorizontal size={12} />
                  Go to Configuration
                </button>
              )}
              <button onClick={clearError} className={ghostBtn}>Close</button>
            </>
          }
        >
          {lastError}
        </NoticeCard>
      )}

      {autoStopped && (
        <NoticeCard
          tone="warning"
          icon={PowerOff}
          title="Engine stopped automatically"
          onDismiss={dismissAutoStop}
          actions={
            <>
              <button
                onClick={() => { dismissAutoStop(); startEngine(config) }}
                className={primaryBtn}
              >
                <Play size={12} />
                Start again
              </button>
              <button onClick={dismissAutoStop} className={ghostBtn}>Got it</button>
            </>
          }
        >
          No browser activity was detected for 5 minutes (machine
          suspended or tab closed?), so the engine was stopped to
          free up resources.
        </NoticeCard>
      )}
    </div>
  )
}
