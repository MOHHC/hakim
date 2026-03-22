import { useLanguage } from '../context/LanguageContext'

const examplePrompts = [
  { ar: 'عندي وجع راس من يومين', en: "I've had a headache for two days" },
  { ar: 'ابني عمرو 5 سنين وعندو حرارة', en: 'My 5-year-old son has a fever' },
  { ar: 'بحس بضيق نفس لما امشي', en: 'I feel short of breath when walking' },
  { ar: 'عندي وجع بطن وغثيان', en: 'I have stomach pain and nausea' },
]

function FeatureCard({ icon, title, desc, index }: { icon: React.ReactNode; title: string; desc: string; index: number }) {
  return (
    <div className={`feature-card anim-scale-in delay-${index + 3}`}>
      <div className="feature-icon">{icon}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--text)', marginBottom: 3 }}>{title}</div>
        <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', lineHeight: 1.45 }}>{desc}</div>
      </div>
    </div>
  )
}

function HowItWorksStep({ number, title, desc, index }: { number: string; title: string; desc: string; index: number }) {
  return (
    <div className={`anim-scale-in delay-${index + 6}`} style={{
      display: 'flex', alignItems: 'flex-start', gap: 14,
      padding: '14px 16px', borderRadius: 12,
      background: 'var(--card)', border: '1px solid var(--border-dim)',
      boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      transition: 'all 0.25s ease',
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        background: 'var(--green-bg)', border: '1px solid var(--gold)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
        fontFamily: 'var(--font-body)',
        fontSize: '0.78rem', fontWeight: 700,
        color: 'var(--gold)',
      }}>{number}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{title}</div>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', lineHeight: 1.4 }}>{desc}</div>
      </div>
    </div>
  )
}

/* Islamic geometric ornament (8-pointed star) rendered as SVG */
function OrnamentStar({ size = 40, opacity = 0.08 }: { size?: number; opacity?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" style={{ opacity }} aria-hidden="true">
      <polygon points="20,2 24,14 36,14 26,22 30,34 20,26 10,34 14,22 4,14 16,14"
        stroke="var(--gold)" strokeWidth="0.8" fill="none" />
      <circle cx="20" cy="20" r="6" stroke="var(--gold)" strokeWidth="0.5" fill="none" />
    </svg>
  )
}

