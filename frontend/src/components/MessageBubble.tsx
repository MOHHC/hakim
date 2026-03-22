import type { Message } from '../types'
import TriageBadge from './TriageBadge'
import SourceCitation from './SourceCitation'
import TypingIndicator from './TypingIndicator'
import { useLanguage } from '../context/LanguageContext'

export default function MessageBubble({ message }: { message: Message }) {
  const { t } = useLanguage()
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-teal-600 text-white rounded-ee-sm'
            : message.isError
              ? 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800 rounded-es-sm'
              : message.isBlocked
                ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800 rounded-es-sm'
                : 'bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 shadow-sm border border-slate-200 dark:border-slate-700 rounded-es-sm'
        }`}
      >
        {message.isStreaming && !message.content ? (
          <TypingIndicator />
        ) : (
          <>
            <p className="whitespace-pre-wrap text-sm sm:text-base leading-relaxed">
              {message.content}
            </p>

            {message.triageResult && !message.isStreaming && (
              <div className="mt-3 space-y-2">
                <TriageBadge level={message.triageResult.triage_level} />

                {message.triageResult.possible_conditions.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-2">
                      {t('possibleConditions')}
                    </p>
                    <ul className="text-xs text-slate-600 dark:text-slate-300 mt-1 space-y-0.5">
                      {message.triageResult.possible_conditions.map((c, i) => (
                        <li key={i}>{'\u2022'} {c}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {message.triageResult.recommended_actions.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-2">
                      {t('recommendedActions')}
                    </p>
                    <ul className="text-xs text-slate-600 dark:text-slate-300 mt-1 space-y-0.5">
                      {message.triageResult.recommended_actions.map((a, i) => (
                        <li key={i}>{'\u2022'} {a}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <SourceCitation sources={message.triageResult.sources} />

                {message.triageResult.disclaimer && (
                  <p className="text-xs text-slate-400 dark:text-slate-500 mt-2 italic">
                    {message.triageResult.disclaimer}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
