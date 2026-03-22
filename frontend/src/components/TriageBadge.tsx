import type { TriageLevel } from '../types'
import { useLanguage } from '../context/LanguageContext'

const cfg: Record<TriageLevel, { cls: string; labelKey: 'triageGreen' | 'triageYellow' | 'triageRed' }> = {
  GREEN:  { cls: 'badge-green',  labelKey: 'triageGreen' },
  YELLOW: { cls: 'badge-yellow', labelKey: 'triageYellow' },
  RED:    { cls: 'badge-red',    labelKey: 'triageRed' },
}

export default function TriageBadge({ level }: { level: TriageLevel }) {
  const { t } = useLanguage()
  const { cls, labelKey } = cfg[level]
  return (
    <span className={cls} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 12px', borderRadius: 20,
      fontSize: '0.78rem', fontWeight: 600,
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
      {t(labelKey)}
    </span>
  )
}
