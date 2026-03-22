import { useLanguage } from '../context/LanguageContext'

export default function DisclaimerBanner() {
  const { t } = useLanguage()
  return (
    <div style={{
      background: 'var(--yellow-bg)',
      borderBottom: '1px solid var(--border-dim)',
      padding: '5px 20px',
    }}>
      <div style={{
        maxWidth: 720, margin: '0 auto',
        display: 'flex', alignItems: 'center', gap: 8,
        color: 'var(--yellow)', fontSize: '0.72rem',
      }}>
        <svg width="12" height="12" fill="currentColor" viewBox="0 0 20 20" style={{ flexShrink: 0 }}>
          <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
        </svg>
        <span>{t('disclaimer')}</span>
      </div>
    </div>
  )
}
