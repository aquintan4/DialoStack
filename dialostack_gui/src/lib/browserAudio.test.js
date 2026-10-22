import { describe, expect, it } from 'vitest'
import { Downsampler, floatToS16leBase64, s16leToFloat } from './browserAudio'

describe('Downsampler', () => {
  it('turns 48 kHz into a third as many samples, averaging each group', () => {
    const out = new Downsampler(48000).push(Float32Array.from([0, 0.3, 0.6, 1, 1, 1]))
    expect(Array.from(out)).toEqual([expect.closeTo(0.3, 6), expect.closeTo(1, 6)])
  })

  it('keeps the remainder between pushes, so chunking does not change the output', () => {
    const input = Float32Array.from({ length: 4410 }, (_, i) => Math.sin(i / 7))
    const whole = new Downsampler(44100).push(input)

    const split = new Downsampler(44100)
    const parts = [split.push(input.subarray(0, 1000)), split.push(input.subarray(1000))]
    const joined = Float32Array.from(parts.flatMap((p) => Array.from(p)))

    expect(joined.length).toBe(whole.length)
    joined.forEach((v, i) => expect(v).toBeCloseTo(whole[i], 6))
  })

  it('passes 16 kHz through untouched', () => {
    const input = Float32Array.from([0.1, -0.2, 0.3])
    expect(Array.from(new Downsampler(16000).push(input))).toEqual(Array.from(input))
  })
})

describe('S16LE conversion', () => {
  it('round-trips through the base64 form rosbridge uses', () => {
    const input = Float32Array.from([0, 0.5, -0.5, 0.999, -1])
    const back = s16leToFloat(floatToS16leBase64(input))
    back.forEach((v, i) => expect(v).toBeCloseTo(input[i], 3))
  })

  it('clips out-of-range samples instead of wrapping', () => {
    const back = s16leToFloat(floatToS16leBase64(Float32Array.from([2, -2])))
    expect(back[0]).toBeCloseTo(1, 3)
    expect(back[1]).toBe(-1)
  })

  it('accepts a plain byte array as well as base64', () => {
    // 0x4000 little-endian = 16384 -> 0.5
    expect(Array.from(s16leToFloat([0x00, 0x40]))).toEqual([0.5])
  })
})
