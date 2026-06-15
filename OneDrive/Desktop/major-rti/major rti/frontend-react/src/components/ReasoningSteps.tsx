interface ReasoningStepsProps {
  reasoning: string
}

export default function ReasoningSteps({ reasoning }: ReasoningStepsProps) {
  if (!reasoning || !reasoning.trim()) {
    return (
      <div className="text-slate-400 dark:text-slate-500 italic text-xs">
        No reasoning details available.
      </div>
    )
  }

  const steps = reasoning.split('|').map(s => s.trim()).filter(Boolean)

  const getEmoji = (stepText: string) => {
    const stepLower = stepText.toLowerCase()
    if (stepLower.includes('keyword pass')) return '🔑'
    if (stepLower.includes('embedding pass')) return '🧠'
    if (stepLower.includes('llm pass')) return '🤖'
    if (stepLower.includes('llm confirms') || stepLower.includes('llm agrees')) return '✅'
    if (stepLower.includes('llm disagrees') || stepLower.includes('prefer')) return '🔄'
    if (stepLower.includes('overlap risk')) return '⚠️'
    if (stepLower.includes('transfer under') || stepLower.includes('section 6(3)')) return '📤'
    return 'ℹ️'
  }

  return (
    <div className="border border-slate-200 dark:border-slate-800 rounded divide-y divide-slate-100 dark:divide-slate-800/60 overflow-hidden">
      {steps.map((step, idx) => {
        const emoji = getEmoji(step)
        let label = ''
        let value = step

        if (step.includes(':')) {
          const parts = step.split(':')
          label = parts[0].trim()
          value = parts.slice(1).join(':').trim()
        }

        return (
          <div
            key={idx}
            className={`flex items-start gap-3 px-4 py-3 text-xs leading-relaxed ${
              idx % 2 === 0
                ? 'bg-white dark:bg-slate-900'
                : 'bg-slate-50/50 dark:bg-slate-800/20'
            }`}
          >
            <span className="text-base select-none shrink-0">{emoji}</span>
            <div className="text-slate-600 dark:text-slate-300">
              {label && (
                <span className="font-bold text-slate-800 dark:text-slate-100 mr-1.5 uppercase tracking-wider text-[10px]">
                  {label}:
                </span>
              )}
              <span>{value}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
