import { useState } from 'react'
import { ChevronDown, Quote } from 'lucide-react'
import { Badge } from './ui/badge'
import { StatutoryReference } from '../lib/types'

interface StatutoryCardProps {
  reference: StatutoryReference
}

export default function StatutoryCard({ reference }: StatutoryCardProps) {
  const { section, title, is_applicable, confidence_score, legal_reasoning, exact_quotes } = reference
  const [isExpanded, setIsExpanded] = useState(false)
  const pct = Math.round(confidence_score * 100)

  return (
    <div className="surface p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center h-9 min-w-9 px-2 rounded-lg bg-slate-100 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300 font-mono">
            §
          </span>
          <h4 className="text-sm font-bold text-slate-900 dark:text-white leading-tight">
            {section}
            {title ? <span className="font-medium text-slate-500 dark:text-slate-400"> — {title}</span> : ''}
          </h4>
        </div>
        <Badge variant={is_applicable ? 'destructive' : 'success'}>
          {is_applicable ? '🔴 APPLICABLE' : '🟢 NOT APPLICABLE'}
        </Badge>
      </div>

      {/* Similarity meter */}
      <div className="flex items-center gap-3">
        <span className="eyebrow shrink-0">RAG similarity</span>
        <div className="flex-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-brand-gradient transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 tabular-nums w-9 text-right">{pct}%</span>
      </div>

      <div>
        <span className="eyebrow">Statutory analysis</span>
        <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mt-1">{legal_reasoning}</p>
      </div>

      {exact_quotes && exact_quotes.length > 0 && (
        <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1.5 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
          >
            <Quote className="h-3.5 w-3.5" />
            Exact statutory quotes cited ({exact_quotes.length})
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
          </button>

          {isExpanded && (
            <div className="mt-3 space-y-2 animate-fadeIn">
              {exact_quotes.map((quote, idx) => (
                <blockquote
                  key={idx}
                  className="rounded-lg border-l-2 border-brand-400 bg-slate-50 px-3.5 py-2.5 text-xs italic leading-relaxed text-slate-600 dark:bg-slate-800/50 dark:text-slate-400"
                >
                  “{quote}”
                </blockquote>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
