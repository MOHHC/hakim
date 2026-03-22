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
      <div className="hakim-panel">
        <div className="hakim-panel-header">
          <h3 style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', margin: 0 }}>
            {t('history')}
          </h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', padding: 2 }}
          >
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div style={{ maxHeight: 256, overflowY: 'auto' }} className="chat-scroll">
          {conversations.length === 0 ? (
            <p style={{ padding: '24px 16px', fontSize: '0.875rem', color: 'var(--text-dim)', textAlign: 'center', margin: 0 }}>
              {t('noHistory')}
            </p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`hakim-panel-item${conv.id === activeId ? ' active' : ''}`}
                onClick={() => {
                  onSelect(conv.id)
                  onClose()
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <p style={{ fontSize: '0.875rem', color: 'var(--text)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {conv.title || '...'}
                  </p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', margin: '2px 0 0' }}>
                    {new Date(conv.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(conv.id)
                  }}
                  style={{
                    padding: 4, background: 'none', border: 'none',
                    color: 'var(--text-dim)', cursor: 'pointer',
                    flexShrink: 0, marginInlineStart: 8,
                    transition: 'color 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-dim)')}
                >
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
