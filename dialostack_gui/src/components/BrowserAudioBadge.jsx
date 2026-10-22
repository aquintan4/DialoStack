/** Sidebar pill for browser audio routing: mic state, plus the click to unlock sound. */
import { useBrowserAudio } from '../contexts/BrowserAudioContext'
import { BROWSER_AUDIO_STATUS } from '../lib/status'
import { StatusBadge } from './ui'

export function BrowserAudioBadge() {
  const { state, resume } = useBrowserAudio()
  const c = BROWSER_AUDIO_STATUS[state]
  if (!c) return null
  if (state === 'suspended') {
    return (
      <button type="button" onClick={resume} className="w-full text-left" title={c.title}>
        <StatusBadge {...c} />
      </button>
    )
  }
  return <div title={c.title}><StatusBadge {...c} /></div>
}
