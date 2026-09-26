import { describe, expect, it } from 'vitest'
import { DEFAULT_CONFIG } from '../contexts/ConfigContext'
import {
  applyProfileConfig, describeProfile, matchesProfile,
  profileFromJson, profileToJson, snapshotConfig,
} from './configProfiles'

const english = {
  ...DEFAULT_CONFIG,
  dialog: { ...DEFAULT_CONFIG.dialog, language: 'English', timeout_prompt: 'Are you still there?' },
  stt: { ...DEFAULT_CONFIG.stt, language: 'en' },
  tts: { ...DEFAULT_CONFIG.tts, model_path: '/models/en_US-lessac-medium.onnx' },
  llm: { ...DEFAULT_CONFIG.llm, gemini_api_key: 'secret-en' },
}

describe('snapshotConfig', () => {
  it('never stores the API key', () => {
    expect(snapshotConfig(english).llm.gemini_api_key).toBeUndefined()
    expect(english.llm.gemini_api_key).toBe('secret-en') // input untouched
  })
})

describe('applyProfileConfig', () => {
  it('switches language, STT and TTS in one go and keeps the current key', () => {
    const current = { ...DEFAULT_CONFIG, llm: { ...DEFAULT_CONFIG.llm, gemini_api_key: 'mine' } }
    const next = applyProfileConfig(current, snapshotConfig(english))
    expect(next.dialog.language).toBe('English')
    expect(next.stt.language).toBe('en')
    expect(next.tts.model_path).toBe('/models/en_US-lessac-medium.onnx')
    expect(next.llm.gemini_api_key).toBe('mine')
  })

  it('fills sections and keys missing from an old profile with defaults', () => {
    const next = applyProfileConfig({}, { stt: { language: 'en' } })
    expect(next.stt.language).toBe('en')
    expect(next.stt.model_size).toBe(DEFAULT_CONFIG.stt.model_size)
    expect(next.audio).toEqual(DEFAULT_CONFIG.audio)
  })
})

describe('matchesProfile', () => {
  it('ignores secrets and detects real changes', () => {
    const profile = snapshotConfig(english)
    const current = applyProfileConfig({ llm: { gemini_api_key: 'other' } }, profile)
    expect(matchesProfile(current, profile)).toBe(true)
    current.stt = { ...current.stt, language: 'fr' }
    expect(matchesProfile(current, profile)).toBe(false)
  })
})

describe('describeProfile', () => {
  it('summarises language, STT language, provider and voice', () => {
    expect(describeProfile(english)).toBe('English · en · gemini · en_US-lessac-medium')
  })
})

describe('profile JSON', () => {
  it('round-trips without leaking the key', () => {
    const text = profileToJson({ name: 'English', config: english })
    expect(text).not.toContain('secret-en')
    const back = profileFromJson(text)
    expect(back.name).toBe('English')
    expect(back.config.stt.language).toBe('en')
  })

  it('accepts a bare config object and drops unknown sections', () => {
    const back = profileFromJson(JSON.stringify({ stt: { language: 'en' }, junk: 1 }), 'x')
    expect(back).toEqual({ name: 'x', config: { stt: { language: 'en' } } })
  })

  it('rejects files that are not a profile', () => {
    expect(() => profileFromJson('nope')).toThrow(/valid JSON/)
    expect(() => profileFromJson('{"foo":1}')).toThrow(/known configuration/)
  })
})
