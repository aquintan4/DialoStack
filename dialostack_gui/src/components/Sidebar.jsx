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
          className="p-2 rounded-lg bg-red-900/30 border border-red-700/50 text-red-400
            hover:bg-red-900/50 transition-colors flex-shrink-0"
        >
          <Square size={13} />
        </button>
      )}
      {(state === 'stopped' || state === 'error') && (
        <button
          onClick={() => startEngine(config)}
          title="Start engine"
          className="p-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white
            transition-colors flex-shrink-0"
        >
          <Play size={13} />
        </button>
      )}
    </div>
  )
}

export function Sidebar() {
  return (
    <aside className="w-56 flex-shrink-0 h-screen flex flex-col bg-app-900 border-r border-app-border">

      {/* Brand - symbol and wordmark derived from the official logo
          (public/logo-mark.png and public/logo-wordmark-white.png) */}
      <div className="px-4 py-5 border-b border-app-border">
        <div className="flex flex-col items-center gap-3">
          <img src="/logo-mark.png" alt="" className="w-24 h-24" />
          <img src="/logo-wordmark-white.png" alt="DialoStack" className="h-[22px] w-auto" />
          <p className="text-[10px] text-slate-500 -mt-1">GUI · v1.0</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {PAGES.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 ${
                isActive
                  ? 'bg-brand-glow border border-brand-600/40 text-brand-400'
                  : 'text-slate-400 hover:bg-app-700 hover:text-slate-200 border border-transparent'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={16}
                  className={`flex-shrink-0 transition-colors ${
                    isActive ? 'text-brand-400' : 'text-slate-500 group-hover:text-slate-300'
                  }`}
                />
                <span className="text-sm font-medium truncate">{label}</span>
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
