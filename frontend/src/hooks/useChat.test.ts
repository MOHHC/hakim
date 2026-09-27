import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SSEEvent } from '../types'

// Drive the stream by hand so each test controls when the server "answers".
let emit: (event: SSEEvent) => void = () => {}
let finish: () => void = () => {}

vi.mock('../api/client', () => ({
  streamChat: vi.fn(
    (
      _message: string,
      _history: unknown,
      _lang: string,
      _script: string,
      onEvent: (event: SSEEvent) => void,
      signal?: AbortSignal,
    ) =>
      new Promise<void>((resolve) => {
        emit = onEvent
        finish = resolve
        signal?.addEventListener('abort', () => resolve())
      }),
  ),
}))

import { useChat } from './useChat'

afterEach(() => localStorage.clear())

function assistant(result: { current: ReturnType<typeof useChat> }) {
  return result.current.messages.find((m) => m.role === 'assistant')!
}

describe('useChat cold-start tracking', () => {
  it('marks the reply as awaiting the server until the first event', async () => {
    const { result } = renderHook(() => useChat('english', 'arabic'))
    act(() => {
      void result.current.sendMessage('I have a headache')
    })
    await waitFor(() => expect(assistant(result)).toBeDefined())
    expect(assistant(result).awaitingServer).toBe(true)

    act(() => emit({ type: 'start' }))
    expect(assistant(result).awaitingServer).toBe(false)
    expect(assistant(result).isStreaming).toBe(true)

    await act(async () => {
      emit({ type: 'complete', triage_level: 'GREEN' })
      finish()
    })
    expect(assistant(result).isStreaming).toBe(false)
  })

  it('stopping a request clears the typing state instead of spinning forever', async () => {
    const { result } = renderHook(() => useChat('english', 'arabic'))
    act(() => {
      void result.current.sendMessage('I have a headache')
    })
    await waitFor(() => expect(assistant(result)).toBeDefined())

    await act(async () => {
      result.current.stopStreaming()
    })
    await waitFor(() => expect(assistant(result).isStreaming).toBe(false))
    expect(assistant(result).awaitingServer).toBe(false)
    expect(result.current.isStreaming).toBe(false)
  })
})
