export type TriageLevel = 'GREEN' | 'YELLOW' | 'RED'

export type Language = 'ar' | 'en'

export interface Source {
  title?: string
  content?: string
  score?: number
  [key: string]: unknown
}

export interface TriageResult {
  triage_level: TriageLevel
  possible_conditions: string[]
  recommended_actions: string[]
  sources: Source[]
  disclaimer: string
  needs_clarification: boolean
  follow_up_question?: string | null
  clarification_question?: string | null
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  triageResult?: TriageResult
  isStreaming?: boolean
  isBlocked?: boolean
  isError?: boolean
}

export interface Conversation {
  id: string
  messages: Message[]
  createdAt: number
  title: string
}

export interface SSEEvent {
  type: 'start' | 'chunk' | 'triage_classified' | 'complete' | 'blocked' | 'error' | 'done'
  content?: string
  triage_level?: string
  possible_conditions?: string[]
  recommended_actions?: string[]
  sources?: Source[]
  disclaimer?: string
  follow_up_question?: string | null
  needs_clarification?: boolean
  reason?: string
  message?: string
  force_red?: boolean
}