export default function WelcomeScreen({ onExampleClick }: { onExampleClick: (t: string) => void }) {
  const { t, language } = useLanguage()
  return (
    <div className="welcome-hero" style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'flex-start',
      padding: '32px 20px 24px', overflow: 'auto',
    }}>
      {/* Decorative ornament rings */}
      <div className="ornament-ring ornament-ring-1" aria-hidden="true" />
      <div className="ornament-ring ornament-ring-2" aria-hidden="true" />
      <div className="ornament-ring ornament-ring-3" aria-hidden="true" />

      {/* Floating corner ornaments */}
      <div aria-hidden="true" style={{ position: 'absolute', top: 24, left: 24, opacity: 0 }} className="anim-fade-in delay-1">
        <OrnamentStar size={36} opacity={0.06} />
      </div>
      <div aria-hidden="true" style={{ position: 'absolute', top: 24, right: 24, opacity: 0 }} className="anim-fade-in delay-2">
        <OrnamentStar size={28} opacity={0.05} />
      </div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: 80, left: 40, opacity: 0 }} className="anim-fade-in delay-3">
        <OrnamentStar size={24} opacity={0.04} />
      </div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: 100, right: 36, opacity: 0 }} className="anim-fade-in delay-4">
        <OrnamentStar size={32} opacity={0.05} />
      </div>

      {/* Watermark */}
      <div aria-hidden="true" style={{
        position: 'absolute', fontSize: '22vw',
        fontFamily: 'var(--font-display)', fontWeight: 700,
        color: 'var(--gold)', opacity: 0.03,
        userSelect: 'none', pointerEvents: 'none',
        top: '50%', left: '50%', transform: 'translate(-50%, -55%)',
        whiteSpace: 'nowrap', lineHeight: 1,
      }}>حكيم</div>

      {/* Logo + Title */}
      <div className="anim-scale-in delay-1" style={{ textAlign: 'center', marginBottom: 28, position: 'relative', zIndex: 1 }}>
        <div className="logo-circle">
          <svg width="34" height="34" viewBox="0 0 40 40" fill="none">
            <polygon points="20,2 25,9 33,9 38,16 33,24 25,24 20,31 15,24 7,24 2,16 7,9 15,9"
              fill="none" stroke="var(--gold)" strokeWidth="1.5" opacity="0.7" />
            <polygon points="20,6 24,11 30,11 34,16 30,22 24,22 20,27 16,22 10,22 6,16 10,11 16,11"
              fill="none" stroke="var(--gold)" strokeWidth="0.6" opacity="0.3" />
            <circle cx="20" cy="16" r="3" fill="var(--gold)" opacity="0.9" />
            <circle cx="20" cy="16" r="5.5" fill="none" stroke="var(--gold)" strokeWidth="0.5" opacity="0.2" />
          </svg>
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(2.2rem, 7vw, 3.6rem)',
          fontWeight: 700,
          fontStyle: language === 'en' ? 'italic' : 'normal',
          color: 'var(--gold)',
          margin: '0 0 8px',
          letterSpacing: language === 'en' ? '0.02em' : '0',
          lineHeight: 1.1,
        }}>{t('appName')}</h1>
        <p style={{ fontSize: '0.94rem', color: 'var(--text-muted)', margin: '0 0 4px', lineHeight: 1.5 }}>{t('welcomeTitle')}</p>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', margin: 0 }}>{t('welcomeSubtitle')}</p>
      </div>

      {/* Stat pills */}
      <div className="anim-fade-in delay-2" style={{
        display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap', justifyContent: 'center',
        position: 'relative', zIndex: 1,
      }}>
        <div className="stat-pill">
          <span className="stat-dot" />
          <span>{language === 'ar' ? 'مجاني ومفتوح المصدر' : 'Free & Open Source'}</span>
        </div>
        <div className="stat-pill">
          <span className="stat-dot" style={{ background: 'var(--green)' }} />
          <span>{language === 'ar' ? 'ثلاثي التصنيف' : '3-Level Triage'}</span>
        </div>
        <div className="stat-pill">
          <span className="stat-dot" style={{ background: 'var(--yellow)' }} />
          <span>{language === 'ar' ? 'عربي ولبناني' : 'Arabic & Lebanese'}</span>
        </div>
      </div>

      {/* Feature Cards */}
      <div style={{
        display: 'flex', gap: 12, width: '100%', maxWidth: 580,
        marginBottom: 28, flexWrap: 'wrap', justifyContent: 'center',
        position: 'relative', zIndex: 1,
      }}>
        <FeatureCard
          index={0}
          title={t('featureAnalysis')}
          desc={t('featureAnalysisDesc')}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          }
        />
        <FeatureCard
          index={1}
          title={t('featureTriage')}
          desc={t('featureTriageDesc')}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          }
        />
        <FeatureCard
          index={2}
          title={t('featurePrivate')}
          desc={t('featurePrivateDesc')}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0110 0v4" />
            </svg>
          }
        />
      </div>

      {/* Ornamental divider */}
      <div className="ornamental-divider anim-fade-in delay-5" style={{ maxWidth: 520, marginBottom: 14, position: 'relative', zIndex: 1 }}>
        <div className="ornamental-divider-line" />
        <div className="ornamental-divider-diamond" />
        <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', letterSpacing: '0.1em', whiteSpace: 'nowrap' }}>
          {t('tryAsking')}
        </span>
        <div className="ornamental-divider-diamond" />
        <div className="ornamental-divider-line" />
      </div>

      {/* Example Prompts */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10,
        width: '100%', maxWidth: 540,
        position: 'relative', zIndex: 1,
      }}>
        {examplePrompts.map((p, i) => (
          <button
            key={i}
            onClick={() => onExampleClick(p[language])}
            className={`welcome-prompt anim-scale-in delay-${i + 6}`}
            style={{
              padding: '13px 16px', borderRadius: 12,
              textAlign: language === 'ar' ? 'right' : 'left',
              fontSize: '0.84rem', lineHeight: 1.5,
              cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: 10,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.5 }}>
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
            <span>{p[language]}</span>
          </button>
        ))}
      </div>

      {/* How It Works section */}
      <div className="anim-fade-in delay-5" style={{
        marginTop: 32, width: '100%', maxWidth: 540,
        position: 'relative', zIndex: 1,
      }}>
        <div className="ornamental-divider" style={{ marginBottom: 18 }}>
          <div className="ornamental-divider-line" />
          <div className="ornamental-divider-diamond" />
          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', letterSpacing: '0.1em', whiteSpace: 'nowrap' }}>
            {language === 'ar' ? 'كيف بيشتغل' : 'How It Works'}
          </span>
          <div className="ornamental-divider-diamond" />
          <div className="ornamental-divider-line" />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <HowItWorksStep
            index={0}
            number="1"
            title={language === 'ar' ? 'اوصف الأعراض' : 'Describe Symptoms'}
            desc={language === 'ar' ? 'اكتب شو عم تحس فيه بالعربي أو بالفرانكو' : 'Type what you feel in Arabic, Franco-Arab, or English'}
          />
          <HowItWorksStep
            index={1}
            number="2"
            title={language === 'ar' ? 'حكيم بيحلل' : 'Hakim Analyzes'}
            desc={language === 'ar' ? 'بيستخدم ذكاء اصطناعي ومراجع طبية موثوقة' : 'Uses AI with trusted medical references and RAG'}
          />
          <HowItWorksStep
            index={2}
            number="3"
            title={language === 'ar' ? 'بتاخد التقييم' : 'Get Your Assessment'}
            desc={language === 'ar' ? 'مستوى الاستعجال + حالات محتملة + خطوات منصوح فيها' : 'Urgency level + possible conditions + recommended steps'}
          />
        </div>
      </div>

      {/* Bottom spacing */}
      <div style={{ height: 20, flexShrink: 0 }} />
    </div>
  )
}
