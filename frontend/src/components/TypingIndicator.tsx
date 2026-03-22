import { useLanguage } from '../context/LanguageContext'

export default function TypingIndicator() {
  const { t } = useLanguage()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ display: 'flex', gap: 5 }}>
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
      </div>
      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{t('typing')}</span>
    </div>
  )
}
