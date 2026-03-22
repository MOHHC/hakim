import { useLanguage } from '../context/LanguageContext'

const examplePrompts = [
  { ar: 'عندي وجع راس من يومين', en: "I've had a headache for two days" },
  { ar: 'ابني عمرو 5 سنين وعندو حرارة', en: 'My 5-year-old son has a fever' },
  { ar: 'بحس بضيق نفس لما امشي', en: 'I feel short of breath when walking' },
  { ar: 'عندي وجع بطن وغثيان', en: 'I have stomach pain and nausea' },
]

export default function WelcomeScreen({ onExampleClick }: { onExampleClick: (t: string) => void }) {
  const { t, language } = useLanguage()
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '32px 20px', position: 'relative', overflow: 'hidden',
    }}>
      <div aria-hidden="true" style={{
        position: 'absolute', fontSize: '24vw',
        fontFamily: 'var(--font-display)', fontWeight: 700,
        color: 'var(--gold)', opacity: 0.025,
        userSelect: 'none', pointerEvents: 'none',
        top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        whiteSpace: 'nowrap', lineHeight: 1,
      }}>حكيم</div>

      <div className="msg-enter" style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{
          width: 60, height: 60, borderRadius: '50%',
          border: '1px solid var(--border)',
          background: 'var(--surface)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          margin: '0 auto 16px',
        }}>
          <svg width="26" height="26" viewBox="0 0 40 40" fill="none">
            <polygon points="20,2 25,9 33,9 38,16 33,24 25,24 20,31 15,24 7,24 2,16 7,9 15,9"
              fill="none" stroke="var(--gold)" strokeWidth="1.5" />
            <circle cx="20" cy="16" r="3.5" fill="var(--gold)" />
          </svg>
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(2rem, 6vw, 3.2rem)',
          fontWeight: 600,
          fontStyle: language === 'en' ? 'italic' : 'normal',
          color: 'var(--gold)',
          margin: '0 0 8px',
          letterSpacing: language === 'en' ? '0.03em' : '0',
        }}>{t('appName')}</h1>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: '0 0 4px' }}>{t('welcomeTitle')}</p>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', margin: 0 }}>{t('welcomeSubtitle')}</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, width: '100%', maxWidth: 480 }}>
        <div style={{ flex: 1, height: 1, background: 'var(--border-dim)' }} />
        <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', letterSpacing: '0.1em' }}>
          {language === 'ar' ? 'أمثلة' : 'EXAMPLES'}
        </span>
        <div style={{ flex: 1, height: 1, background: 'var(--border-dim)' }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, width: '100%', maxWidth: 480 }}>
        {examplePrompts.map((p, i) => (
          <button
            key={i}
            onClick={() => onExampleClick(p[language])}
            className={"welcome-prompt msg-enter stagger-" + (i + 1)}
            style={{
              padding: '12px 14px', borderRadius: 10,
              textAlign: language === 'ar' ? 'right' : 'left',
              fontSize: '0.82rem', lineHeight: 1.4,
              cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {p[language]}
          </button>
        ))}
      </div>
    </div>
  )
}
