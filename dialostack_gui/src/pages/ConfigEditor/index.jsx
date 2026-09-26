/** Configuration page: engine panel, tabbed parameter editor, YAML export and reset. */
import { useState } from 'react'
import { Check, Copy, MessagesSquare, Mic, Moon, Radio, RotateCcw, Sparkles, Sun, Volume2, X } from 'lucide-react'
import { useConfig } from '../../contexts/ConfigContext'
import { useTheme } from '../../hooks/useTheme'
import { api } from '../../lib/api'
import { EnginePanel } from './EnginePanel'
import { ProfileBar } from './ProfileBar'
import { LLMTab } from './LLMTab'
import { DialogTab } from './DialogTab'
import { STTTab } from './STTTab'
import { TTSTab } from './TTSTab'
import { AudioTab } from './AudioTab'

const TABS = [
  { id: 'llm',    label: 'LLM',     icon: Sparkles       },
  { id: 'dialog', label: 'Dialogue', icon: MessagesSquare },
  { id: 'stt',    label: 'STT',     icon: Mic            },
  { id: 'tts',    label: 'TTS',     icon: Volume2        },
  { id: 'audio',  label: 'Audio',   icon: Radio          },
]

const THEME_OPTIONS = [
  { id: 'light', label: 'Light', icon: Sun  },
  { id: 'dark',  label: 'Dark',  icon: Moon },
]

/** Light/dark segmented switch for the page header. */
function ThemeSwitch() {
  const [theme, setTheme] = useTheme()
  return (
    <div className="flex items-center p-0.5 rounded border border-app-border" title="Interface theme">
      {THEME_OPTIONS.map(({ id, label, icon: Icon }) => (
        <button key={id} onClick={() => setTheme(id)}
          className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-sm transition-colors ${
            theme === id
              ? 'bg-app-700 text-slate-100'
              : 'text-slate-500 hover:text-slate-300'
          }`}>
          <Icon size={12} />
          {label}
        </button>
      ))}
    </div>
  )
}

export function ConfigEditor() {
  const { config, updateSection, resetConfig } = useConfig()
  const [activeTab, setActiveTab] = useState('llm')
  const [copyState, setCopyState] = useState('idle')   // 'idle' | 'copied' | 'failed'
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  // The YAML is generated on the server - same source of truth as the
  // engine start, so what is exported always matches what runs.
  async function copyYaml() {
    try {
      const { yaml } = await api.configYaml(config)
      await navigator.clipboard.writeText(yaml)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
    setTimeout(() => setCopyState('idle'), 2500)
  }

  function handleReset() {
    if (!showResetConfirm) { setShowResetConfirm(true); return }
    resetConfig()
    setShowResetConfirm(false)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <div className="h-12 flex items-center justify-between px-6 border-b border-app-border bg-app-900 flex-shrink-0">
        <div>
          <h1 className="text-sm font-semibold text-slate-100">Configuration</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Tune the parameters and start the engine
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitch />
          <button onClick={copyYaml}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200
              px-3 py-1.5 rounded-lg hover:bg-app-700 border border-app-border transition-all">
            {copyState === 'copied' && <Check size={13} className="text-green-400" />}
            {copyState === 'failed' && <X size={13} className="text-red-400" />}
            {copyState === 'idle' && <Copy size={13} />}
            {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Export YAML'}
          </button>
          <button onClick={handleReset} onBlur={() => setShowResetConfirm(false)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
              showResetConfirm
                ? 'text-red-400 border-red-700/50 bg-red-900/20'
                : 'text-slate-500 border-transparent hover:text-red-400 hover:bg-app-700 hover:border-app-border'
            }`}>
            <RotateCcw size={13} />
            {showResetConfirm ? 'Confirm?' : 'Reset'}
          </button>
        </div>
      </div>

      {/* Scrollable content: engine + tabs + cards */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-4">

          <EnginePanel />

          <ProfileBar />

          {/* Tab bar */}
          <div className="flex gap-1 p-1 bg-app-800 rounded-xl border border-app-border sticky top-0 z-10">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setActiveTab(id)}
                className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg
                  text-xs font-medium transition-all ${
                  activeTab === id
                    ? 'bg-app-600 text-slate-100 shadow-sm'
                    : 'text-slate-500 hover:text-slate-300'
                }`}>
                <Icon size={13} className={activeTab === id ? 'text-brand-400' : ''} />
                {label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="pb-8">
            {activeTab === 'llm'    && <LLMTab    llm={config.llm}       update={v => updateSection('llm', v)}    />}
            {activeTab === 'dialog' && <DialogTab dialog={config.dialog} update={v => updateSection('dialog', v)} />}
            {activeTab === 'stt'    && <STTTab    stt={config.stt}       update={v => updateSection('stt', v)}    />}
            {activeTab === 'tts'    && <TTSTab    tts={config.tts}       update={v => updateSection('tts', v)}    />}
            {activeTab === 'audio'  && <AudioTab  audio={config.audio}   update={v => updateSection('audio', v)}  />}
          </div>
        </div>
      </div>
    </div>
  )
}
