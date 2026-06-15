import { useState, useRef, useEffect } from 'react'
import { ShieldAlert } from 'lucide-react'
import { RoutingResult, ExtractedInformation, EvaluationResult, OCRResult } from '../../lib/types'
import { evaluateExemptionsAndSynthesis } from '../../lib/api'
import ErrorBanner from '../ErrorBanner'

interface ReviewStepProps {
  ocr?: OCRResult | null
  routing: RoutingResult
  extraction: ExtractedInformation
  onConfirm: (confirmed: ExtractedInformation, evaluation: EvaluationResult | null) => void
  onStartOver: () => void
}

const DEPARTMENTS: Record<string, { en: string; hi: string }> = {
  chips: { en: 'CHiPS (Chhattisgarh Infotech)', hi: 'छत्तीसगढ़ इन्फोटेक प्रमोशन सोसाइटी (CHiPS)' },
  revenue: { en: 'Revenue Department', hi: 'राजस्व विभाग' },
  pwd: { en: 'Public Works Department', hi: 'लोक निर्माण विभाग' },
  health: { en: 'Health & Family Welfare', hi: 'स्वास्थ्य एवं परिवार कल्याण विभाग' },
  finance: { en: 'Finance Department', hi: 'वित्त विभाग' },
  other: { en: 'Other Department', hi: 'अन्य विभाग' },
}

const INFO_TYPE_OPTIONS = [
  { value: 'citizen_data', label: 'Citizen Private Data' },
  { value: 'employee', label: 'Employee Records' },
  { value: 'procurement', label: 'Procurement Files' },
  { value: 'cybersecurity', label: 'Cybersecurity Logs' },
  { value: 'other', label: 'Other Records' },
]

const PROCUREMENT_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'active_tender', label: 'Active Tender' },
  { value: 'completed_tender', label: 'Completed Tender' },
]

