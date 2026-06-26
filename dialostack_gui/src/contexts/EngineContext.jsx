/**
 * Engine context: polls the GUI server for engine status, sends keepalives so
 * the server watchdog keeps the engine alive, and exposes start/stop plus
 * error and auto-stop notices.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const EngineContext = createContext(null)
const POLL_MS = 2500
const KEEPALIVE_MS = 10_000

export function EngineProvider({ children }) {
  const [engineState, setEngineState] = useState({ state: 'stopped', pid: null, stop_reason: null })
  const [lastError, setLastError] = useState(null)
  // The engine stopped on its own (server watchdog) - triggers the UI notice
  const [autoStopped, setAutoStopped] = useState(false)
  // While a start/stop is in flight, poll results are potentially older than
  // the request - discard them.
  const busyRef = useRef(false)
  const prevStateRef = useRef('stopped')

  useEffect(() => {
    let active = true
    async function poll() {
      try {
        const status = await api.engineStatus()
        if (!active || busyRef.current) return
        const wasAlive = prevStateRef.current === 'running' || prevStateRef.current === 'starting'
        if (wasAlive && status.state === 'stopped' && status.stop_reason === 'watchdog') {
          setAutoStopped(true)
        }
        prevStateRef.current = status.state
        setEngineState(status)
      } catch {
        // GUI server down - retried on the next cycle
      }
    }
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { active = false; clearInterval(id) }
  }, [])

  // Keepalive: the server watchdog stops the engine if the browser goes away.
  // On returning to the foreground one is sent immediately, because browsers
  // throttle the intervals of background tabs.
  useEffect(() => {
    const send = () => api.engineKeepalive().catch(() => {})
    send()
    const id = setInterval(send, KEEPALIVE_MS)
    const onVisible = () => { if (!document.hidden) send() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  const startEngine = useCallback(async (config) => {
    busyRef.current = true
    setLastError(null)
    setAutoStopped(false)
    setEngineState((prev) => ({ ...prev, state: 'starting' }))
    prevStateRef.current = 'starting'
    try {
      const data = await api.engineStart(config)
      if (!data.ok) {
        setLastError(data.error || 'Unknown failure while starting')
        setEngineState((prev) => ({ ...prev, state: 'error' }))
        prevStateRef.current = 'error'
      }
    } catch (err) {
      setLastError(err?.kind === 'timeout'
        ? 'The GUI server is not responding (timeout)'
        : 'No connection to the GUI server')
      setEngineState((prev) => ({ ...prev, state: 'error' }))
      prevStateRef.current = 'error'
    } finally {
      busyRef.current = false
    }
  }, [])

  const stopEngine = useCallback(async () => {
    busyRef.current = true
    try {
      await api.engineStop()
      setEngineState((prev) => ({ ...prev, state: 'stopped', pid: null }))
      prevStateRef.current = 'stopped'
    } catch {
      setLastError('No connection to the GUI server')
    } finally {
      busyRef.current = false
    }
  }, [])

  // Panic button: kill every DialoStack process (engine, LLM, speech, vision,
  // NAO) across terminals, not just the GUI-launched engine. Returns the server
  // report ({ ok, count, ... }) so the caller can surface how many were killed.
  const killAll = useCallback(async () => {
    busyRef.current = true
    setAutoStopped(false)
    try {
      const data = await api.killAll()
      setEngineState((prev) => ({ ...prev, state: 'stopped', pid: null }))
      prevStateRef.current = 'stopped'
      if (data && data.ok === false) setLastError(data.error || 'Could not kill the processes')
      return data
    } catch (err) {
      setLastError(err?.kind === 'timeout'
        ? 'The GUI server is not responding (timeout)'
        : 'No connection to the GUI server')
      return { ok: false }
    } finally {
      busyRef.current = false
    }
  }, [])

  const dismissAutoStop = useCallback(() => setAutoStopped(false), [])
  const clearError = useCallback(() => setLastError(null), [])

  return (
    <EngineContext.Provider
      value={{ engineState, lastError, clearError, autoStopped, dismissAutoStop, startEngine, stopEngine, killAll }}
    >
      {children}
    </EngineContext.Provider>
  )
}

export function useEngine() {
  const ctx = useContext(EngineContext)
  if (!ctx) throw new Error('useEngine must be used within EngineProvider')
  return ctx
}
