import { createContext, useContext, useEffect, useRef, useState } from 'react'
import ROSLIB from 'roslib'
import { DIALOG_ACTION, ROSBRIDGE_URL } from '../lib/ros'

const ROSContext = createContext(null)

const SERVER_POLL_MS = 2000
const RECONNECT_MS = 3000

/**
 * Single rosbridge connection for the whole application.
 *
 * status:
 *   'disconnected' - no WebSocket (rosbridge down)
 *   'connecting'   - opening the WebSocket
 *   'waiting'      - rosbridge connected, but the engine action server is absent
 *   'connected'    - rosbridge + engine ready
 */
export function ROSProvider({ url = ROSBRIDGE_URL, children }) {
  const [status, setStatus] = useState('disconnected')
  const rosRef = useRef(null)
  const pollTimerRef = useRef(null)

  useEffect(() => {
    let reconnectTimer = null

    function stopPolling() {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }

    // With the socket open, periodically check that the dialog manager action
    // server is advertised before declaring 'connected'.
    function startPolling(ros) {
      function poll() {
        if (rosRef.current !== ros) return
        ros.getActionServers(
          (servers) => {
            if (rosRef.current !== ros) return
            setStatus(servers.includes(DIALOG_ACTION) ? 'connected' : 'waiting')
            pollTimerRef.current = setTimeout(poll, SERVER_POLL_MS)
          },
          () => {
            if (rosRef.current !== ros) return
            setStatus('waiting')
            pollTimerRef.current = setTimeout(poll, SERVER_POLL_MS)
          }
        )
      }
      poll()
    }

    function connect() {
      const ros = new ROSLIB.Ros({ url })
      rosRef.current = ros
      setStatus('connecting')

      ros.on('connection', () => {
        setStatus('waiting')
        startPolling(ros)
      })
      ros.on('error', () => {
        stopPolling()
        setStatus('disconnected')
      })
      ros.on('close', () => {
        stopPolling()
        setStatus('disconnected')
        reconnectTimer = setTimeout(() => {
          if (rosRef.current === ros) connect()
        }, RECONNECT_MS)
      })
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      stopPolling()
      if (rosRef.current) {
        rosRef.current.close()
        rosRef.current = null
      }
    }
  }, [url])

  return (
    <ROSContext.Provider value={{ ros: rosRef, status }}>
      {children}
    </ROSContext.Provider>
  )
}

export function useROS() {
  const ctx = useContext(ROSContext)
  if (!ctx) throw new Error('useROS must be used within ROSProvider')
  return ctx
}
