import { afterEach, describe, expect, it, vi } from 'vitest'
import { warmUpBackend } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('warmUpBackend', () => {
  it('pings the health endpoint without waiting on it', () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}))
    vi.stubGlobal('fetch', fetchMock)
    expect(warmUpBackend()).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/health$/))
  })

  it('swallows network errors so page load is never affected', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))))
    warmUpBackend()
    // An unhandled rejection would fail the test run
    await new Promise((r) => setTimeout(r, 0))
  })
})
