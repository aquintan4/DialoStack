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

// Browser audio routing ('off' renders nothing). title is the hover hint.
export const BROWSER_AUDIO_STATUS = {
  starting:    { dot: 'bg-slate-400 animate-pulse',  text: 'text-slate-400',  label: 'Opening microphone…',
                 title: 'Allow microphone access when the browser asks' },
  suspended:   { dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-400', label: 'Click to enable audio',
                 title: 'The browser needs a click on the page before it captures or plays sound' },
  live:        { dot: 'bg-green-500',                text: 'text-green-400',  label: 'Browser mic live',
                 title: 'This page is the robot\'s microphone and speaker' },
  blocked:     { dot: 'bg-red-500',                  text: 'text-red-400',    label: 'Microphone blocked',
                 title: 'Allow the microphone for this site in the browser (padlock icon in the address bar)' },
  unsupported: { dot: 'bg-red-500',                  text: 'text-red-400',    label: 'No microphone access',
                 title: 'Browsers only allow the microphone on localhost or HTTPS, and need an input device' },
}
