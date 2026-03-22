import { useState } from 'react'
import type { Source } from '../types'
import { useLanguage } from '../context/LanguageContext'

export default function SourceCitation({ sources }: { sources: Source[] }) {
  const [isOpen, setIsOpen] = useState(false)
  const { t } = useLanguage()

  if (!sources.length) return null

  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="hakim-source-btn"
      >
        <svg
          width="12" height="12"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          style={{ transition: 'transform 0.2s', transform: isOpen ? 'rotate(90deg)' : 'none' }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        {t('sources')} ({sources.length})
      </button>

      {isOpen && (
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {sources.map((source, i) => (
            <div key={i} className="hakim-source-card">
              {source.title && (
                <p className="hakim-source-title" style={{ margin: 0 }}>
                  {source.title}
                </p>
              )}
              {source.content && (
                <p className="hakim-source-content" style={{
                  margin: 0, display: '-webkit-box',
                  WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                }}>
                  {source.content}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
