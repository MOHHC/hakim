import type { Conversation } from '../types'
import { useLanguage } from '../context/LanguageContext'

interface Props {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onClose: () => void
}

export default function SymptomHistory({
  conversations,
  activeId,
  onSelect,
  onDelete,
  onClose,
}: Props) {
  const { t } = useLanguage()

  return (
    <div className="absolute top-full mt-1 z-50 end-0 w-72 sm:w-80">
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
            {t('history')}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="max-h-64 overflow-y-auto">
          {conversations.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-400 text-center">
              {t('noHistory')}
            </p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`flex items-center justify-between px-4 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-700/50 cursor-pointer border-b border-slate-100 dark:border-slate-700/50 last:border-0 ${
                  conv.id === activeId ? 'bg-teal-50 dark:bg-teal-950/20' : ''
                }`}
                onClick={() => {
                  onSelect(conv.id)
                  onClose()
                }}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-700 dark:text-slate-300 truncate">
                    {conv.title || '...'}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {new Date(conv.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(conv.id)
                  }}
                  className="p-1 text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 shrink-0 ms-2"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
