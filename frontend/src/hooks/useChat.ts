import { useState, useCallback, useRef } from 'react'
import type { Message, Conversation, TriageResult, SSEEvent } from '../types'
import { useLocalStorage } from './useLocalStorage'
import { streamChat } from '../api/client'

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

export function useChat(languagePreference: string = 'auto') {
  const [conversations, setConversations] = useLocalStorage<Conversation[]>(
    'hakim-conversations',
    [],
  )
  const [activeId, setActiveId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const activeConversation = conversations.find((c) => c.id === activeId) ?? null
  const messages = activeConversation?.messages ?? []

  /* ---- helpers to update a specific message in a conversation ---- */
  const patchMessage = useCallback(
    (convId: string, msgId: string, patch: Partial<Message>) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === msgId ? { ...m, ...patch } : m,
                ),
              }
            : c,
        ),
      )
    },
    [setConversations],
  )

  /* ---- actions ---- */

  const startNewChat = useCallback(() => {
    setActiveId(null)
  }, [])

  const sendMessage = useCallback(
    async (content: string) => {
      let convId = activeId

      // Create conversation if needed
      if (!convId) {
        convId = uid()
        const conv: Conversation = {
          id: convId,
          messages: [],
          createdAt: Date.now(),
          title: content.slice(0, 50),
        }
        setConversations((prev) => [conv, ...prev])
        setActiveId(convId)
      }

      const userMsg: Message = {
        id: uid(),
        role: 'user',
        content,
        timestamp: Date.now(),
      }
      const asstMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      }

      const cid = convId
      const aid = asstMsg.id

      // Append both messages
      setConversations((prev) =>
        prev.map((c) =>
          c.id === cid
            ? {
                ...c,
                messages: [...c.messages, userMsg, asstMsg],
                title: c.title || content.slice(0, 50),
              }
            : c,
        ),
      )

      setIsStreaming(true)
      const controller = new AbortController()
      abortRef.current = controller

      const history = messages
        .filter((m) => !m.isStreaming)
        .map((m) => ({ role: m.role, content: m.content }))

      try {
        await streamChat(
          content,
          history,
          languagePreference,
          (event: SSEEvent) => {
            switch (event.type) {
              case 'triage_classified': {
                const partialTriageResult: TriageResult = {
                  triage_level:
                    (event.triage_level as TriageResult['triage_level']) || 'YELLOW',
                  possible_conditions: event.possible_conditions ?? [],
                  recommended_actions: event.recommended_actions ?? [],
                  sources: [],
                  disclaimer: '',
                  needs_clarification: event.needs_clarification ?? false,
                }
                patchMessage(cid, aid, { triageResult: partialTriageResult })
                break
              }

              case 'chunk':
                if (event.content) {
                  setConversations((prev) =>
                    prev.map((c) =>
                      c.id === cid
                        ? {
                            ...c,
                            messages: c.messages.map((m) =>
                              m.id === aid
                                ? { ...m, content: m.content + event.content }
                                : m,
                            ),
                          }
                        : c,
                    ),
                  )
                }
                break

              case 'complete': {
                const triageResult: TriageResult = {
                  triage_level:
                    (event.triage_level as TriageResult['triage_level']) || 'YELLOW',
                  possible_conditions: event.possible_conditions ?? [],
                  recommended_actions: event.recommended_actions ?? [],
                  sources: event.sources ?? [],
                  disclaimer: event.disclaimer ?? '',
                  needs_clarification: event.needs_clarification ?? false,
                  follow_up_question: event.follow_up_question,
                }
                patchMessage(cid, aid, { isStreaming: false, triageResult })
                break
              }

              case 'blocked':
                patchMessage(cid, aid, {
                  content: event.message ?? '',
                  isStreaming: false,
                  isBlocked: true,
                  triageResult: event.force_red
                    ? {
                        triage_level: 'RED',
                        possible_conditions: [],
                        recommended_actions: [],
                        sources: [],
                        disclaimer: event.message ?? '',
                        needs_clarification: false,
                      }
                    : undefined,
                })
                break

              case 'error':
                patchMessage(cid, aid, {
                  content: event.message ?? 'An error occurred.',
                  isStreaming: false,
                  isError: true,
                })
                break
            }
          },
          controller.signal,
        )
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          patchMessage(cid, aid, {
            content: 'Connection error.',
            isStreaming: false,
            isError: true,
          })
        }
      } finally {
        setIsStreaming(false)
        abortRef.current = null
      }
    },
    [activeId, messages, languagePreference, setConversations, patchMessage],
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const selectConversation = useCallback((id: string) => {
    setActiveId(id)
  }, [])

  const deleteConversation = useCallback(
    (id: string) => {
      setConversations((prev) => prev.filter((c) => c.id !== id))
      if (activeId === id) setActiveId(null)
    },
    [activeId, setConversations],
  )

  return {
    messages,
    conversations,
    activeConversation,
    isStreaming,
    sendMessage,
    startNewChat,
    stopStreaming,
    selectConversation,
    deleteConversation,
  }
}
