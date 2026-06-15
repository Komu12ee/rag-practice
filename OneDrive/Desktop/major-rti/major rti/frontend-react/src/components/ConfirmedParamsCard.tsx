import { ExtractedInformation } from '../lib/types'

interface ConfirmedParamsCardProps {
  info: ExtractedInformation
}

export default function ConfirmedParamsCard({ info }: ConfirmedParamsCardProps) {
  if (!info) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 text-xs">
      <div>
        <span className="eyebrow block mb-1">Information Type</span>
        <span className="font-bold text-slate-800 dark:text-slate-100 uppercase tracking-wider">
          {info.classification_type || 'N/A'}
        </span>
      </div>

      <div>
        <span className="eyebrow block mb-1">Procurement Tender Status</span>
        <span className="font-medium text-slate-800 dark:text-slate-200 capitalize">
          {info.procurement_status ? info.procurement_status.replace('_', ' ') : 'N/A'}
        </span>
      </div>

      <div className="md:col-span-2">
        <span className="eyebrow block mb-1">Extracted Entities</span>
        <span className="font-medium text-slate-800 dark:text-slate-300 leading-relaxed">
          {info.entities && info.entities.length > 0 ? info.entities.join(', ') : 'None'}
        </span>
      </div>

      <div className="md:col-span-2">
        <span className="eyebrow block mb-1">IT Systems Mentioned</span>
        <span className="font-medium text-slate-800 dark:text-slate-300 leading-relaxed">
          {info.systems && info.systems.length > 0 ? info.systems.join(', ') : 'None'}
        </span>
      </div>

      <div>
        <span className="eyebrow block mb-1">Personal Data Flag</span>
        <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
          {info.personal_data ? (
            <>
              <span className="text-red-500 font-bold">🔴</span> Yes (Personal Privacy Risk)
            </>
          ) : (
            <>
              <span className="text-green-500 font-bold">🟢</span> No personal private data
            </>
          )}
        </span>
      </div>

      <div>
        <span className="eyebrow block mb-1">Section 8(2) Override Flag</span>
        <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
          {info.public_interest ? (
            <>
              <span className="text-amber-500 font-bold">🔥</span> Yes (Allegations of corruption/human rights)
            </>
          ) : (
            <>
              <span className="text-green-500 font-bold">🟢</span> None alleged
            </>
          )}
        </span>
      </div>

      {info.explanation && (
        <div className="md:col-span-2 border-t border-slate-100 dark:border-slate-800/60 pt-3 mt-1">
          <span className="eyebrow block mb-1">Extraction Explanation</span>
          <p className="text-slate-600 dark:text-slate-400 italic leading-relaxed">
            {info.explanation}
          </p>
        </div>
      )}
    </div>
  )
}
