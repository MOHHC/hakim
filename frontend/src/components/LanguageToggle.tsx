import { useLanguage } from '../context/LanguageContext'

export default function LanguageToggle() {
  const { toggleLanguage, t } = useLanguage()

  return (
    <button
      onClick={toggleLanguage}
      className="hakim-toolbar-btn"
      aria-label="Toggle language"
      style={{ padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600 }}
    >
      {t('toggleLang')}
    </button>
  )
}
