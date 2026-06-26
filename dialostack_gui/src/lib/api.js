/**
 * Single client for the GUI server HTTP API (server.py).
 * Every frontend fetch call goes through here.
 *
 * Each request carries a timeout (AbortController): if the server hangs, the
 * promise rejects instead of staying pending forever - important for the
 * status/keepalive polling, which would otherwise pile up without bound.
 */
const JSON_HEADERS = { 'Content-Type': 'application/json' }
const DEFAULT_TIMEOUT = 8000

/** API error with a typed cause so callers can distinguish failure modes. */
export class ApiError extends Error {
  constructor(message, { kind = 'http', status = null, path } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind // 'http' | 'timeout' | 'network' | 'parse'
    this.status = status
    this.path = path
  }
}

async function request(path, { timeout = DEFAULT_TIMEOUT, ...options } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(path, { ...options, signal: controller.signal })
    if (!res.ok) throw new ApiError(`${path} - HTTP ${res.status}`, { kind: 'http', status: res.status, path })
    return await res.json()
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err.name === 'AbortError') throw new ApiError(`${path} - request timed out`, { kind: 'timeout', path })
    if (err.name === 'SyntaxError') throw new ApiError(`${path} - response is not JSON`, { kind: 'parse', path })
    throw new ApiError(`${path} - no connection to the server`, { kind: 'network', path })
  } finally {
    clearTimeout(timer)
  }
}

const postJson = (path, body, opts = {}) =>
  request(path, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body), ...opts })

export const api = {
  engineStatus: () => request('/api/engine/status'),
  engineStart: (config) => postJson('/api/engine/start', { config }),
  engineStop: () => request('/api/engine/stop', { method: 'POST' }),
  engineKeepalive: () => request('/api/engine/keepalive', { method: 'POST' }),
  engineLog: () => request('/api/engine/log'),

  /** Generates the parameters YAML on the server (single source of truth). */
  configYaml: (config) => postJson('/api/config/yaml', { config }),

  /** Engine default prompt templates (read from prompts.yaml). */
  prompts: () => request('/api/prompts'),

  /** Generates the exportable prompts.yaml (defaults+overrides or overrides only). */
  promptsYaml: (overrides, mode = 'full') => postJson('/api/prompts/yaml', { overrides, mode }),

  /** Parses an imported prompts file (YAML or JSON) into a {key: template} map. */
  promptsParse: (text) => postJson('/api/prompts/parse', { text }),

  /** Engine default canned phrases for a language ({key: str | 'ack': list}). */
  phrases: (language) => request(`/api/phrases?language=${encodeURIComponent(language)}`),

  /** Generates the exportable phrases.yaml for a language (full or overrides). */
  phrasesYaml: (overrides, language, mode = 'full') =>
    postJson('/api/phrases/yaml', { overrides, language, mode }),

  /** Parses an imported phrases file into a {key: str | 'ack': list} map. */
  phrasesParse: (text) => postJson('/api/phrases/parse', { text }),

  /** Parses a pasted task (goal JSON, YAML, or a `ros2 action send_goal` command) into a goal object. */
  taskParse: (text) => postJson('/api/task/parse', { text }),

  /** System microphone status (hardware mute via PipeWire). */
  micStatus: () => request('/api/mic/status'),

  micMute: (muted) => postJson('/api/mic/mute', { muted }),

  /**
   * Panic button: kills every DialoStack node/launch across terminals (engine,
   * LLM, speech, vision, NAO). rosbridge and the GUI server are left alive.
   * Longer timeout: the server does SIGTERM, waits, then SIGKILL survivors.
   */
  killAll: () => request('/api/system/kill-all', { method: 'POST', timeout: 15000 }),
}
