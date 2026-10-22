/**
 * Browser audio: the GUI page as DialoStack's microphone and speaker.
 *
 * Speaks the same AudioChunk contract as a robot or the audio_bridge_node:
 * the microphone is captured, resampled to 16 kHz S16LE mono and published on
 * the input topic; TTS audio from the output topic is played back. The browser
 * provides echo cancellation, so no host audio setup (PulseAudio, WSLg) is
 * involved at all.
 *
 * The pure helpers below (resampling, PCM <-> base64) carry the logic and are
 * unit-tested; BrowserAudio only wires them to the Web Audio API.
 */

export const STT_RATE = 16000
// Samples per published chunk: 100 ms at 16 kHz.
const CHUNK_SAMPLES = 1600
// Scheduling lead so back-to-back TTS chunks play without gaps.
const PLAY_LEAD_S = 0.08

// ==== PURE HELPERS ====

/**
 * Streaming downsampler (e.g. 48 kHz -> 16 kHz). Each output sample averages
 * the input samples it covers, a box filter that is enough anti-aliasing for
 * speech. State carries over between push() calls, so chunk boundaries do not
 * click.
 */
export class Downsampler {
  constructor(inRate, outRate = STT_RATE) {
    this.inRate = Math.round(inRate)
    this.outRate = outRate
    // Integer bookkeeping (outputs produced, inputs dropped) keeps the sample
    // boundaries exact however the input is chunked.
    this.produced = 0
    this.dropped = 0
    this.buf = new Float32Array(0)
  }

  // Absolute input index where output sample n starts.
  _edge(n) {
    return Math.floor((n * this.inRate) / this.outRate)
  }

  push(input) {
    const buf = new Float32Array(this.buf.length + input.length)
    buf.set(this.buf)
    buf.set(input, this.buf.length)

    const out = []
    for (;;) {
      const start = this._edge(this.produced) - this.dropped
      // At least one input sample per output, should a device run below 16 kHz.
      const end = Math.max(this._edge(this.produced + 1) - this.dropped, start + 1)
      if (end > buf.length) break
      let sum = 0
      for (let i = start; i < end; i++) sum += buf[i]
      out.push(sum / (end - start))
      this.produced++
    }
    const keep = this._edge(this.produced) - this.dropped
    this.buf = buf.slice(keep)
    this.dropped += keep
    return Float32Array.from(out)
  }
}

/** Float samples in [-1, 1] -> base64 of S16LE bytes (rosbridge's uint8[] form). */
export function floatToS16leBase64(samples) {
  const bytes = new Uint8Array(samples.length * 2)
  const view = new DataView(bytes.buffer)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}

/**
 * AudioChunk.data as rosbridge delivers it (base64 string, or a plain byte
 * array) -> float samples in [-1, 1].
 */
export function s16leToFloat(data) {
  const bytes = typeof data === 'string'
    ? Uint8Array.from(atob(data), (c) => c.charCodeAt(0))
    : Uint8Array.from(data ?? [])
  const view = new DataView(bytes.buffer)
  const out = new Float32Array(bytes.length >> 1)
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 0x8000
  return out
}

// ==== WEB AUDIO ====

// The capture worklet just forwards each 128-sample render quantum to the page.
const CAPTURE_WORKLET = `
class DialoStackCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch) this.port.postMessage(ch.slice(0))
    return true
  }
}
registerProcessor('dialostack-capture', DialoStackCapture)
`

/** True when the page may use the microphone (localhost or HTTPS). */
export function micSupported() {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

/**
 * One live microphone + speaker session. onChunk(base64) receives each
 * captured 100 ms chunk; play() queues TTS audio; flush() drops whatever is
 * still queued (barge-in, end of turn).
 */
export class BrowserAudio {
  constructor(onChunk) {
    this.onChunk = onChunk
    this.ctx = null
    this.stream = null
    this.sources = new Set()
    this.playhead = 0
    this.pending = []
    this.pendingLen = 0
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    this.ctx = new AudioContext()
    const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'application/javascript' }))
    try {
      await this.ctx.audioWorklet.addModule(url)
    } finally {
      URL.revokeObjectURL(url)
    }

    const down = new Downsampler(this.ctx.sampleRate)
    const node = new AudioWorkletNode(this.ctx, 'dialostack-capture')
    node.port.onmessage = (e) => this._collect(down.push(e.data))
    this.ctx.createMediaStreamSource(this.stream).connect(node)
  }

  /** 'running' or 'suspended' (the browser waits for a click to allow sound). */
  get state() {
    return this.ctx?.state ?? 'closed'
  }

  resume() {
    return this.ctx?.resume()
  }

  _collect(samples) {
    if (!samples.length) return
    this.pending.push(samples)
    this.pendingLen += samples.length
    if (this.pendingLen < CHUNK_SAMPLES) return
    const chunk = new Float32Array(this.pendingLen)
    let off = 0
    for (const s of this.pending) { chunk.set(s, off); off += s.length }
    this.pending = []
    this.pendingLen = 0
    this.onChunk(floatToS16leBase64(chunk))
  }

  play(samples, sampleRate) {
    if (!this.ctx || !samples.length) return
    const buffer = this.ctx.createBuffer(1, samples.length, sampleRate)
    buffer.copyToChannel(samples, 0)
    const src = this.ctx.createBufferSource()
    src.buffer = buffer
    src.connect(this.ctx.destination)
    const at = Math.max(this.playhead, this.ctx.currentTime + PLAY_LEAD_S)
    src.start(at)
    this.playhead = at + buffer.duration
    this.sources.add(src)
    src.onended = () => this.sources.delete(src)
  }

  flush() {
    for (const src of this.sources) {
      try { src.stop() } catch { /* already stopped */ }
    }
    this.sources.clear()
    this.playhead = 0
  }

  close() {
    this.flush()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.ctx?.close()
    this.ctx = null
    this.stream = null
  }
}
