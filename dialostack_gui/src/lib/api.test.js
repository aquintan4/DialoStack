/** Tests for the api client: success path and error-kind mapping. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { api, ApiError } from './api'

const mockFetch = (impl) => { global.fetch = vi.fn(impl) }
afterEach(() => { vi.restoreAllMocks() })

describe('request: success and error mapping', () => {
  it('returns the JSON on an ok response', async () => {
    mockFetch(async () => ({ ok: true, json: async () => ({ state: 'running' }) }))
    await expect(api.engineStatus()).resolves.toEqual({ state: 'running' })
  })

  it('an HTTP !ok response is ApiError kind "http" with the status', async () => {
    mockFetch(async () => ({ ok: false, status: 503, json: async () => ({}) }))
    await expect(api.engineStatus()).rejects.toMatchObject({ name: 'ApiError', kind: 'http', status: 503 })
  })

  it('an abort (timeout) maps to kind "timeout"', async () => {
    mockFetch(async () => { const e = new Error('aborted'); e.name = 'AbortError'; throw e })
    await expect(api.engineStatus()).rejects.toMatchObject({ kind: 'timeout' })
  })

  it('a network failure maps to kind "network"', async () => {
    mockFetch(async () => { throw new TypeError('Failed to fetch') })
    await expect(api.engineStatus()).rejects.toBeInstanceOf(ApiError)
    mockFetch(async () => { throw new TypeError('Failed to fetch') })
    await expect(api.engineStatus()).rejects.toMatchObject({ kind: 'network' })
  })

  it('a non-JSON body maps to kind "parse"', async () => {
    mockFetch(async () => ({ ok: true, json: async () => { throw new SyntaxError('bad') } }))
    await expect(api.engineStatus()).rejects.toMatchObject({ kind: 'parse' })
  })
})

describe('request: passes the AbortController signal', () => {
  it('fetch receives an AbortSignal (for the timeout)', async () => {
    const spy = vi.fn(async () => ({ ok: true, json: async () => ({}) }))
    mockFetch(spy)
    await api.engineKeepalive()
    expect(spy.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal)
  })
})
