/**
 * Subscribe to a single image topic and surface the latest frame.
 *
 * CompressedImage arrives as base64 bytes that go straight into an <img> via a
 * data URL. Raw Image is decoded here into the caller's <canvas> (common
 * encodings only: rgb8/bgr8/rgba8/bgra8/mono8). The subscription is throttled
 * server-side (rosbridge throttle_rate) so this debug view never floods the
 * socket; it only runs while `active` is true, so a hidden panel costs nothing.
 */
import { useEffect, useRef, useState } from 'react'
import ROSLIB from 'roslib'
import { useROS } from '../contexts/ROSContext'

// ~10 fps cap. This is a debugging peek, not a video wall, and raw frames are
// heavy over the websocket; throttling keeps the browser and the link healthy.
const THROTTLE_MS = 100

const EMPTY = { src: null, width: 0, height: 0, fps: 0, count: 0, error: null }

// Channels per supported encoding (used to fall back when `step` is absent).
const CHANNELS = { rgb8: 3, bgr8: 3, rgba8: 4, bgra8: 4, mono8: 1 }

// Decode a raw sensor_msgs/Image into the canvas. Returns an error string on an
// unsupported encoding (or null on success).
function drawRaw(canvas, msg) {
  const { width, height, encoding } = msg
  if (!width || !height) return 'Empty frame'
  const channels = CHANNELS[encoding]
  if (!channels) return `Unsupported encoding: ${encoding || 'unknown'}`

  // rosbridge sends uint8[] as a base64 string.
  const bin = atob(msg.data)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)

  const ctx = canvas.getContext('2d')
  const out = ctx.createImageData(width, height)
  const px = out.data
  const step = msg.step || width * channels

  for (let y = 0; y < height; y++) {
    const row = y * step
    for (let x = 0; x < width; x++) {
      const s = row + x * channels
      const d = (y * width + x) * 4
      if (channels === 1) {
        px[d] = px[d + 1] = px[d + 2] = bytes[s]
        px[d + 3] = 255
      } else if (encoding === 'bgr8' || encoding === 'bgra8') {
        px[d] = bytes[s + 2]
        px[d + 1] = bytes[s + 1]
        px[d + 2] = bytes[s]
        px[d + 3] = channels === 4 ? bytes[s + 3] : 255
      } else {
        px[d] = bytes[s]
        px[d + 1] = bytes[s + 1]
        px[d + 2] = bytes[s + 2]
        px[d + 3] = channels === 4 ? bytes[s + 3] : 255
      }
    }
  }

  canvas.width = width
  canvas.height = height
  ctx.putImageData(out, 0, 0)
  return null
}

export function useImageTopic(topic, { active, canvasRef }) {
  const { ros, status } = useROS()
  const [info, setInfo] = useState(EMPTY)
  const lastTsRef = useRef(0)
  const fpsRef = useRef(0)

  useEffect(() => {
    setInfo(EMPTY)
    lastTsRef.current = 0
    fpsRef.current = 0

    const connected = status === 'connected' || status === 'waiting'
    if (!active || !topic || !ros.current || !connected) return

    const sub = new ROSLIB.Topic({
      ros: ros.current,
      name: topic.name,
      messageType: topic.type,
      throttle_rate: THROTTLE_MS,
      queue_length: 1,
    })

    let count = 0
    const handler = (msg) => {
      // Smoothed frame rate (EMA) from inter-arrival time.
      const now = Date.now()
      if (lastTsRef.current) {
        const dt = now - lastTsRef.current
        if (dt > 0) {
          const inst = 1000 / dt
          fpsRef.current = fpsRef.current ? fpsRef.current * 0.7 + inst * 0.3 : inst
        }
      }
      lastTsRef.current = now
      count++
      const fps = Math.round(fpsRef.current)

      if (topic.kind === 'compressed') {
        const fmt = (msg.format || '').toLowerCase().includes('png') ? 'png' : 'jpeg'
        setInfo((p) => ({ ...p, src: `data:image/${fmt};base64,${msg.data}`, fps, count, error: null }))
      } else {
        const canvas = canvasRef.current
        if (!canvas) return
        const error = drawRaw(canvas, msg)
        setInfo((p) => ({
          ...p,
          src: null,
          width: msg.width || 0,
          height: msg.height || 0,
          fps,
          count,
          error,
        }))
      }
    }

    sub.subscribe(handler)
    return () => sub.unsubscribe(handler)
  }, [active, topic, status, ros, canvasRef])

  return info
}
