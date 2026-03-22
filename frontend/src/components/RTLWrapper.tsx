import type { ReactNode } from 'react'
import { useLanguage } from '../context/LanguageContext'

export default function RTLWrapper({ children }: { children: ReactNode }) {
  const { dir } = useLanguage()
  return (
    <div dir={dir} className="min-h-screen flex flex-col">
      {children}
    </div>
  )
}
