import type { SSEEvent } from '../types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const MAX_RETRIES = 3

async function _doStream(
  message: string,
  conversationHistory: Array<{ role: string; content: string }>,
  languagePreference: string,
  responseScript: string,
  onEvent: (event: SSEEvent) => void,
  signal: AbortSignal | undefined,
  onContent: () => void,
): Promise<void> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_history: conversationHistory,
      language_preference: languagePreference,
      response_script: responseScript,
    }),
    signal,
  })

  if (!response.ok) {
    if (response.status === 429) {
      onEvent({ type: 'error', message: 'Rate limit exceeded. Please wait a moment.' })
      return
    }
    if (response.status >= 400 && response.status < 500) {
      onEvent({ type: 'error', message: 'Request failed.' })
      return
    }
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') {
        onEvent({ type: 'done' })
        return
      }
      try {
        const event = JSON.parse(data) as SSEEvent
        if (event.type === 'chunk') onContent()
        onEvent(event)
      } catch {
        // skip malformed frames
      }
    }
  }
}

export async function streamChat(
  message: string,
  conversationHistory: Array<{ role: string; content: string }>,
  languagePreference: string,
  responseScript: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let hadContent = false

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      await _doStream(
        message,
        conversationHistory,
        languagePreference,
        responseScript,
        onEvent,
        signal,
        () => { hadContent = true },
      )
      return
    } catch {
      if (signal?.aborted) return
      if (hadContent || attempt >= MAX_RETRIES) {
        onEvent({ type: 'error', message: 'Connection error. Please try again.' })
        return
      }
      await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt))
    }
  }
}

export async function triageDirect(query: string) {
  const response = await fetch(`${API_URL}/api/triage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  return response.json()
}

export async function checkHealth() {
  const response = await fetch(`${API_URL}/api/health`)
  return response.json()
}
