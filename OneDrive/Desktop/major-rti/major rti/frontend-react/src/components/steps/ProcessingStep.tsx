import { useEffect, useRef, useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import ErrorBanner from '../ErrorBanner'
import {
  routeApplication,
  extractParameters,
  evaluateExemptionsAndSynthesis,
  generatePIODraft,
} from '../../lib/api'
import {
  OCRResult,
  RoutingResult,
  ExtractedInformation,
  EvaluationResult,
} from '../../lib/types'

interface ProcessingStepProps {
  text: string
  language: string
  ocr: OCRResult | null
  onComplete: (payload: {
    routing: RoutingResult
    extraction: ExtractedInformation
    evaluation: EvaluationResult
    draft: string
    warning?: string | null
  }) => void
  onStartOver: () => void
}

const THINKING_STEPS = [
  'Reading RTI application',
  'Identifying requested information',
  'Checking department routing',
  'Extracting legal research parameters',
  'Reviewing RTI Act exemption clauses',
  'Searching statutory references',
  'Balancing disclosure and exemption grounds',
  'Drafting official RTI reply',
  'Formatting response for PIO review',
]

export default function ProcessingStep({
  text,
  language,
  ocr,
  onComplete,
  onStartOver,
}: ProcessingStepProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const startedRef = useRef(0)

  useEffect(() => {
    const runId = retryKey + 1
    startedRef.current = runId
    setError('')
    setActiveIndex(0)

    async function runFullPipeline() {
      try {
        setActiveIndex(1)
        const routingPromise = routeApplication(text, language)
        const extractionPromise = extractParameters(text)

        setActiveIndex(3)
        const [routing, extraction] = await Promise.all([routingPromise, extractionPromise])

        setActiveIndex(4)
        const evaluation = await evaluateExemptionsAndSynthesis(extraction)

        setActiveIndex(7)
        const draftResult = await generatePIODraft({
          routing,
          confirmed_info: extraction,
          exemption_flags: evaluation.exemption_flags,
          layer_b_res: evaluation.layer_b_res,
          balance_res: evaluation.balance_res,
          final_recom: evaluation.final_recom,
          department: routing.primary_department,
          is_chips: routing.primary_department === 'chips',
        })

        if (startedRef.current !== runId) return
        setActiveIndex(THINKING_STEPS.length - 1)
        onComplete({
          routing,
          extraction,
          evaluation,
          draft: draftResult.draft,
          warning: draftResult.warning || null,
        })
      } catch (err: any) {
        if (startedRef.current !== runId) return
        setError(err.message || 'The full RTI pipeline failed before a reply could be generated.')
      }
    }

    runFullPipeline()
  }, [retryKey, text, language, onComplete])

  const retry = () => {
    setRetryKey(prev => prev + 1)
  }

  return (
    <div className="w-full max-w-4xl mx-auto py-8 animate-fadeIn">
      <div className="card card-navy p-6 space-y-5">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--s3)] pb-4">
          <div>
            <p className="text-section-hd">Processing RTI Application</p>
            <h2 className="text-[22px] font-bold text-[var(--t1)] mt-1">
              Generating final RTI reply
            </h2>
            <p className="text-caption mt-1">
              The system is running OCR context, routing, extraction, statutory review,
              balancing, and drafting without officer interruption.
            </p>
          </div>
          <div className="flex items-center gap-2 text-[16px] font-semibold text-[var(--navy)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Working
          </div>
        </div>

        {ocr && (
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded border border-[var(--s3)] bg-[var(--s0)] p-3">
              <div className="text-[13px] font-bold uppercase text-[var(--t3)]">Language</div>
              <div className="text-[16px] font-semibold text-[var(--t1)]">{language.toUpperCase()}</div>
            </div>
            <div className="rounded border border-[var(--s3)] bg-[var(--s0)] p-3">
              <div className="text-[13px] font-bold uppercase text-[var(--t3)]">OCR Confidence</div>
              <div className="text-[16px] font-semibold text-[var(--t1)]">
                {Math.round(ocr.confidence * 100)}%
              </div>
            </div>
            <div className="rounded border border-[var(--s3)] bg-[var(--s0)] p-3">
              <div className="text-[13px] font-bold uppercase text-[var(--t3)]">Mode</div>
              <div className="text-[16px] font-semibold text-[var(--t1)]">Full Pipeline</div>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {THINKING_STEPS.map((step, index) => {
            const done = index < activeIndex
            const active = index === activeIndex
            return (
              <div
                key={step}
                className={`flex items-center gap-3 rounded border px-3 py-2 text-[16px] ${
                  active
                    ? 'border-[var(--navy)] bg-[var(--navy-light)] text-[var(--navy)]'
                    : done
                      ? 'border-[var(--green-border)] bg-[var(--green-bg)] text-[var(--green)]'
                      : 'border-[var(--s3)] bg-[var(--s1)] text-[var(--t3)]'
                }`}
              >
                <span className={`dot ${done ? 'dot-green' : active ? 'dot-amber' : 'dot-grey'}`} />
                <span className="font-medium">{step}</span>
              </div>
            )
          })}
        </div>

        {error && (
          <div className="space-y-3">
            <ErrorBanner message={error} />
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn btn-ghost" onClick={onStartOver}>
                Start over
              </button>
              <button type="button" className="btn btn-primary" onClick={retry}>
                <RotateCcw className="h-4 w-4" />
                Retry full pipeline
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
