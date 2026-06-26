/**
 * Transient status message ("toast"): call flash(msg) and it auto-clears after
 * `duration` ms. Re-arms cleanly on rapid calls. Used by the editor toolbars.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export function useFlash(duration = 2500) {
  const [message, setMessage] = useState(null)
  const timer = useRef(null)

  const flash = useCallback((msg) => {
    setMessage(msg)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setMessage(null), duration)
  }, [duration])

  useEffect(() => () => clearTimeout(timer.current), [])

  return { message, flash }
}
