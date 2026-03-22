import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import type { Language, ResponseScript } from '../types'

const translations = {
  ar: {
    appName: '\u062d\u0643\u064a\u0645',
    tagline: '\u0645\u0633\u0627\u0639\u062f\u0643 \u0627\u0644\u0635\u062d\u064a \u0627\u0644\u0630\u0643\u064a',
    disclaimer:
      '\u0647\u0630\u0627 \u0627\u0644\u062a\u0637\u0628\u064a\u0642 \u0644\u0627 \u064a\u063a\u0646\u064a \u0639\u0646 \u0627\u0633\u062a\u0634\u0627\u0631\u0629 \u0627\u0644\u0637\u0628\u064a\u0628. \u0641\u064a \u062d\u0627\u0644\u0629 \u0627\u0644\u0637\u0648\u0627\u0631\u0626\u060c \u0627\u062a\u0635\u0644 \u0628\u0627\u0644\u062f\u0641\u0627\u0639 \u0627\u0644\u0645\u062f\u0646\u064a \u0639\u0644\u0649 125 \u0623\u0648 \u062a\u0648\u062c\u0647 \u0644\u0623\u0642\u0631\u0628 \u0645\u0633\u062a\u0634\u0641\u0649.',
    welcomeTitle: '\u0643\u064a\u0641 \u0628\u0642\u062f\u0631 \u0633\u0627\u0639\u062f\u0643 \u0627\u0644\u064a\u0648\u0645\u061f',
    welcomeSubtitle:
      '\u0627\u0648\u0635\u0641 \u0623\u0639\u0631\u0627\u0636\u0643 \u0648\u0623\u0646\u0627 \u0628\u0633\u0627\u0639\u062f\u0643 \u062a\u0641\u0647\u0645 \u0634\u0648 \u0645\u0645\u0643\u0646 \u064a\u0643\u0648\u0646 \u0639\u0646\u062f\u0643',
    inputPlaceholder: '\u0627\u0648\u0635\u0641 \u0623\u0639\u0631\u0627\u0636\u0643 \u0647\u0648\u0646...',
    send: '\u0625\u0631\u0633\u0627\u0644',
    newChat: '\u0645\u062d\u0627\u062f\u062b\u0629 \u062c\u062f\u064a\u062f\u0629',
    sources: '\u0627\u0644\u0645\u0635\u0627\u062f\u0631',
    possibleConditions: '\u062d\u0627\u0644\u0627\u062a \u0645\u062d\u062a\u0645\u0644\u0629',
    recommendedActions: '\u0627\u0644\u062e\u0637\u0648\u0627\u062a \u0627\u0644\u0645\u0646\u0635\u0648\u062d \u0641\u064a\u0647\u0627',
    triageGreen: '\u0639\u0646\u0627\u064a\u0629 \u0645\u0646\u0632\u0644\u064a\u0629',
    triageYellow: '\u0631\u0627\u062c\u0639 \u0637\u0628\u064a\u0628',
    triageRed: '\u0637\u0648\u0627\u0631\u0626 \u0641\u0648\u0631\u0627\u064b',
    history: '\u0627\u0644\u0645\u062d\u0627\u062f\u062b\u0627\u062a \u0627\u0644\u0633\u0627\u0628\u0642\u0629',
    noHistory: '\u0645\u0627 \u0641\u064a \u0645\u062d\u0627\u062f\u062b\u0627\u062a \u0633\u0627\u0628\u0642\u0629',
    toggleLang: 'EN',
    typing: '\u062d\u0643\u064a\u0645 \u0639\u0645 \u064a\u0641\u0643\u0631...',
    errorMessage: '\u0635\u0627\u0631 \u062e\u0637\u0623\u060c \u062c\u0631\u0628 \u0645\u0631\u0629 \u062a\u0627\u0646\u064a\u0629',
    analyzing: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u062d\u0644\u064a\u0644...',
    featureAnalysis: '\u062a\u062d\u0644\u064a\u0644 \u0627\u0644\u0623\u0639\u0631\u0627\u0636',
    featureAnalysisDesc: '\u0627\u0648\u0635\u0641 \u0634\u0648 \u0639\u0645 \u062a\u062d\u0633 \u0641\u064a\u0647 \u0648\u062d\u0643\u064a\u0645 \u0628\u064a\u062d\u0644\u0644\u0647\u0627',
    featureTriage: '\u062a\u0642\u064a\u064a\u0645 \u0627\u0644\u0627\u0633\u062a\u0639\u062c\u0627\u0644',
    featureTriageDesc: '\u0628\u062a\u0627\u062e\u062f \u0645\u0633\u062a\u0648\u0649 \u0623\u0648\u0644\u0648\u064a\u0629: \u0623\u062e\u0636\u0631\u060c \u0623\u0635\u0641\u0631\u060c \u0623\u0648 \u0623\u062d\u0645\u0631',
    featurePrivate: '\u062e\u0627\u0635 \u0648\u0622\u0645\u0646',
    featurePrivateDesc: '\u0628\u064a\u0627\u0646\u0627\u062a\u0643 \u0627\u0644\u0634\u062e\u0635\u064a\u0629 \u0645\u0627 \u0628\u062a\u0646\u062d\u0641\u0638 \u0623\u0628\u062f\u0627\u064b',
    tryAsking: '\u062c\u0631\u0628 \u0627\u0633\u0623\u0644',
  },
  en: {
    appName: 'Hakim',
    tagline: 'Your AI Health Assistant',
    disclaimer:
      'This app is not a substitute for medical advice. In emergencies, call 125 (Civil Defense) or go to the nearest hospital.',
    welcomeTitle: 'How can I help you today?',
    welcomeSubtitle:
      "Describe your symptoms and I'll help you understand what might be going on",
    inputPlaceholder: 'Describe your symptoms here...',
    send: 'Send',
    newChat: 'New Chat',
    sources: 'Sources',
    possibleConditions: 'Possible Conditions',
    recommendedActions: 'Recommended Actions',
    triageGreen: 'Home Care',
    triageYellow: 'See a Doctor',
    triageRed: 'Emergency Now',
    history: 'Conversation History',
    noHistory: 'No previous conversations',
    toggleLang: '\u0639',
    typing: 'Hakim is thinking...',
    errorMessage: 'Something went wrong, please try again',
    analyzing: 'Analyzing...',
    featureAnalysis: 'Symptom Analysis',
    featureAnalysisDesc: 'Describe what you feel and Hakim will analyze it',
    featureTriage: 'Urgency Assessment',
    featureTriageDesc: 'Get a priority level: Green, Yellow, or Red',
    featurePrivate: 'Private & Secure',
    featurePrivateDesc: 'Your personal data is never stored',
    tryAsking: 'Try asking',
  },
} as const

