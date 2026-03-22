import { useState, useRef } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import { LanguageProvider, useLanguage } from './context/LanguageContext'
import RTLWrapper from './components/RTLWrapper'
import DisclaimerBanner from './components/DisclaimerBanner'
import DarkModeToggle from './components/DarkModeToggle'
import LanguageToggle from './components/LanguageToggle'
import ChatInterface from './components/ChatInterface'
import WelcomeScreen from './components/WelcomeScreen'
import SymptomHistory from './components/SymptomHistory'
import { useChat } from './hooks/useChat'

function AppContent() {
  const { t, language } = useLanguage()
  const {
    messages,
    conversations,
    activeConversation,
    isStreaming,
    sendMessage,
    startNewChat,
    stopStreaming,
    selectConversation,
    deleteConversation,
  } = useChat(language === 'ar' ? 'arabic' : 'english')

  const [showHistory, setShowHistory] = useState(false)
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const hasMessages = messages.length > 0

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return
    sendMessage(trimmed)
    setInput('')
    inputRef.current?.focus()
  }

  const handleExampleClick = (text: string) => {
    sendMessage(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <RTLWrapper>
      <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-slate-950">
        <DisclaimerBanner />

        {/* Header */}
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center">
              <svg
                className="w-4 h-4 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                />
              </svg>
            </div>
            <h1 className="text-lg font-bold text-teal-700 dark:text-teal-400">
              {t('appName')}
            </h1>
          </div>

          <div className="flex items-center gap-2 relative">
            {hasMessages && (
              <button
                onClick={startNewChat}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-teal-50 dark:bg-teal-950/30 text-teal-600 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-900/40 transition-colors"
              >
                {t('newChat')}
              </button>
            )}
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              aria-label="History"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
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

        {/* Main content */}
        {hasMessages ? (
          <ChatInterface messages={messages} />
        ) : (
          <WelcomeScreen onExampleClick={handleExampleClick} />
        )}

        {/* Input area — always visible */}
        <div className="border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3">
          <div className="max-w-3xl mx-auto flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('inputPlaceholder')}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
            />
            {isStreaming ? (
              <button
                onClick={stopStreaming}
                className="shrink-0 p-2.5 rounded-xl bg-red-500 text-white hover:bg-red-600 transition-colors"
                aria-label="Stop"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="shrink-0 px-4 py-2.5 rounded-xl bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {t('send')}
              </button>
            )}
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
