/**
 * Browser audio context: while the audio routing is "browser" and the engine
 * is up, this page is the robot's microphone and speaker (lib/browserAudio).
 * Exposes the session state for the sidebar badge and resume() for browsers
 * that only allow sound after a click.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import ROSLIB from 'roslib'
import { useROS } from './ROSContext'
import { useConfig } from './ConfigContext'
import { BrowserAudio, STT_RATE, micSupported, s16leToFloat } from '../lib/browserAudio'
import { AUDIO_CHUNK_TYPE, TOPICS } from '../lib/ros'

const BrowserAudioContext = createContext(null)

/**
 * state:
 *   'off'         - routing is not "browser", or the engine is not up
 *   'starting'    - asking for the microphone
 *   'suspended'   - live, but the browser wants a click before playing sound
 *   'live'        - capturing and playing
 *   'blocked'     - microphone permission denied
 *   'unsupported' - page not on localhost/HTTPS, so no microphone API
 */
export function BrowserAudioProvider({ children }) {
  const { ros, status } = useROS()
  const { config } = useConfig()
  const [state, setState] = useState('off')
  const audioRef = useRef(null)

  const { mode, in_topic: inTopic, out_topic: outTopic } = config.audio
  const active = mode === 'browser' && status === 'connected'

  useEffect(() => {
    if (!active || !ros.current) {
      setState('off')
      return
    }
    if (!micSupported()) {
      setState('unsupported')
      return
    }

    let cancelled = false
    const rosInstance = ros.current
    const pub = new ROSLIB.Topic({ ros: rosInstance, name: inTopic, messageType: AUDIO_CHUNK_TYPE })
    const out = new ROSLIB.Topic({ ros: rosInstance, name: outTopic, messageType: AUDIO_CHUNK_TYPE })
    const speaking = new ROSLIB.Topic({
      ros: rosInstance, name: TOPICS.isSpeaking.name, messageType: TOPICS.isSpeaking.type,
    })

    const audio = new BrowserAudio((data) => {
      pub.publish(new ROSLIB.Message({ data, sample_rate: STT_RATE, channels: 1, encoding: 'S16LE' }))
    })
    const onOut = (msg) => audio.play(s16leToFloat(msg.data), msg.sample_rate)
    // The TTS node drops /is_speaking when an utterance ends or is cut short:
    // drop whatever is still queued so a barge-in silences the robot at once.
    const onSpeaking = (msg) => { if (!msg.data) audio.flush() }

    setState('starting')
    audio.start().then(
      () => {
        if (cancelled) return audio.close()
        audioRef.current = audio
        out.subscribe(onOut)
        speaking.subscribe(onSpeaking)
        setState(audio.state === 'running' ? 'live' : 'suspended')
      },
      (err) => {
        audio.close()
        if (!cancelled) setState(err?.name === 'NotAllowedError' ? 'blocked' : 'unsupported')
      },
    )

    return () => {
      cancelled = true
      out.unsubscribe(onOut)
      speaking.unsubscribe(onSpeaking)
      audio.close()
      audioRef.current = null
    }
  }, [active, ros, inTopic, outTopic])

  const resume = useCallback(async () => {
    const audio = audioRef.current
    if (!audio) return
    await audio.resume()
    setState(audio.state === 'running' ? 'live' : 'suspended')
  }, [])

  // A suspended context neither captures nor plays: the first click or key
  // anywhere on the page unlocks it, not only the badge's button.
  useEffect(() => {
    if (state !== 'suspended') return
    const unlock = () => { resume() }
    document.addEventListener('pointerdown', unlock)
    document.addEventListener('keydown', unlock)
    return () => {
      document.removeEventListener('pointerdown', unlock)
      document.removeEventListener('keydown', unlock)
    }
  }, [state, resume])

  return (
    <BrowserAudioContext.Provider value={{ state, resume }}>
      {children}
    </BrowserAudioContext.Provider>
  )
}

export function useBrowserAudio() {
  const ctx = useContext(BrowserAudioContext)
  if (!ctx) throw new Error('useBrowserAudio must be used within BrowserAudioProvider')
  return ctx
}
