import { useLanguage } from '../context/LanguageContext'

export default function ResponseScriptToggle() {
  const { responseScript, toggleResponseScript } = useLanguage()
  const isFranco = responseScript === 'franco'

  return (
    <button
      onClick={toggleResponseScript}
      className="hakim-toolbar-btn"
      aria-label="Toggle response script"
      title={isFranco ? 'Switch to Arabic script' : 'Switch to Franco-Arab'}
      style={{ padding: '4px 10px', gap: 5 }}
    >
      <span style={{
        fontSize: '0.7rem',
        fontWeight: 600,
        opacity: isFranco ? 1 : 0.35,
        transition: 'opacity 0.2s',
      }}>Aa</span>
      <span style={{
        width: 1,
        height: 12,
        background: 'var(--border)',
      }} />
      <span style={{
        fontSize: '0.74rem',
        fontWeight: 600,
        opacity: isFranco ? 0.35 : 1,
        transition: 'opacity 0.2s',
      }}>{'\u0639\u0631'}</span>
    </button>
  )
}
