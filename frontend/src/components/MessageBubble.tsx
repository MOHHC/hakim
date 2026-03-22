import type { Message } from '../types'
import PulsingTriageBadge from './PulsingTriageBadge'
import SourceCitation from './SourceCitation'
import TypingIndicator from './TypingIndicator'
import { useLanguage } from '../context/LanguageContext'

function AiAvatar() {
  return (
    <div style={{
      width: 30, height: 30, borderRadius: '50%',
      background: 'var(--green-bg)', border: '1px solid var(--border-dim)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0, marginTop: 2,
      boxShadow: '0 2px 8px var(--gold-glow)',
    }}>
      <svg width="14" height="14" viewBox="0 0 40 40" fill="none">
        <polygon points="20,4 25,10 32,10 36,16 32,22 25,22 20,28 15,22 8,22 4,16 8,10 15,10"
          fill="none" stroke="var(--gold)" strokeWidth="2" opacity="0.8" />
        <circle cx="20" cy="16" r="3" fill="var(--gold)" opacity="0.9" />
      </svg>
    </div>
  )
}

function ConditionsList({ items, label }: { items: string[]; label: string }) {
  if (!items.length) return null
  return (
    <div>
      <div style={{
        fontSize: '0.68rem', fontWeight: 600, letterSpacing: '0.08em',
        color: 'var(--text-dim)', marginBottom: 6, textTransform: 'uppercase',
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <div style={{ width: 12, height: 1, background: 'var(--gold)', opacity: 0.3 }} />
        {label}
      </div>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((c, i) => (
          <li key={i} style={{
            fontSize: '0.8rem', color: 'var(--text-muted)',
            display: 'flex', alignItems: 'flex-start', gap: 8,
            padding: '3px 0',
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: 'var(--gold)', flexShrink: 0, marginTop: 6,
              boxShadow: '0 0 4px var(--gold-glow)',
            }} />
            {c}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function MessageBubble({ message }: { message: Message }) {
  const { t, language } = useLanguage()
  const isUser = message.role === "user"

  const bubbleStyle = isUser
    ? {
        background: "var(--user-bg)",
        color: "var(--user-text)",
        borderRadius: 18, borderTopRightRadius: 4,
        padding: "12px 18px", maxWidth: "78%",
        boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
      } as React.CSSProperties
    : message.isError
      ? {
          background: "var(--red-bg)", border: "1px solid var(--red)",
          color: "var(--red)", borderRadius: 14, padding: "12px 16px", maxWidth: "80%",
        } as React.CSSProperties
      : message.isBlocked
        ? {
            background: "var(--yellow-bg)", border: "1px solid var(--yellow)",
            color: "var(--yellow)", borderRadius: 14, padding: "12px 16px", maxWidth: "80%",
          } as React.CSSProperties
        : {
            background: "var(--card-ai)", border: "1px solid var(--border)",
            color: "var(--text)", borderRadius: 18, borderTopLeftRadius: 4,
            padding: "14px 18px", maxWidth: "80%",
            boxShadow: "0 1px 8px rgba(0,0,0,0.04)",
          } as React.CSSProperties

  return (
    <div className="msg-enter" style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", gap: 8 }}>
      {!isUser && <AiAvatar />}
      <div style={bubbleStyle}>
        {message.isStreaming && !message.content ? (
          <TypingIndicator />
        ) : (
          <>
            <p style={{ margin: 0, fontSize: "0.925rem", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
              {message.content}
            </p>

            {!isUser && (message.triageResult || message.isStreaming) && (
              <div style={{ marginTop: 12 }}>
                <PulsingTriageBadge
                  level={message.triageResult?.triage_level}
                  isStreaming={!!message.isStreaming}
                />
              </div>
            )}

            {message.triageResult && !message.isStreaming && (
              <div style={{
                marginTop: 14, display: "flex", flexDirection: "column", gap: 10,
                borderTop: "1px solid var(--border-dim)", paddingTop: 12,
              }}>
                <ConditionsList items={message.triageResult.possible_conditions} label={language === 'en' ? `${t("possibleConditions")} (حالات محتملة)` : t("possibleConditions")} />
                <ConditionsList items={message.triageResult.recommended_actions} label={language === 'en' ? `${t("recommendedActions")} (الخطوات المنصوح فيها)` : t("recommendedActions")} />

                <SourceCitation sources={message.triageResult.sources} />

                {message.triageResult.disclaimer && (
                  <p style={{
                    margin: 0, fontSize: "0.71rem", color: "var(--text-dim)",
                    fontStyle: "italic", borderTop: "1px solid var(--border-dim)", paddingTop: 8,
                    lineHeight: 1.5,
                  }}>
                    {message.triageResult.disclaimer}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
