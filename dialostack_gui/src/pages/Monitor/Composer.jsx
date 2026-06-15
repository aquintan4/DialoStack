/** Keyboard composer for the Monitor: publishes typed text as a transcription and a hardware mic mute toggle. */
import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, Send } from 'lucide-react'
import { usePublisher } from '../../hooks/usePublisher'
import { api } from '../../lib/api'
import { TOPICS } from '../../lib/ros'

const MIC_POLL_MS = 10_000

/** Hardware mute of the system microphone (PipeWire, via the GUI server). */
function MicButton() {
  const [mic, setMic] = useState({ available: false, muted: false })

  useEffect(() => {
    let active = true
    const fetchStatus = () => api.micStatus().then((s) => active && setMic(s)).catch(() => {})
    fetchStatus()
    const id = setInterval(fetchStatus, MIC_POLL_MS)
    return () => { active = false; clearInterval(id) }
  }, [])

  if (!mic.available) return null

  async function toggle() {
    try {
      setMic(await api.micMute(!mic.muted))
    } catch {
      // server not reachable - the next poll resyncs
    }
  }

  return (
    <button
      onClick={toggle}
      title={mic.muted
        ? 'Microphone muted at the system level - click to reactivate it'
        : 'Mute microphone (hardware) - useful for testing by keyboard only'}
      className={`flex items-center justify-center w-9 h-9 rounded-lg border transition-colors flex-shrink-0 ${
        mic.muted
          ? 'bg-red-900/30 border-red-700/50 text-red-400 hover:bg-red-900/50'
          : 'border-app-border text-slate-500 hover:text-slate-300 hover:bg-app-700'
      }`}
    >
      {mic.muted ? <MicOff size={15} /> : <Mic size={15} />}
    </button>
  )
}

/**
 * Text input to talk to the robot by keyboard.
 *
 * - On send, publishes the text to /transcription: for the engine it is
 *   indistinguishable from an ASR transcription.
 * - While the box has text, publishes /user_speaking = true (the dialog
 *   manager's barge-in signal) even if you stop typing - this lets you test
 *   interrupting the robot by writing.
 */
export function Composer({ rosStatus, onLocalMessage }) {
  const publishTranscription = usePublisher(TOPICS.transcription.name, TOPICS.transcription.type)
  const publishSpeaking = usePublisher(TOPICS.userSpeaking.name, TOPICS.userSpeaking.type)
  const [text, setText] = useState('')
  const speakingRef = useRef(false)

  const connected = rosStatus === 'connected'

  function setSpeaking(value) {
    if (speakingRef.current === value) return
    speakingRef.current = value
    publishSpeaking({ data: value })
  }

  // If the component unmounts (tab change) do not leave the signal stuck
  useEffect(() => () => {
    if (speakingRef.current) publishSpeaking({ data: false })
  }, [publishSpeaking])

  function handleChange(e) {
    setText(e.target.value)
    setSpeaking(e.target.value.trim().length > 0)
  }

  function send() {
    const t = text.trim()
    if (!t || !connected) return
    setSpeaking(false)
    onLocalMessage?.(t)           // render the bubble instantly (without waiting for the echo)
    publishTranscription({ data: t })
    setText('')
  }

  return (
    <div className="border-t border-app-border bg-app-900 px-4 py-3 flex items-center gap-2.5 flex-shrink-0">
      <MicButton />
      <div className="relative flex-1">
        <input
          type="text"
          value={text}
          onChange={handleChange}
          onBlur={() => setSpeaking(false)}
          onFocus={() => setSpeaking(text.trim().length > 0)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={connected
            ? 'Type instead of speaking - sent as a transcription'
            : 'No connection with the engine'}
          disabled={!connected}
          className={`w-full bg-app-800 border rounded-lg px-3 py-2 pr-32 text-sm text-slate-200
            placeholder-slate-600 focus:outline-none transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed ${
              speakingRef.current && text.trim()
                ? 'border-brand-500/60'
                : 'border-app-border focus:border-brand-600'
            }`}
        />
        {text.trim() && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5
            text-[10px] text-brand-400 font-medium pointer-events-none">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
            counting as voice
          </span>
        )}
      </div>
      <button
        onClick={send}
        disabled={!connected || !text.trim()}
        title="Send (Enter)"
        className="flex items-center justify-center w-9 h-9 rounded-lg bg-brand-600
          hover:bg-brand-700 text-white transition-colors
          disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
      >
        <Send size={14} />
      </button>
    </div>
  )
}
