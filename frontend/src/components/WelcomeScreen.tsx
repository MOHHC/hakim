import { useLanguage } from '../context/LanguageContext'

const examplePrompts = [
  {
    ar: '\u0639\u0646\u062f\u064a \u0648\u062c\u0639 \u0631\u0627\u0633 \u0645\u0646 \u064a\u0648\u0645\u064a\u0646',
    en: "I've had a headache for two days",
  },
  {
    ar: '\u0627\u0628\u0646\u064a \u0639\u0645\u0631\u0648 5 \u0633\u0646\u064a\u0646 \u0648\u0639\u0646\u062f\u0648 \u062d\u0631\u0627\u0631\u0629',
    en: 'My 5-year-old son has a fever',
  },
  {
    ar: '\u0628\u062d\u0633 \u0628\u0636\u064a\u0642 \u0646\u0641\u0633 \u0644\u0645\u0627 \u0627\u0645\u0634\u064a',
    en: 'I feel short of breath when walking',
  },
  {
    ar: '\u0639\u0646\u062f\u064a \u0648\u062c\u0639 \u0628\u0637\u0646 \u0648\u063a\u062b\u064a\u0627\u0646',
    en: 'I have stomach pain and nausea',
  },
]

export default function WelcomeScreen({
  onExampleClick,
}: {
  onExampleClick: (text: string) => void
}) {
  const { t, language } = useLanguage()

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 sm:py-12">
      {/* Logo */}
      <div className="w-16 h-16 rounded-2xl bg-teal-600 flex items-center justify-center mb-4 shadow-lg shadow-teal-600/20">
        <svg
          className="w-8 h-8 text-white"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
          />
        </svg>
      </div>

      <h1 className="text-3xl font-bold text-teal-700 dark:text-teal-400 mb-1">
        {t('appName')}
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-8">
        {t('tagline')}
      </p>

      <h2 className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">
        {t('welcomeTitle')}
      </h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6 text-center max-w-md">
        {t('welcomeSubtitle')}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
        {examplePrompts.map((prompt, i) => (
          <button
            key={i}
            onClick={() => onExampleClick(prompt[language])}
            className="text-start px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/50 text-sm text-slate-700 dark:text-slate-300 hover:border-teal-400 dark:hover:border-teal-500 hover:bg-teal-50 dark:hover:bg-teal-950/20 transition-colors"
          >
            {prompt[language]}
          </button>
        ))}
      </div>
    </div>
  )
}
