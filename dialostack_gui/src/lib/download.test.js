/** Tests for fileStamp: default and seconds-omitted file name timestamps. */
import { describe, it, expect } from 'vitest'
import { fileStamp } from './download'

describe('fileStamp', () => {
  const d = new Date('2026-06-14T09:05:03')

  it('formats YYYYMMDD-HHMMSS by default', () => {
    expect(fileStamp(d)).toBe('20260614-090503')
  })

  it('can omit the seconds', () => {
    expect(fileStamp(d, false)).toBe('20260614-0905')
  })
})
