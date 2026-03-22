import { useState, useCallback } from 'react'
import type { TriageResult } from '../types'
import { triageDirect } from '../api/client'

export function useTriage() {
  const [result, setResult] = useState<TriageResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const triage = useCallback(async (query: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await triageDirect(query)
      if (data.blocked) {
        setError(data.message)
        return null
      }
      setResult(data)
      return data as TriageResult
    } catch {
      setError('Triage request failed.')
      return null
    } finally {
      setIsLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return { result, isLoading, error, triage, reset }
}
