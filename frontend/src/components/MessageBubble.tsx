import type { Message } from '../types'
import PulsingTriageBadge from './PulsingTriageBadge'
import SourceCitation from './SourceCitation'
import TypingIndicator from './TypingIndicator'
import { useLanguage } from '../context/LanguageContext'

export default function MessageBubble({ message }: { message: Message }) {
  const { t } = useLanguage()
  const isUser = message.role === "user"

  const bubbleStyle = isUser
    ? {
        background: "var(--user-bg)",
        color: "var(--user-text)",
        borderRadius: 16, borderTopRightRadius: 4,
        padding: "12px 16px", maxWidth: "78%",
      } as React.CSSProperties
    : message.isError
      ? {
          background: "var(--red-bg)", border: "1px solid var(--red)",
          color: "var(--red)", borderRadius: 12, padding: "12px 16px", maxWidth: "80%",
        } as React.CSSProperties
      : message.isBlocked
        ? {
            background: "var(--yellow-bg)", border: "1px solid var(--yellow)",
            color: "var(--yellow)", borderRadius: 12, padding: "12px 16px", maxWidth: "80%",
          } as React.CSSProperties
        : {
            background: "var(--card-ai)", border: "1px solid var(--border)",
            color: "var(--text)", borderRadius: 16, borderTopLeftRadius: 4,
            padding: "14px 16px", maxWidth: "80%",
          } as React.CSSProperties

  return (
    <div className="msg-enter" style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
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
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                {message.triageResult.possible_conditions.length > 0 && (
                  <div>
                    <div style={{ fontSize: "0.68rem", fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 5, textTransform: "uppercase" }}>
                      {t("possibleConditions")}
                    </div>
                    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 3 }}>
                      {message.triageResult.possible_conditions.map((c, i) => (
                        <li key={i} style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 7 }}>
                          <span style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--gold)", flexShrink: 0 }} />
                          {c}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {message.triageResult.recommended_actions.length > 0 && (
                  <div>
                    <div style={{ fontSize: "0.68rem", fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 5, textTransform: "uppercase" }}>
                      {t("recommendedActions")}
                    </div>
                    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 3 }}>
                      {message.triageResult.recommended_actions.map((a, i) => (
                        <li key={i} style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "flex-start", gap: 7 }}>
                          <span style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--gold)", flexShrink: 0, marginTop: 6 }} />
                          {a}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <SourceCitation sources={message.triageResult.sources} />

                {message.triageResult.disclaimer && (
                  <p style={{
                    margin: 0, fontSize: "0.71rem", color: "var(--text-dim)",
                    fontStyle: "italic", borderTop: "1px solid var(--border-dim)", paddingTop: 8,
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
