import { useLanguage } from '../context/LanguageContext'

export default function LanguageToggle() {
  const { toggleLanguage, t } = useLanguage()

  return (
    <button
      onClick={toggleLanguage}
      className="px-3 py-1.5 text-sm font-medium rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
      aria-label="Toggle language"
    >
      {t('toggleLang')}
    </button>
  )
}
