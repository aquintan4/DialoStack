import { useEffect, useState } from 'react'

/**
 * Like useState, but the value survives unmounts and reloads
 * (backed by localStorage). Use it for form drafts that the user
 * must not lose when switching tabs.
 */
export function usePersistentState(key, defaultValue) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw != null ? JSON.parse(raw) : defaultValue
    } catch {
      return defaultValue
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // storage full or blocked - the draft simply does not persist
    }
  }, [key, value])

  return [value, setValue]
}
