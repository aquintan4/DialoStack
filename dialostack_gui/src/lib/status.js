/**
 * Presentation maps for the ROS connection and engine states.
 * Shared by Sidebar, ConnectionBadge and EnginePanel so the same state always
 * renders identically across the application.
 */

export const ROS_STATUS = {
  connected:    { dot: 'bg-green-500',                text: 'text-green-400',  label: 'ROS connected'      },
  waiting:      { dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-400', label: 'Waiting for engine…' },
  connecting:   { dot: 'bg-slate-400 animate-pulse',  text: 'text-slate-400',  label: 'Connecting…'        },
  disconnected: { dot: 'bg-red-500',                  text: 'text-red-400',    label: 'No rosbridge'       },
}

export const ENGINE_STATUS = {
  stopped:  { dot: 'bg-slate-500',                text: 'text-slate-400',  label: 'Engine stopped', border: 'border-app-border'    },
  starting: { dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-400', label: 'Starting…',      border: 'border-yellow-700/50' },
  running:  { dot: 'bg-green-500',                text: 'text-green-400',  label: 'Running',        border: 'border-green-700/40'  },
  error:    { dot: 'bg-red-500',                  text: 'text-red-400',    label: 'Engine error',   border: 'border-red-700/50'   },
}
