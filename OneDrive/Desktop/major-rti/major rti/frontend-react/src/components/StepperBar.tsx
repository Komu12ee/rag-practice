import React from 'react'
import { Check, Lock } from 'lucide-react'
import { Step } from '../lib/stepMachine'

interface StepperBarProps {
  currentStep: Step
}

const STEPS = [
  { id: 'input', label: 'Input & Routing', hint: 'Extract & classify' },
  { id: 'review_extraction', label: 'Verify Parameters', hint: 'Human interlock' },
  { id: 'exemption_analysis', label: 'Exemption Evaluation', hint: 'Analyse & decide' },
]

const ORDER = ['input', 'review_extraction', 'exemption_analysis']

export default function StepperBar({ currentStep }: StepperBarProps) {
  const getStepState = (stepId: string) => {
    if (currentStep === 'completed') return 'completed'
    const currentIndex = ORDER.indexOf(currentStep)
    const targetIndex = ORDER.indexOf(stepId)
    if (currentIndex > targetIndex) return 'completed'
    if (currentIndex === targetIndex) return 'active'
    return 'locked'
  }

  return (
    <div className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded p-4">
      <div className="flex items-center">
        {STEPS.map((step, idx) => {
          const state = getStepState(step.id)
          const isLast = idx === STEPS.length - 1
          return (
            <React.Fragment key={step.id}>
              <div className="flex items-center gap-3 shrink-0">
                <div
                  className={`relative grid place-items-center h-8 w-8 rounded-full text-xs font-bold transition-all ${
                    state === 'completed'
                      ? 'bg-emerald-600 text-white'
                      : state === 'active'
                      ? 'bg-[#1E3A5F] text-white ring-2 ring-slate-300 dark:ring-slate-700'
                      : 'bg-slate-100 text-slate-400 border border-slate-200 dark:bg-slate-800 dark:text-slate-500 dark:border-slate-700'
                  }`}
                >
                  {state === 'completed' ? (
                    <Check className="h-4.5 w-4.5" strokeWidth={3} />
                  ) : state === 'locked' ? (
                    <Lock className="h-3.5 w-3.5" />
                  ) : (
                    idx + 1
                  )}
                </div>
                <div className="hidden sm:block leading-tight">
                  <p
                    className={`text-xs font-bold uppercase tracking-wider ${
                      state === 'locked'
                        ? 'text-slate-400 dark:text-slate-600'
                        : 'text-slate-800 dark:text-slate-200'
                    }`}
                  >
                    {step.label}
                  </p>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500">{step.hint}</p>
                </div>
              </div>
              {!isLast && (
                <div className="flex-1 mx-3 sm:mx-5 h-[1.5px] bg-slate-205 dark:bg-slate-800">
                  <div
                    className={`h-full bg-emerald-600 transition-all duration-500 ${
                      getStepState(STEPS[idx + 1].id) !== 'locked' ? 'w-full' : 'w-0'
                    }`}
                  />
                </div>
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
