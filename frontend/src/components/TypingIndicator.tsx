import { useEffect, useState } from 'react'
import { useLanguage } from '../context/LanguageContext'

/** How long the server may stay silent before we assume it is cold-starting. */
export const WAKING_UP_AFTER_MS = 5000

interface Props {
  /** True while the server has not answered at all yet. */
  awaitingServer?: boolean
}

export default function TypingIndicator({ awaitingServer = false }: Props) {
  const { t } = useLanguage()
  const [slow, setSlow] = useState(false)

  // The free-tier backend sleeps when idle and takes up to a minute to start.
  // Only a server that hasn't answered at all counts as waking up; a slow
  // model reply on an awake server keeps the normal "thinking" text.
  useEffect(() => {
    if (!awaitingServer) return
    const timer = setTimeout(() => setSlow(true), WAKING_UP_AFTER_MS)
    return () => clearTimeout(timer)
  }, [awaitingServer])

  const wakingUp = awaitingServer && slow

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ display: 'flex', gap: 5 }}>
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
        <span className="typing-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', display: 'inline-block' }} />
      </div>
      <span role="status" style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
        {t(wakingUp ? 'wakingUp' : 'typing')}
      </span>
    </div>
  )
}
