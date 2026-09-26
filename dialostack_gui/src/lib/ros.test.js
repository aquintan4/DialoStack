import { describe, expect, it } from 'vitest'
import { uuidBytes } from './ros'

const BYTES = [192, 77, 228, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 255]
const B64 = btoa(String.fromCharCode(...BYTES))

describe('uuidBytes', () => {
  it('decodes the base64 string rosbridge sends for uint8[16]', () => {
    // Regression: the string used to be split into characters, so rosbridge
    // failed with "invalid literal for int()" and the cancel never arrived.
    expect(uuidBytes(JSON.stringify(B64))).toEqual(BYTES)
  })

  it('accepts a plain byte array and an index-keyed object', () => {
    expect(uuidBytes(JSON.stringify(BYTES))).toEqual(BYTES)
    expect(uuidBytes(JSON.stringify({ ...BYTES }))).toEqual(BYTES)
  })

  it('rejects anything that is not a 16-byte uuid', () => {
    expect(uuidBytes('not json')).toBeNull()
    expect(uuidBytes(JSON.stringify('%%%'))).toBeNull()
    expect(uuidBytes(JSON.stringify([1, 2, 3]))).toBeNull()
    expect(uuidBytes(JSON.stringify(null))).toBeNull()
  })
})
