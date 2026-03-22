import { useLanguage } from '../context/LanguageContext'

export default function TypingIndicator() {
  const { t } = useLanguage()

  return (
    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm">
      <div className="flex gap-1">
        <span className="typing-dot w-1.5 h-1.5 bg-teal-500 rounded-full" />
        <span className="typing-dot w-1.5 h-1.5 bg-teal-500 rounded-full" />
        <span className="typing-dot w-1.5 h-1.5 bg-teal-500 rounded-full" />
      </div>
      <span>{t('typing')}</span>
    </div>
  )
}
