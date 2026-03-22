import type { SSEEvent } from '../types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function streamChat(
  message: string,
  conversationHistory: Array<{ role: string; content: string }>,
  languagePreference: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_history: conversationHistory,
      language_preference: languagePreference,
    }),
    signal,
  })

  if (!response.ok) {
    if (response.status === 429) {
      onEvent({ type: 'error', message: 'Rate limit exceeded. Please wait a moment.' })
      return
    }
    onEvent({ type: 'error', message: 'Request failed.' })
    return
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
        onEvent(JSON.parse(data))
      } catch {
        // skip malformed frames
      }
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