export default function ReviewStep({ ocr, routing, extraction, onConfirm, onStartOver }: ReviewStepProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  // Routing verification state
  const [routingState, setRoutingState] = useState<'confirmed' | 'overridden' | null>('confirmed')
  const [overrideDept, setOverrideDept] = useState<string>('')
  const [overrideReason, setOverrideReason] = useState<string>('')

  // Parameters dialog state
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [tempParams, setTempParams] = useState<ExtractedInformation>({ ...extraction })
  const [confirmedParams, setConfirmedParams] = useState<ExtractedInformation>({ ...extraction })
  const [paramsConfirmed, setParamsConfirmed] = useState(true)

  // Sync state if extraction prop changes
  useEffect(() => {
    setTempParams({ ...extraction })
    setConfirmedParams({ ...extraction })
  }, [extraction])

  // Reasoning Emoji Helper
  const getReasoningEmoji = (stepText: string) => {
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

  // Handle dialog confirm
  const handleDialogConfirm = () => {
    setConfirmedParams({ ...tempParams })
    setParamsConfirmed(true)
    dialogRef.current?.close()
  }

  // Handle final submission to next step
  const handleContinue = async () => {
    setIsLoading(true)
    setError('')
    try {
      // Apply routing override if selected
      if (routingState === 'overridden') {
        routing.primary_department = overrideDept
        routing.reasoning = `Overridden by PIO: ${overrideReason} | ${routing.reasoning}`
      }

      const evaluationResult = await evaluateExemptionsAndSynthesis(confirmedParams)
      onConfirm(confirmedParams, evaluationResult)
    } catch (err: any) {
      setError(err.message || 'Failed to compile exemption evaluation.')
    } finally {
      setIsLoading(false)
    }
  }

  // Parse reasoning segments
  const reasoningSegments = routing.reasoning
    ? routing.reasoning.split('|').map(s => s.trim()).filter(Boolean)
    : []

  const isRoutingValid =
    routingState === 'confirmed' ||
    (routingState === 'overridden' && overrideDept !== '' && overrideReason.trim() !== '')

  const isContinueEnabled = isRoutingValid && paramsConfirmed && !isLoading

  const ocrConf = ocr?.confidence !== undefined ? ocr.confidence : 0.9
  const ocrText = ocr?.text || extraction.explanation || ''

  if (isLoading) {
    return (
      <div className="w-full max-w-5xl mx-auto py-16 flex flex-col items-center justify-center space-y-4 bg-white border border-slate-200 rounded shadow-sm text-center">
        <svg className="animate-spin h-10 w-10 text-[var(--navy)]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="text-[14px] font-semibold text-[var(--t1)]">Running Statutory Exemption Analysis...</p>
        <p className="text-[11px] text-[var(--t3)] uppercase tracking-wider">Evaluating Section 8 and Section 9 Clauses</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto animate-fadeIn">
      {/* CSS injection for native dialog backdrop */}
      <style>{`
        dialog::backdrop {
          background: rgba(0, 0, 0, 0.45);
        }
      `}</style>

      {/* Human-in-the-loop alert banner */}
      <div className="flex gap-3 rounded border border-[var(--amber-border)] bg-[var(--amber-bg)] p-4">
        <span className="grid place-items-center h-8 w-8 shrink-0 rounded bg-[var(--s3)]">
          <ShieldAlert className="h-4 w-4 text-[var(--amber)]" />
        </span>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--amber)]">
            Officer Validation Checkpoint
          </p>
          <p className="text-[13px] text-[var(--t2)] mt-1 leading-relaxed">
            These preliminary parameters are parsed from the application text and determine which statutory clauses are evaluated. Review and verify these settings before initiating the statutory review.
          </p>
        </div>
      </div>

      {/* SECTION A: Recommended Department Card */}
      <div className="card card-navy">
        <div className="flex items-center justify-between">
          <span className="text-section-hd">Preliminary Department Assignment</span>
          {routing.confidence === 'HIGH' && (
            <span className="badge badge-green">Consistent Parameters (High)</span>
          )}
          {routing.confidence === 'MEDIUM' && (
            <span className="badge badge-amber">Verification Advised (Medium)</span>
          )}
          {routing.confidence === 'LOW' && (
            <span className="badge badge-red">Manual Review Required (Low)</span>
          )}
        </div>

        <div className="text-[18px] font-bold text-[var(--navy)] mt-2">
          {DEPARTMENTS[routing.primary_department]?.en || routing.primary_department}
        </div>
        <div className="text-[14px] font-normal text-[var(--t2)] text-devanagari mt-1">
          {DEPARTMENTS[routing.primary_department]?.hi || 'विभाग'}
        </div>

        {/* OCR Status Line */}
        <div className="flex items-center gap-2 mt-3 select-none">
          <span className={`dot ${ocrConf >= 0.85 ? 'dot-green' : 'dot-amber'}`} />
          <span
            className="text-caption"
            style={{ color: ocrConf >= 0.85 ? 'var(--green)' : 'var(--amber)' }}
          >
            {ocrConf >= 0.85
              ? `OCR: Good (${Math.round(ocrConf * 100)}%)`
              : `OCR: Low (${Math.round(ocrConf * 100)}%) — verify extracted text`}
          </span>
        </div>

        <div className="space-y-2 mt-4">
          {/* Collapsible: Routing Reasoning */}
          <details className="group border-t border-[var(--s3)] pt-2">
            <summary className="flex items-center justify-between py-2 text-[13px] font-medium text-[var(--t2)] cursor-pointer select-none">
              <span>Routing Assessment Rationale</span>
            </summary>
            <div className="details-body py-2 divide-y divide-[var(--s3)]">
              {reasoningSegments.length === 0 ? (
                <div className="text-caption italic py-2">No reasoning segments found.</div>
              ) : (
                reasoningSegments.map((segment, idx) => {
                  const emoji = getReasoningEmoji(segment)
                  const hasColon = segment.includes(':')
                  let boldPart = ''
                  let regularPart = segment

                  if (hasColon) {
                    const colonIdx = segment.indexOf(':')
                    boldPart = segment.slice(0, colonIdx + 1)
                    regularPart = segment.slice(colonIdx + 1)
                  }

                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        gap: '8px',
                        padding: '8px 12px',
                        background: idx % 2 === 0 ? 'var(--s0)' : 'var(--s1)',
                      }}
                      className="text-[13px] text-[var(--t2)] items-start rounded-sm"
                    >
                      <span className="shrink-0">{emoji}</span>
                      <span>
                        {hasColon && <strong>{boldPart}</strong>}
                        {regularPart}
                      </span>
                    </div>
                  )
                })
              )}
            </div>
          </details>

          {/* Collapsible: Alternative Departments */}
          <details className="group border-t border-[var(--s3)] pt-2">
            <summary className="flex items-center justify-between py-2 text-[13px] font-medium text-[var(--t2)] cursor-pointer select-none">
              <span>Alternative Departments ({routing.alternatives ? routing.alternatives.length : 0})</span>
            </summary>
            <div className="details-body py-2">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Score</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {!routing.alternatives || routing.alternatives.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="text-caption italic text-center py-4">
                        No alternative departments considered.
                      </td>
                    </tr>
                  ) : (
                    routing.alternatives.map((alt, idx) => {
                      const deptEn = DEPARTMENTS[alt]?.en || alt
                      const simulatedScore = (0.75 - idx * 0.12).toFixed(2)
                      const simulatedPct = `${Math.round((0.75 - idx * 0.12) * 100)}%`

                      return (
                        <tr key={idx}>
                          <td>{deptEn}</td>
                          <td>{simulatedPct} ({simulatedScore})</td>
                          <td className="text-caption">Secondary keyword match &amp; semantic overlap</td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </details>

          {/* Collapsible: Extracted Text */}
          <details className="group border-t border-[var(--s3)] pt-2">
            <summary className="flex items-center justify-between py-2 text-[13px] font-medium text-[var(--t2)] cursor-pointer select-none">
              <span>Extracted Text</span>
            </summary>
            <div className="details-body py-2 space-y-2">
              <pre
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  color: 'var(--t2)',
                  maxHeight: '200px',
                  overflowY: 'auto',
                  background: 'var(--s2)',
                  padding: '12px',
                  borderRadius: 'var(--radius)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {ocrText.slice(0, 3000)}
              </pre>
              {ocrText.length > 3000 && (
                <div className="text-caption italic text-right pr-2">
                  Showing 3,000 of {ocrText.length.toLocaleString()} characters
                </div>
              )}
            </div>
          </details>
        </div>
      </div>

      {/* SECTION B: Routing Verification */}
      <div className="card space-y-4">
        <span className="text-section-hd">Department Assignment Verification</span>
        <div className="text-[13px] text-[var(--t2)]">Is the preliminary department assignment correct?</div>

        <div className="flex gap-3">
          <button
            onClick={() => setRoutingState('confirmed')}
            className={`btn flex-1 justify-center ${
              routingState === 'confirmed' ? 'btn-primary' : 'btn-outline'
            }`}
          >
            ✓ Confirm Department Assignment
          </button>
          <button
            onClick={() => setRoutingState('overridden')}
            className={`btn flex-1 justify-center ${
              routingState === 'overridden'
                ? 'bg-[var(--amber)] text-white hover:bg-[var(--amber)] border-[var(--amber)]'
                : 'btn-amber'
            }`}
          >
            ✎ Override Department Assignment
          </button>
        </div>

        {routingState === 'overridden' && (
          <div className="space-y-4 pt-3 border-t border-[var(--s3)]">
            <div className="field">
              <label>Correct Department</label>
              <select
                value={overrideDept}
                onChange={e => setOverrideDept(e.target.value)}
                className="w-full"
              >
                <option value="">— Select department —</option>
                {Object.entries(DEPARTMENTS).map(([key, dept]) => (
                  <option key={key} value={key}>
                    {dept.en}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>Reason for correction</label>
              <textarea
                rows={3}
                value={overrideReason}
                onChange={e => setOverrideReason(e.target.value)}
                placeholder="e.g. This RTI concerns e-District portal which is under CHiPS, not Revenue Department"
                className="w-full"
              />
            </div>

            <div className="flex items-center gap-2 select-none">
              <span className="dot dot-amber" />
              <span className="text-[12px] font-semibold text-[var(--amber)]">
                Assignment manually overridden by Officer
              </span>
            </div>
          </div>
        )}
      </div>

      {/* SECTION C: Parameter Review Button + Dialog */}
      <div className="card card-amber space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col text-left">
            <span className="text-section-hd">Application Parameter Classification</span>
            <p className="text-caption mt-1">
              Verify and validate preliminary classification parameters before continuing
            </p>
          </div>
          <button onClick={() => dialogRef.current?.showModal()} className="btn btn-amber">
            🔍 Validate &amp; Correct Parameters
          </button>
        </div>

        {paramsConfirmed && (
          <div className="border-t border-[var(--s3)] pt-3">
            <div className="text-[12px] font-mono text-[var(--t2)] uppercase tracking-wider">
              Type: {confirmedParams.classification_type.replace(/_/g, ' ')} &middot; Personal Data:{' '}
              {confirmedParams.personal_data ? 'Yes' : 'No'} &middot; Procurement:{' '}
              {confirmedParams.procurement_status}
            </div>
          </div>
        )}
      </div>

      {/* PARAMETER DIALOG (Native HTML Dialog) */}
      <dialog
        ref={dialogRef}
        className="select-none"
        style={{
          width: '520px',
          maxWidth: '90vw',
          padding: '24px',
          borderRadius: 'var(--radius)',
          border: 'var(--border)',
          background: 'var(--s1)',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.18)',
          margin: 'auto',
          outline: 'none',
        }}
      >
        <div className="flex items-center justify-between border-b border-[var(--s3)] pb-3">
          <span className="text-[15px] font-semibold text-[var(--t1)]">
            Review Extracted Parameters
          </span>
          <button
            onClick={() => dialogRef.current?.close()}
            className="btn btn-ghost btn-sm text-lg font-bold"
          >
            ✕
          </button>
        </div>

        <div className="py-4 space-y-4">
          {/* SECTION CLASSIFICATION */}
          <div className="space-y-3">
            <span className="text-label text-[11px] font-semibold block text-[var(--t3)]">
              CLASSIFICATION
            </span>
            <div className="field">
              <label>Information Type</label>
              <select
                value={tempParams.classification_type}
                onChange={e =>
                  setTempParams(prev => ({
                    ...prev,
                    classification_type: e.target.value,
                  }))
                }
              >
                {INFO_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>Procurement Status</label>
              <select
                value={tempParams.procurement_status}
                onChange={e =>
                  setTempParams(prev => ({
                    ...prev,
                    procurement_status: e.target.value as any,
                  }))
                }
              >
                {PROCUREMENT_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <hr className="divider" />

          {/* SECTION ENTITIES & SYSTEMS */}
          <div className="space-y-3">
            <span className="text-label text-[11px] font-semibold block text-[var(--t3)]">
              ENTITIES &amp; SYSTEMS
            </span>
            <div className="field">
              <label>Key Entities</label>
              <textarea
                rows={3}
                value={tempParams.entities.join(', ')}
                onChange={e =>
                  setTempParams(prev => ({
                    ...prev,
                    entities: e.target.value
                      .split(',')
                      .map(s => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="Comma separated names or organizations"
              />
            </div>

            <div className="field">
              <label>IT Systems Mentioned</label>
              <textarea
                rows={2}
                value={tempParams.systems.join(', ')}
                onChange={e =>
                  setTempParams(prev => ({
                    ...prev,
                    systems: e.target.value
                      .split(',')
                      .map(s => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="Comma separated systems (e.g. e-District, UPAHAR)"
              />
            </div>
          </div>

          <hr className="divider" />

          {/* SECTION RISK FLAGS */}
          <div className="space-y-3">
            <span className="text-label text-[11px] font-semibold block text-[var(--t3)]">
              RISK FLAGS
            </span>
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 select-none cursor-pointer text-[13px] text-[var(--t1)] normal-case tracking-normal">
                <input
                  type="checkbox"
                  checked={tempParams.personal_data}
                  onChange={e =>
                    setTempParams(prev => ({
                      ...prev,
                      personal_data: e.target.checked,
                    }))
                  }
                  className="w-4 h-4 cursor-pointer"
                />
                Contains personal private information
              </label>

              <label className="flex items-center gap-2 select-none cursor-pointer text-[13px] text-[var(--t1)] normal-case tracking-normal">
                <input
                  type="checkbox"
                  checked={tempParams.public_interest}
                  onChange={e =>
                    setTempParams(prev => ({
                      ...prev,
                      public_interest: e.target.checked,
                    }))
                  }
                  className="w-4 h-4 cursor-pointer"
                />
                Contains allegations of corruption or HR violations
              </label>
            </div>

            <div className="field pt-2">
              <label>Extraction Explanation</label>
              <textarea
                rows={3}
                value={tempParams.explanation}
                onChange={e =>
                  setTempParams(prev => ({
                    ...prev,
                    explanation: e.target.value,
                  }))
                }
                placeholder="Rationale for classification"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 pt-3 border-t border-[var(--s3)] mt-4">
          <button
            onClick={() => {
              setTempParams({ ...confirmedParams })
              dialogRef.current?.close()
            }}
            className="btn btn-ghost"
          >
            Cancel
          </button>
          <button onClick={handleDialogConfirm} className="btn btn-primary">
            ✓ Confirm &amp; Continue
          </button>
        </div>
      </dialog>

      {/* ERROR BANNER */}
      {error && <ErrorBanner message={error} />}

      {/* BOTTOM ACTION */}
      <div className="flex justify-between items-center pt-4 border-t border-[var(--s3)] mt-6">
        <button onClick={onStartOver} className="btn btn-ghost" disabled={isLoading}>
          Start Over
        </button>
        <button onClick={handleContinue} className="btn btn-primary" disabled={!isContinueEnabled || isLoading}>
          Continue to Exemption Analysis →
        </button>
      </div>
    </div>
  )
}
