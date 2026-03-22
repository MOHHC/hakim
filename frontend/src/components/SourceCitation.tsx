import { useState } from 'react'
import type { Source } from '../types'
import { useLanguage } from '../context/LanguageContext'

export default function SourceCitation({ sources }: { sources: Source[] }) {
  const [isOpen, setIsOpen] = useState(false)
  const { t } = useLanguage()

  if (!sources.length) return null

  return (
    <div className="mt-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1 text-xs text-teal-600 dark:text-teal-400 hover:underline"
      >
        <svg
          className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
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
        <div className="mt-1.5 space-y-1.5">
          {sources.map((source, i) => (
            <div
              key={i}
              className="text-xs bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 border border-slate-200 dark:border-slate-700"
            >
              {source.title && (
                <p className="font-medium text-slate-700 dark:text-slate-300">
                  {source.title}
                </p>
              )}
              {source.content && (
                <p className="text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
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
