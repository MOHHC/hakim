export type TriageLevel = 'GREEN' | 'YELLOW' | 'RED'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface TriageResult {
  level: TriageLevel
  conditions: string[]
  nextSteps: string[]
  disclaimer: string
}
