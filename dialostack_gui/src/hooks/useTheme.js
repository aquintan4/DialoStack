/**
 * UI theme (light/dark), persisted in localStorage and applied as the
 * data-theme attribute on <html>. The colors themselves live in
 * tailwind.config.js as CSS variables; this hook only flips the attribute.
 * Light is the default. index.html applies the saved theme before React
 * mounts, so only the switch in Configuration needs this hook.
 */
import { useEffect } from 'react'
import { usePersistentState } from './usePersistentState'
import { STORAGE } from '../lib/storageKeys'

export const THEMES = ['light', 'dark']

export function useTheme() {
  const [theme, setTheme] = usePersistentState(STORAGE.theme, 'light')

  useEffect(() => {
    document.documentElement.dataset.theme = THEMES.includes(theme) ? theme : 'light'
  }, [theme])

  return [theme, setTheme]
}
