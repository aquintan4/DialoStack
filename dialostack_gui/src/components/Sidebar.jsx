/** Left navigation rail: page links plus engine and connection status. */
import { NavLink } from 'react-router-dom'
import { Activity, Layers, Loader2, MessageSquareText, Play, SlidersHorizontal, Square, Workflow } from 'lucide-react'
import { ConnectionBadge } from './ConnectionBadge'
import { useConfig } from '../contexts/ConfigContext'
import { useEngine } from '../contexts/EngineContext'
import { ENGINE_STATUS } from '../lib/status'
import { StatusBadge } from './ui'

/** Adding a new section = one more entry here. */
const PAGES = [
  { path: '/monitor', label: 'Monitor',       icon: Activity          },
  { path: '/builder', label: 'Frame Builder', icon: Layers            },
  { path: '/prompts', label: 'Prompts',       icon: MessageSquareText },
  { path: '/strategies', label: 'Strategies', icon: Workflow          },
  { path: '/config',  label: 'Configuration', icon: SlidersHorizontal },
]

/** Engine status badge with built-in start/stop control, reachable
    from any page without going through Configuration. */
function EngineControl() {
  const { engineState, startEngine, stopEngine } = useEngine()
  const { config } = useConfig()
  const { state } = engineState
  const c = ENGINE_STATUS[state] ?? ENGINE_STATUS.stopped

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 min-w-0">
        <StatusBadge {...c} />
      </div>
      {state === 'starting' && (
        <span className="p-2 text-yellow-400">
          <Loader2 size={14} className="animate-spin" />
        </span>
      )}
      {state === 'running' && (
        <button
          onClick={stopEngine}
          title="Stop engine"
          className="p-2 rounded border border-app-border text-slate-400
            hover:text-red-400 hover:border-red-800/60 transition-colors flex-shrink-0"
        >
          <Square size={13} />
        </button>
      )}
      {(state === 'stopped' || state === 'error') && (
        <button
          onClick={() => startEngine(config)}
          title="Start engine"
          className="p-2 rounded border border-app-border text-slate-300
            hover:bg-app-700 hover:text-slate-100 transition-colors flex-shrink-0"
        >
          <Play size={13} />
        </button>
      )}
    </div>
  )
}

export function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 h-screen flex flex-col bg-app-900 border-r border-app-border">

      {/* Brand - symbol and wordmark from the official logo. The white
          wordmark is for the dark theme, the cyan one for the light theme. */}
      <div className="px-4 pt-6 pb-5 border-b border-app-border">
        <div className="flex flex-col items-center gap-3">
          <img src="/logo-mark.png" alt="" className="w-24 h-24" />
          <img src="/logo-wordmark-white.png" alt="DialoStack" className="h-[22px] w-auto light:hidden" />
          <img src="/logo-wordmark-cyan.png" alt="DialoStack" className="hidden light:block h-[22px] w-auto" />
          <p className="text-[10px] font-mono text-slate-500 -mt-1">GUI · v1.0</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {PAGES.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `group flex items-center gap-3.5 px-5 py-3.5 border-l-[3px] transition-colors ${
                isActive
                  ? 'bg-app-800 border-brand-500 text-slate-100'
                  : 'text-slate-400 hover:bg-app-800/60 hover:text-slate-200 border-transparent'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={19}
                  className={`flex-shrink-0 transition-colors ${
                    isActive ? 'text-slate-300' : 'text-slate-500 group-hover:text-slate-400'
                  }`}
                />
                <span className="text-[15px] font-medium truncate">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* System status */}
      <div className="p-3 border-t border-app-border space-y-1.5">
        <EngineControl />
        <ConnectionBadge />
      </div>
    </aside>
  )
}
