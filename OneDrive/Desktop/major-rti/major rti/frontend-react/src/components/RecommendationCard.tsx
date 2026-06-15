import { CheckCircle2, AlertTriangle, XCircle, Send, Target } from 'lucide-react'
import { Badge } from './ui/badge'
import { Recommendation } from '../lib/types'

interface RecommendationCardProps {
  recommendation: Recommendation
}

const CONFIG = {
  APPROVE: {
    icon: CheckCircle2,
    accent: 'emerald',
    title: 'Approve — Disclose Entire Record',
  },
  PARTIALLY_APPROVE: {
    icon: AlertTriangle,
    accent: 'amber',
    title: 'Partially Approve — Redact & Sever (Section 10)',
  },
  REJECT: {
    icon: XCircle,
    accent: 'red',
    title: 'Reject Request (Section 8 / 9)',
  },
  TRANSFER: {
    icon: Send,
    accent: 'blue',
    title: 'Transfer Directive (Section 6(3))',
  },
} as const

const ACCENT: Record<string, { ring: string; glow: string; chip: string; icon: string; bar: string }> = {
  emerald: {
    ring: 'ring-emerald-200/70 dark:ring-emerald-800/50',
    glow: 'from-emerald-500/10',
    chip: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
    icon: 'text-emerald-600 dark:text-emerald-400',
    bar: 'bg-emerald-500',
  },
  amber: {
    ring: 'ring-amber-200/70 dark:ring-amber-800/50',
    glow: 'from-amber-500/10',
    chip: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
    icon: 'text-amber-600 dark:text-amber-400',
    bar: 'bg-amber-500',
  },
  red: {
    ring: 'ring-red-200/70 dark:ring-red-800/50',
    glow: 'from-red-500/10',
    chip: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
    icon: 'text-red-600 dark:text-red-400',
    bar: 'bg-red-500',
  },
  blue: {
    ring: 'ring-blue-200/70 dark:ring-blue-800/50',
    glow: 'from-blue-500/10',
    chip: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
    icon: 'text-blue-600 dark:text-blue-400',
    bar: 'bg-blue-500',
  },
  slate: {
    ring: 'ring-slate-200/70 dark:ring-slate-700',
    glow: 'from-slate-500/5',
    chip: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    icon: 'text-slate-500',
    bar: 'bg-slate-400',
  },
}

export default function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const { action, confidence, reasoning, citations, timeline } = recommendation
  const cfg = CONFIG[action] || { icon: Target, accent: 'slate', title: action }
  const a = ACCENT[cfg.accent]
  const Icon = cfg.icon

  const confidenceVariant =
    confidence === 'HIGH' ? 'success' : confidence === 'MEDIUM' ? 'warning' : 'destructive'

  return (
    <div className={`relative overflow-hidden rounded-2xl bg-white dark:bg-slate-900 ring-1 ${a.ring} shadow-card`}>
      <div className={`absolute inset-x-0 top-0 h-1 ${a.bar}`} />
      <div className={`pointer-events-none absolute -top-16 -right-16 h-48 w-48 rounded-full bg-gradient-to-br ${a.glow} to-transparent blur-2xl`} />

      <div className="relative p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <span className={`grid place-items-center h-12 w-12 shrink-0 rounded-2xl ${a.chip}`}>
              <Icon className={`h-6 w-6 ${a.icon}`} />
            </span>
            <div>
              <span className="eyebrow">Synthesised AI recommendation</span>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mt-0.5 leading-snug">
                {cfg.title}
              </h3>
            </div>
          </div>
          <Badge variant={confidenceVariant}>{confidence} confidence</Badge>
        </div>

        <div className="mt-5 space-y-5">
          <div>
            <span className="eyebrow">Primary legal reasoning</span>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mt-1.5">{reasoning}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow mr-1">Statutory citations</span>
            {citations.length > 0 ? (
              citations.map(c => <Badge key={c} variant="outline">{c}</Badge>)
            ) : (
              <span className="text-xs text-slate-400">None</span>
            )}
          </div>

          <div className="flex gap-3 rounded-xl border border-slate-200/70 bg-slate-50/70 p-4 dark:border-slate-700/60 dark:bg-slate-800/40">
            <Target className="h-5 w-5 shrink-0 text-brand-500 mt-0.5" />
            <div>
              <span className="eyebrow text-brand-600 dark:text-brand-400">Suggested PIO action directive</span>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100 mt-1">{timeline}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
