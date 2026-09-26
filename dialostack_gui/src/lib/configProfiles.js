/**
 * Configuration profiles: named snapshots of the whole engine config (LLM,
 * dialogue, STT, TTS, audio, prompt and phrase overrides) so switching setup
 * - typically the language, with its STT language and TTS voice model path -
 * is one click instead of editing field by field.
 *
 * Pure module (no React, no storage): the page keeps the list in
 * localStorage and calls these helpers.
 */
import { DEFAULT_CONFIG } from '../contexts/ConfigContext'

// ==== SECRETS ====
// Credentials are machine/user specific, not part of a "setup": they are never
// stored in a profile or exported, and applying a profile keeps the current ones.
export const SECRET_FIELDS = { llm: ['gemini_api_key'] }

function stripSecrets(config) {
  const out = structuredClone(config)
  for (const [section, keys] of Object.entries(SECRET_FIELDS)) {
    if (!out[section]) continue
    for (const k of keys) delete out[section][k]
  }
  return out
}

// ==== SNAPSHOT / APPLY ====

/** Profile payload for the given config (secrets removed). */
export function snapshotConfig(config) {
  return stripSecrets(config)
}

/**
 * Config that results from applying `profileConfig` on top of `current`:
 * every section comes from the profile (missing keys fall back to the
 * defaults, so profiles saved by an older GUI still load), and the secrets
 * of `current` are preserved.
 */
export function applyProfileConfig(current, profileConfig) {
  const next = Object.fromEntries(
    Object.entries(DEFAULT_CONFIG).map(([section, defaults]) => [
      section,
      { ...defaults, ...(profileConfig?.[section] ?? {}) },
    ])
  )
  for (const [section, keys] of Object.entries(SECRET_FIELDS)) {
    for (const k of keys) {
      if (current?.[section]?.[k] !== undefined) next[section][k] = current[section][k]
    }
  }
  return next
}

/** True if `config` matches the profile (ignoring secrets and key order). */
export function matchesProfile(config, profileConfig) {
  const a = snapshotConfig(applyProfileConfig({}, config))
  const b = snapshotConfig(applyProfileConfig({}, profileConfig))
  return stableStringify(a) === stableStringify(b)
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort()
      .filter((k) => value[k] !== undefined)
      .map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

// ==== SHORT SUMMARY ====

/** One-line description shown under the profile name (e.g. "Spanish · es · gemini"). */
export function describeProfile(profileConfig) {
  const c = applyProfileConfig({}, profileConfig)
  const voice = c.tts.model_path ? c.tts.model_path.split('/').pop().replace(/\.onnx$/, '') : ''
  return [c.dialog.language, c.stt.language, c.llm.provider, voice].filter(Boolean).join(' · ')
}

// ==== IMPORT / EXPORT ====

export const PROFILE_FILE_KIND = 'dialostack-config-profile'

/** JSON text for one profile (secrets already stripped). */
export function profileToJson(profile) {
  return JSON.stringify(
    { kind: PROFILE_FILE_KIND, version: 1, name: profile.name, config: snapshotConfig(profile.config) },
    null,
    2
  )
}

/**
 * Parses a profile file. Returns { name, config } or throws an Error with a
 * user-facing message.
 */
export function profileFromJson(text, fallbackName = 'Imported profile') {
  let data
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error('The file is not valid JSON.')
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('The file does not contain a configuration profile.')
  }
  // Accept both a wrapped profile file and a bare config object.
  const config = data.kind === PROFILE_FILE_KIND ? data.config : data
  const known = Object.keys(DEFAULT_CONFIG)
  if (!config || typeof config !== 'object' || !Object.keys(config).some((k) => known.includes(k))) {
    throw new Error('The file does not contain any known configuration section.')
  }
  const picked = Object.fromEntries(Object.entries(config).filter(([k]) => known.includes(k)))
  return { name: (data.name || fallbackName).toString().slice(0, 60), config: snapshotConfig(picked) }
}
