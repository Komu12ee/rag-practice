import { Check, AlertTriangle, Scale, Unlock, Lock } from 'lucide-react'
import { BalancerOutput } from '../lib/types'

interface BalancerGridProps {
  balance: BalancerOutput
}

export default function BalancerGrid({ balance }: BalancerGridProps) {
  const { pro_disclosure_argument, pro_exemption_argument, balancing_factors } = balance

  const proDisclosureList = pro_disclosure_argument.split(' | ').filter(Boolean)
  const proExemptionList = pro_exemption_argument.split(' | ').filter(Boolean)

  return (
    <section className="space-y-4">

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pro disclosure */}
        <div className="rounded-2xl border border-emerald-200/70 bg-emerald-50/50 p-5 dark:border-emerald-800/50 dark:bg-emerald-950/20">
          <div className="flex items-center gap-2 mb-4">
            <span className="grid place-items-center h-8 w-8 rounded-lg bg-emerald-100 dark:bg-emerald-900/40">
              <Unlock className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            </span>
            <span className="text-xs font-bold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
              Case for disclosure
            </span>
          </div>
          <ul className="space-y-3">
            {proDisclosureList.map((arg, idx) => (
              <li key={idx} className="flex gap-2.5">
                <Check className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" strokeWidth={2.5} />
                <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{arg}</p>
              </li>
            ))}
          </ul>
        </div>

        {/* Pro exemption */}
        <div className="rounded-2xl border border-red-200/70 bg-red-50/50 p-5 dark:border-red-800/50 dark:bg-red-950/20">
          <div className="flex items-center gap-2 mb-4">
            <span className="grid place-items-center h-8 w-8 rounded-lg bg-red-100 dark:bg-red-900/40">
              <Lock className="h-4 w-4 text-red-600 dark:text-red-400" />
            </span>
            <span className="text-xs font-bold uppercase tracking-wide text-red-700 dark:text-red-300">
              Case for exemption
            </span>
          </div>
          <ul className="space-y-3">
            {proExemptionList.map((arg, idx) => (
              <li key={idx} className="flex gap-2.5">
                <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{arg}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Proportionality */}
      <div className="flex gap-3 rounded-2xl border border-amber-200/70 bg-amber-50/60 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
        <span className="grid place-items-center h-9 w-9 shrink-0 rounded-xl bg-amber-100 dark:bg-amber-900/40">
          <Scale className="h-[18px] w-[18px] text-amber-600 dark:text-amber-400" />
        </span>
        <div>
          <span className="text-xs font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300">
            Key balancing factors · proportionality test
          </span>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mt-1">{balancing_factors}</p>
        </div>
      </div>
    </section>
  )
}