type TranslationKey = keyof (typeof translations)['ar']

interface LanguageContextValue {
  language: Language
  setLanguage: (lang: Language) => void
  toggleLanguage: () => void
  t: (key: TranslationKey) => string
  dir: 'rtl' | 'ltr'
  responseScript: ResponseScript
  setResponseScript: (script: ResponseScript) => void
  toggleResponseScript: () => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLang] = useState<Language>(
    () => (localStorage.getItem('hakim-lang') as Language) || 'ar',
  )
  const [responseScript, setScript] = useState<ResponseScript>(
    () => (localStorage.getItem('hakim-script') as ResponseScript) || 'arabic',
  )

  const handleSet = useCallback((lang: Language) => {
    setLang(lang)
    localStorage.setItem('hakim-lang', lang)
  }, [])

  const toggleLanguage = useCallback(() => {
    setLang((prev) => {
      const next = prev === 'ar' ? 'en' : 'ar'
      localStorage.setItem('hakim-lang', next)
      return next
    })
  }, [])

  const handleSetScript = useCallback((s: ResponseScript) => {
    setScript(s)
    localStorage.setItem('hakim-script', s)
  }, [])

  const toggleResponseScript = useCallback(() => {
    setScript((prev) => {
      const next = prev === 'arabic' ? 'franco' : 'arabic'
      localStorage.setItem('hakim-script', next)
      return next
    })
  }, [])

  const t = useCallback(
    (key: TranslationKey): string => translations[language][key],
    [language],
  )

  const dir = language === 'ar' ? ('rtl' as const) : ('ltr' as const)

  // Sync dir attribute on <html>
  useEffect(() => {
    document.documentElement.dir = dir
    document.documentElement.lang = language
  }, [dir, language])

  return (
    <LanguageContext.Provider
      value={{ language, setLanguage: handleSet, toggleLanguage, t, dir, responseScript, setResponseScript: handleSetScript, toggleResponseScript }}
    >
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
