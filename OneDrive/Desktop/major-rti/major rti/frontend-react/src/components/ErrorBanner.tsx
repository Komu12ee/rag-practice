import { AlertCircle } from 'lucide-react'

interface ErrorBannerProps {
  message: string
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  if (!message) return null

  return (
    <div className="flex gap-3 items-start rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-900/50 dark:bg-red-950/30 animate-fadeIn">
      <span className="grid place-items-center h-7 w-7 shrink-0 rounded-lg bg-red-100 dark:bg-red-900/40">
        <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
      </span>
      <div className="pt-0.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">
          Something went wrong
        </p>
        <p className="text-sm text-red-800 dark:text-red-300 mt-0.5">{message}</p>
      </div>
    </div>
  )
}
