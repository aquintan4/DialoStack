/**
 * Configuration context: holds the engine config (LLM, dialogue, STT, TTS,
 * prompt overrides), persisting it to localStorage and exposing per-section
 * update/reset helpers.
 */
import { createContext, useContext, useState, useCallback } from 'react'
import { STORAGE } from '../lib/storageKeys'

export const DEFAULT_CONFIG = {
  llm: {
    provider: 'gemini',
    model: 'gemini-2.5-flash',
    timeout: 60,
    max_concurrent: 4,
    silent_mode: false,
    gemini_api_key: '',
    ollama_host: '127.0.0.1',
    ollama_port: 11434,
  },
  dialog: {
    language: 'Spanish',
    wait_timeout: 20,
    llm_timeout: 120,
    tts_timeout: 60,
    max_timeouts: 2,
    max_unclear: 3,
    max_attempts: 3,
    timeout_prompt: '¿Sigues ahí?',
    history_max_turns: 200,
    ack_phrases: ['Anotado.', 'Hecho.', 'Perfecto.', 'Entendido.', 'De acuerdo.'],
    silent_mode: false,
    conversation_log_path: '/tmp/dialog_conversations.log',
    conversation_log_max_mb: 10.0,
  },
  stt: {
    model_size: 'small',
    device: 'cpu',
    compute_type: 'int8',
    language: 'es',
    vad_threshold: 0.5,
    grace_period: 0.8,
    max_phrase_secs: 8.0,
    cpu_threads: 4,
    sample_rate: 16000,
    input_device: '',
    silent_mode: false,
  },
  tts: {
    model_path: '',
    sample_rate: 22050,
    audio_device: 'default',
  },
  // Prompt overrides: { <key>: template }. Only contains the prompts the user
  // has modified; the rest always come from prompts.yaml (the defaults).
  prompts: {},
}

const LS_KEY = STORAGE.config

function loadConfig() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return DEFAULT_CONFIG
    const parsed = JSON.parse(raw)
    return Object.fromEntries(
      Object.entries(DEFAULT_CONFIG).map(([section, defaults]) => [
        section,
        { ...defaults, ...(parsed[section] ?? {}) },
      ])
    )
  } catch {
    return DEFAULT_CONFIG
  }
}

const ConfigContext = createContext(null)

export function ConfigProvider({ children }) {
  const [config, setConfig] = useState(loadConfig)

  const updateSection = useCallback((section, values) => {
    setConfig(prev => {
      const next = { ...prev, [section]: { ...prev[section], ...values } }
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)) } catch {}
      return next
    })
  }, [])

  const resetConfig = useCallback(() => {
    try { localStorage.removeItem(LS_KEY) } catch {}
    setConfig(DEFAULT_CONFIG)
  }, [])

  return (
    <ConfigContext.Provider value={{ config, updateSection, resetConfig }}>
      {children}
    </ConfigContext.Provider>
  )
}

export function useConfig() {
  const ctx = useContext(ConfigContext)
  if (!ctx) throw new Error('useConfig must be used within ConfigProvider')
  return ctx
}
