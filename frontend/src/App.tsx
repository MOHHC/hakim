import { useState, useRef } from "react"
import { ThemeProvider } from "./context/ThemeContext"
import { LanguageProvider, useLanguage } from "./context/LanguageContext"
import RTLWrapper from "./components/RTLWrapper"
import DisclaimerBanner from "./components/DisclaimerBanner"
import DarkModeToggle from "./components/DarkModeToggle"
import LanguageToggle from "./components/LanguageToggle"
import ChatInterface from "./components/ChatInterface"
import WelcomeScreen from "./components/WelcomeScreen"
import SymptomHistory from "./components/SymptomHistory"
import { useChat } from "./hooks/useChat"

function HakimLogo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <polygon points="20,2 25,9 33,9 38,16 33,24 25,24 20,31 15,24 7,24 2,16 7,9 15,9"
        fill="none" stroke="var(--gold)" strokeWidth="1.5" />
      <line x1="20" y1="2" x2="20" y2="31" stroke="var(--gold)" strokeWidth="0.7" opacity="0.4" />
      <line x1="2" y1="16" x2="38" y2="16" stroke="var(--gold)" strokeWidth="0.7" opacity="0.4" />
      <line x1="7" y1="9" x2="33" y2="24" stroke="var(--gold)" strokeWidth="0.7" opacity="0.4" />
      <line x1="33" y1="9" x2="7" y2="24" stroke="var(--gold)" strokeWidth="0.7" opacity="0.4" />
      <circle cx="20" cy="16" r="3.5" fill="var(--gold)" />
    </svg>
  )
}

function AppContent() {
  const { t, language } = useLanguage()
  const {
    messages, conversations, activeConversation, isStreaming,
    sendMessage, startNewChat, stopStreaming, selectConversation, deleteConversation,
  } = useChat(language === "ar" ? "arabic" : "english")

  const [showHistory, setShowHistory] = useState(false)
  const [input, setInput] = useState("")
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const hasMessages = messages.length > 0

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return
    sendMessage(trimmed)
    setInput("")
    inputRef.current?.focus()
  }
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <RTLWrapper>
      <div className="hakim-bg" style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
        <div style={{ position: "relative", zIndex: 2, flex: 1, display: "flex", flexDirection: "column" }}>
          <DisclaimerBanner />

          <header className="hakim-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 20px" }}>
            <button onClick={startNewChat} style={{ display: "flex", alignItems: "center", gap: 12, background: "none", border: "none", padding: 0, cursor: "pointer" }}>
              <HakimLogo size={34} />
              <div style={{ lineHeight: 1.1 }}>
                <div style={{
                  fontFamily: "var(--font-display)",
                  fontSize: language === "ar" ? "1.45rem" : "1.6rem",
                  fontWeight: 600,
                  fontStyle: language === "en" ? "italic" : "normal",
                  color: "var(--gold)",
                  letterSpacing: language === "en" ? "0.03em" : "0",
                }}>{t("appName")}</div>
                <div style={{ fontSize: "0.62rem", color: "var(--text-dim)", marginTop: 2 }}>{t("tagline")}</div>
              </div>
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 8, position: "relative" }}>
              {hasMessages && (
                <button onClick={startNewChat} style={{
                  padding: "5px 14px", fontSize: "0.75rem", fontWeight: 500,
                  borderRadius: 6, border: "1px solid var(--border)",
                  background: "var(--surface)", color: "var(--text-muted)",
                  cursor: "pointer", fontFamily: "inherit",
                }}>{t("newChat")}</button>
              )}
              <button onClick={() => setShowHistory(!showHistory)} aria-label="History" style={{
                padding: 7, borderRadius: 8, border: "1px solid var(--border)",
                background: "var(--surface)", color: "var(--text-muted)",
                cursor: "pointer", display: "flex", alignItems: "center",
              }}>
                <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
              <LanguageToggle />
              <DarkModeToggle />
              {showHistory && (
                <SymptomHistory
                  conversations={conversations}
                  activeId={activeConversation?.id ?? null}
                  onSelect={selectConversation}
                  onDelete={deleteConversation}
                  onClose={() => setShowHistory(false)}
                />
              )}
            </div>
          </header>

          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {hasMessages ? <ChatInterface messages={messages} /> : <WelcomeScreen onExampleClick={sendMessage} />}
          </div>

          <div className="hakim-header" style={{ padding: "12px 20px" }}>
            <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", gap: 10, alignItems: "flex-end" }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t("inputPlaceholder")}
                rows={1}
                className="hakim-textarea"
                style={{ flex: 1, borderRadius: 12, padding: "10px 16px", fontSize: "0.95rem", lineHeight: 1.5, resize: "none", fontFamily: "inherit" }}
              />
              {isStreaming ? (
                <button onClick={stopStreaming} style={{
                  flexShrink: 0, width: 42, height: 42, borderRadius: 12, border: "none",
                  background: "var(--red)", color: "#fff", cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                </button>
              ) : (
                <button onClick={handleSend} disabled={!input.trim()} className="btn-gold" style={{
                  flexShrink: 0, height: 42, padding: "0 20px", borderRadius: 12, border: "none",
                  fontSize: "0.875rem", fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
                }}>{t("send")}</button>
              )}
            </div>
          </div>
        </div>
      </div>
    </RTLWrapper>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppContent />
      </LanguageProvider>
    </ThemeProvider>
  )
}
