import type { TriageLevel } from '../types'
import { useLanguage } from '../context/LanguageContext'

const config: Record<
  TriageLevel,
  { bg: string; text: string; dot: string; labelKey: 'triageGreen' | 'triageYellow' | 'triageRed' }
> = {
  GREEN: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    text: 'text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500',
    labelKey: 'triageGreen',
  },
  YELLOW: {
    bg: 'bg-amber-100 dark:bg-amber-900/40',
    text: 'text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500',
    labelKey: 'triageYellow',
  },
  RED: {
    bg: 'bg-red-100 dark:bg-red-900/40',
    text: 'text-red-700 dark:text-red-300',
    dot: 'bg-red-500',
    labelKey: 'triageRed',
  },
}

export default function TriageBadge({ level }: { level: TriageLevel }) {
  const { t } = useLanguage()
  const { bg, text, dot, labelKey } = config[level]

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${bg} ${text}`}
    >
      <span className={`w-2 h-2 rounded-full ${dot}`} />
      {t(labelKey)}
    </span>
  )
}
