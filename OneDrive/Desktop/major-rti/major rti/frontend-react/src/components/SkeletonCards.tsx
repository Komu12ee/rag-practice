import { Loader2 } from 'lucide-react'
import { Skeleton } from './ui/skeleton'

export default function SkeletonCards() {
  return (
    <div className="space-y-5 w-full animate-fadeIn">
      <div className="flex items-center justify-center gap-2 text-sm text-slate-400 py-1">
        <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
        Running Layer A rules, RAG analysis, balancing & synthesis…
      </div>

      {/* Recommendation */}
      <div className="surface p-6 space-y-4">
        <div className="flex items-center gap-4">
          <Skeleton className="h-12 w-12 rounded-2xl" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
      </div>

      {/* Balancer */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[0, 1].map(i => (
          <div key={i} className="surface p-5 space-y-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ))}
      </div>

      {/* Statutory */}
      <div className="surface p-5 space-y-3">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    </div>
  )
}
