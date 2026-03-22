import { useLanguage } from '../context/LanguageContext'

export default function ResponseScriptToggle() {
  const { responseScript, toggleResponseScript } = useLanguage()
  const isFranco = responseScript === 'franco'

  return (
    <button
      onClick={toggleResponseScript}
      aria-label="Toggle response script"
      title={isFranco ? 'Switch to Arabic script' : 'Switch to Franco-Arab'}
      style={{
        padding: '4px 10px',
        fontSize: '0.72rem',
        fontWeight: 600,
        borderRadius: 8,
        border: '1px solid var(--border)',
        background: 'var(--surface)',
        color: 'var(--text-muted)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        transition: 'all 0.2s ease',
      }}
    >
      <span style={{
        fontSize: '0.68rem',
        opacity: isFranco ? 1 : 0.4,
        transition: 'opacity 0.2s',
      }}>Aa</span>
      <span style={{
        width: 1,
        height: 12,
        background: 'var(--border)',
      }} />
      <span style={{
        fontSize: '0.72rem',
        opacity: isFranco ? 0.4 : 1,
        transition: 'opacity 0.2s',
      }}>{'\u0639\u0631'}</span>
    </button>
  )
}
