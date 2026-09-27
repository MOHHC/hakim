import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { LanguageProvider } from '../context/LanguageContext'
import TypingIndicator, { WAKING_UP_AFTER_MS } from './TypingIndicator'

function renderIndicator(ui: ReactNode) {
  localStorage.setItem('hakim-lang', 'en')
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

describe('TypingIndicator', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    localStorage.clear()
  })

  it('says "thinking" while the server has not been silent for long', () => {
    renderIndicator(<TypingIndicator awaitingServer />)
    act(() => vi.advanceTimersByTime(WAKING_UP_AFTER_MS - 1))
    expect(screen.getByRole('status').textContent).toBe('Hakim is thinking...')
  })

  it('explains the cold start once the server has been silent for 5s', () => {
    renderIndicator(<TypingIndicator awaitingServer />)
    act(() => vi.advanceTimersByTime(WAKING_UP_AFTER_MS))
    expect(screen.getByRole('status').textContent).toMatch(/waking up/i)
  })

  it('never shows "waking up" once the server has answered', () => {
    renderIndicator(<TypingIndicator awaitingServer={false} />)
    act(() => vi.advanceTimersByTime(60_000))
    expect(screen.getByRole('status').textContent).toBe('Hakim is thinking...')
  })

  it('goes back to "thinking" when the server answers after a slow start', () => {
    const { rerender } = renderIndicator(<TypingIndicator awaitingServer />)
    act(() => vi.advanceTimersByTime(WAKING_UP_AFTER_MS))
    rerender(
      <LanguageProvider>
        <TypingIndicator awaitingServer={false} />
      </LanguageProvider>,
    )
    expect(screen.getByRole('status').textContent).toBe('Hakim is thinking...')
  })

  it('has the waking-up text in Arabic too', () => {
    localStorage.setItem('hakim-lang', 'ar')
    render(
      <LanguageProvider>
        <TypingIndicator awaitingServer />
      </LanguageProvider>,
    )
    act(() => vi.advanceTimersByTime(WAKING_UP_AFTER_MS))
    expect(screen.getByRole('status').textContent).toMatch(/[؀-ۿ]/)
    expect(screen.getByRole('status').textContent).not.toBe('')
  })
})
