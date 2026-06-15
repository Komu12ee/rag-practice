import React, { useState } from 'react'
import { ChevronRight } from 'lucide-react'

interface CollapsibleProps {
  title: string | React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  className?: string
}

export default function Collapsible({ title, children, defaultOpen = false, className = '' }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <details
      open={isOpen}
      onToggle={(e) => setIsOpen((e.target as HTMLDetailsElement).open)}
      className={`group border border-slate-200 dark:border-slate-800 rounded-lg bg-white dark:bg-slate-900 transition-all ${className}`}
    >
      <summary className="flex items-center justify-between gap-3 px-4 py-3 font-medium text-slate-800 dark:text-slate-200 cursor-pointer list-none select-none hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
        <span className="flex items-center gap-2">
          {title}
        </span>
        <ChevronRight className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`} />
      </summary>
      <div className="border-t border-slate-100 dark:border-slate-800/60 px-4 py-4 text-sm text-slate-600 dark:text-slate-400 bg-white/50 dark:bg-slate-900/50">
        {children}
      </div>
    </details>
  )
}
