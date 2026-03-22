import type { TriageLevel } from '../types'
import TriageBadge from './TriageBadge'
import { useLanguage } from '../context/LanguageContext'

interface Props { level?: TriageLevel; isStreaming: boolean }

const clsMap: Record<TriageLevel, string> = {
  GREEN: 'badge-green', YELLOW: 'badge-yellow', RED: 'badge-red',
}
const labelMap: Record<TriageLevel, 'triageGreen' | 'triageYellow' | 'triageRed'> = {
  GREEN: 'triageGreen', YELLOW: 'triageYellow', RED: 'triageRed',
}

export default function PulsingTriageBadge({ level, isStreaming }: Props) {
  const { t } = useLanguage()

  if (!isStreaming) return level ? <TriageBadge level={level} /> : null

  if (!level) {
    return (
      <span className="badge-analyzing" style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 12px', borderRadius: 20, fontSize: '0.78rem', fontWeight: 500,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-dim)', display: 'inline-block' }} />
        {t('analyzing')}
      </span>
    )
  }

  return (
    <span className={clsMap[level]} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 12px', borderRadius: 20, fontSize: '0.78rem', fontWeight: 600,
      animation: 'badge-pulse 1.4s ease-in-out infinite',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
      {t(labelMap[level])}
    </span>
  )
}
