/**
 * Subscribes to /llm/error and keeps the most recent LLM failure so the Monitor
 * can explain why the dialog dropped to its deterministic fallback. Provider-
 * agnostic: it just renders whatever fields the backend fills in.
 */
import { useCallback, useState } from 'react'
import { useTopic } from './useTopic'
import { TOPICS } from '../lib/ros'

export function useLlmError() {
  const [lastError, setLastError] = useState(null)

  useTopic(TOPICS.llmError.name, TOPICS.llmError.type, (msg) => {
    setLastError({
      provider: msg.provider || '',
      model: msg.model || '',
      sessionId: msg.session_id || '',
      code: Number(msg.code) || 0,
      errorType: msg.error_type || '',
      message: msg.message || '',
      at: Date.now(),
    })
  })

  const dismiss = useCallback(() => setLastError(null), [])

  return { lastError, dismiss }
}
