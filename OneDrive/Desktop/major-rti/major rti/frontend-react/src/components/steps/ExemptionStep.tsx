import { useState, useEffect } from 'react'
import SkeletonCards from '../SkeletonCards'
import { evaluateExemptionsAndSynthesis, logFinalDecision, generatePIODraft } from '../../lib/api'
import { RoutingResult, ExtractedInformation, EvaluationResult, AuditRecord } from '../../lib/types'
import ErrorBanner from '../ErrorBanner'

interface ExemptionStepProps {
  caseId: string
  rawText: string
  routing: RoutingResult
  confirmedInfo: ExtractedInformation
  evaluationResult: EvaluationResult | null
  onEvaluationLoaded: (result: EvaluationResult) => void
  onDecisionLogged: (record: AuditRecord) => void
  onEditParameters: () => void
}

export default function ExemptionStep({
  caseId,
  rawText,
  routing,
  confirmedInfo,
  evaluationResult,
  onEvaluationLoaded,
  onDecisionLogged,
  onEditParameters,
}: ExemptionStepProps) {
  const [isLoading, setIsLoading] = useState(!evaluationResult)
  const [isLogging, setIsLogging] = useState(false)
  const [error, setError] = useState('')

  // Decision Form State
  const [decision, setDecision] = useState('')
  const [notes, setNotes] = useState('')
  const [checkboxChecked, setCheckboxChecked] = useState(false)
  const [submitError, setSubmitError] = useState('')

  // Draft State
  const [draftLoading, setDraftLoading] = useState(false)
  const [draftUsed, setDraftUsed] = useState(false)

  useEffect(() => {
    if (!evaluationResult) {
      const fetchEvaluation = async () => {
        setIsLoading(true)
        setError('')
        try {
          const result = await evaluateExemptionsAndSynthesis(confirmedInfo)
          onEvaluationLoaded(result)
        } catch (err: any) {
          setError(err.message || 'Failed to load exemption evaluation results.')
        } finally {
          setIsLoading(false)
        }
      }
      fetchEvaluation()
    }
  }, [confirmedInfo, evaluationResult, onEvaluationLoaded])

  // Call API to generate draft response
  const handleGenerateClick = async () => {
    if (!evaluationResult) return
    setDraftLoading(true)
    setError('')
    try {
      const res = await generatePIODraft({
        routing,
        confirmed_info: confirmedInfo,
        exemption_flags: evaluationResult.exemption_flags,
        layer_b_res: evaluationResult.layer_b_res,
        balance_res: evaluationResult.balance_res,
        final_recom: evaluationResult.final_recom,
        department: routing.primary_department,
        is_chips: routing.primary_department === 'chips',
      })
      setNotes(res.draft)
      setDraftUsed(true)
    } catch (err: any) {
      setError(err.message || 'Failed to generate response draft.')
    } finally {
      setDraftLoading(false)
    }
  }

  // Handle final decision log submission
  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!evaluationResult) return

    if (!checkboxChecked) {
      setSubmitError('You must accept legal responsibility before submitting.')
      return
    }

    setSubmitError('')
    setIsLogging(true)
    setError('')

    // Map decision select options to API types
    let apiDecision: 'APPROVED' | 'PARTIALLY_APPROVE' | 'REJECTED' | 'TRANSFER' | 'PENDING' | 'OVERRIDDEN' = 'APPROVED'
    if (decision === 'Approve') apiDecision = 'APPROVED'
    else if (decision === 'Partially Approve') apiDecision = 'PARTIALLY_APPROVE'
    else if (decision === 'Reject') apiDecision = 'REJECTED'
    else if (decision === 'Transfer (Section 6(3))') apiDecision = 'TRANSFER'
    else if (decision === 'Pending — Further Review') apiDecision = 'PENDING'

    try {
      const recordPayload: Omit<AuditRecord, 'timestamp'> = {
        audit_id: caseId,
        pio_action_taken: apiDecision,
        override_department: apiDecision === 'TRANSFER' ? routing.primary_department : '',
        reasoning_notes: notes,
        extracted_info: confirmedInfo,
        routing,
        evaluation: evaluationResult,
      }
      const signedRecord = await logFinalDecision(recordPayload)
      onDecisionLogged(signedRecord)
    } catch (err: any) {
      setError(err.message || 'Failed to log decision to the audit trail.')
    } finally {
      setIsLogging(false)
    }
  }

  if (isLoading) {
    return (
      <div className="w-full max-w-5xl mx-auto py-8">
        <SkeletonCards />
      </div>
    )
  }

  if (error && !evaluationResult) {
    return (
      <div className="w-full max-w-5xl mx-auto py-6">
        <ErrorBanner message={error} />
        <button onClick={onEditParameters} className="btn btn-outline mt-4">
          ← Back to Parameters
        </button>
      </div>
    )
  }

  if (!evaluationResult) return null

  const { final_recom, exemption_flags = [], balance_res, layer_b_res = [] } = evaluationResult
  const recommAction = final_recom?.action || 'APPROVE'

  // Card border mapping
  let recommendationCardClass = 'border-l-4 border-l-emerald-600 bg-white shadow-sm p-5 space-y-4'
  let recommendationHeading = 'APPROVE — DISCLOSE'
  let recommendationHeadingColor = 'var(--green)'

  if (recommAction === 'REJECT') {
    recommendationCardClass = 'border-l-4 border-l-rose-600 bg-white shadow-sm p-5 space-y-4'
    recommendationHeading = 'REJECT — EXEMPT'
    recommendationHeadingColor = 'var(--red)'
  } else if (recommAction === 'PARTIALLY_APPROVE') {
    recommendationCardClass = 'border-l-4 border-l-amber-600 bg-white shadow-sm p-5 space-y-4'
    recommendationHeading = 'PARTIALLY APPROVE'
    recommendationHeadingColor = 'var(--amber)'
  } else if (recommAction === 'TRANSFER') {
    recommendationCardClass = 'border-l-4 border-l-sky-800 bg-white shadow-sm p-5 space-y-4'
    recommendationHeading = 'TRANSFER — S.6(3)'
    recommendationHeadingColor = 'var(--navy)'
  }

  return (
    <div className="w-full space-y-6 select-none">
      {/* Case Summary Card */}
      <div className={recommendationCardClass}>
        {/* Top Row: Review Status */}
        <div className="flex items-center justify-between pb-2 border-b border-[var(--s3)]">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Suggested Action</span>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] uppercase font-bold text-slate-400">Review Status:</span>
            <span className="badge badge-amber">Officer Verification Required</span>
          </div>
        </div>

        {/* Suggested Action Title & Description */}
        <div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: recommendationHeadingColor }}>
            {recommendationHeading}
          </div>
          {final_recom?.timeline && (
            <p className="text-[12px] text-slate-500 italic mt-0.5">{final_recom.timeline}</p>
          )}
        </div>

        <p className="text-[13px] text-[var(--t1)] leading-relaxed">
          {final_recom?.reasoning || 'No reasoning analysis available.'}
        </p>

        <hr className="divider" style={{ margin: '12px 0' }} />

        {/* Grid for Summary Fields */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="md:col-span-2 space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Information Requested</span>
            <div className="bg-slate-50 border border-slate-200 rounded p-2.5 max-h-[120px] overflow-y-auto font-sans text-slate-700 whitespace-pre-wrap leading-relaxed">
              {rawText}
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Information Type</span>
            <p className="text-[13px] text-slate-800 font-medium capitalize mt-0.5">
              {confirmedInfo.classification_type.replace(/_/g, ' ')}
            </p>
          </div>
          <div className="space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Statutory Exemptions</span>
            <p className="text-[13px] text-slate-800 font-medium mt-0.5">
              {final_recom?.citations && final_recom.citations.length > 0
                ? final_recom.citations.join(', ')
                : 'No exemptions triggered'}
            </p>
          </div>
          <div className="space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Public Interest Override</span>
            <p className="text-[13px] font-medium flex items-center gap-1.5 mt-0.5" style={{ color: confirmedInfo.public_interest ? 'var(--green)' : 'var(--t2)' }}>
              <span className={`dot ${confirmedInfo.public_interest ? 'dot-green' : 'dot-gray'}`} />
              {confirmedInfo.public_interest ? 'Applied (Section 8(2))' : 'Not Triggered'}
            </p>
          </div>
        </div>
      </div>

      {/* Collapsible Details Accordions */}
      <div className="flex flex-col gap-4">
        {/* 1. Applicable Sections */}
        <details className="group border border-slate-200 rounded bg-white shadow-sm" open={false}>
          <summary className="flex items-center justify-between p-3 text-[13px] font-semibold text-[var(--t1)] cursor-pointer select-none hover:bg-slate-50 transition-colors">
            <span>Applicable Sections</span>
            <span className="text-xs text-slate-500 font-normal">{exemption_flags.length} sections reviewed</span>
          </summary>
          <div className="p-4 border-t border-slate-200 space-y-3 bg-slate-50/50">
            {exemption_flags.length === 0 ? (
              <p className="text-xs italic text-slate-500 text-center py-2">No statutory exemptions triggered.</p>
            ) : (
              exemption_flags.map((flag, idx) => {
                const isFlagged = !flag.is_overridden && flag.suggested_action === 'REJECT'
                return (
                  <div key={idx} className="bg-white border border-slate-200 rounded p-3.5 space-y-2 shadow-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-bold text-slate-800">
                        Section {flag.section} — {flag.title}
                      </span>
                      <span className={`badge ${isFlagged ? 'badge-red' : 'badge-green'}`}>
                        {isFlagged ? 'FLAGGED' : 'CLEAR'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">{flag.reasoning}</p>
                    {flag.is_overridden && flag.override_reason && (
                      <div className="mt-1 pt-1.5 border-t border-dashed border-slate-200 text-[11px] text-amber-700">
                        <span className="font-semibold">Override Reason:</span> {flag.override_reason}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </details>

        {/* 2. Legal References */}
        <details className="group border border-slate-200 rounded bg-white shadow-sm" open={false}>
          <summary className="flex items-center justify-between p-3 text-[13px] font-semibold text-[var(--t1)] cursor-pointer select-none hover:bg-slate-50 transition-colors">
            <span>Legal References</span>
            <span className="text-xs text-slate-500 font-normal">{layer_b_res.length} references available</span>
          </summary>
          <div className="p-4 border-t border-slate-200 space-y-4 bg-slate-50/50">
            {layer_b_res.length === 0 ? (
              <p className="text-xs italic text-slate-500 text-center py-2">No reference citations available.</p>
            ) : (
              layer_b_res.map((ref, idx) => (
                <div key={idx} className="bg-white border border-slate-200 rounded p-3.5 space-y-2 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold text-slate-800">
                      Section {ref.section} — {ref.title}
                    </span>
                    <span className="text-xs font-semibold text-slate-500 font-mono">
                      Match: {Math.round(ref.confidence_score * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed">{ref.legal_reasoning}</p>
                  {ref.exact_quotes && ref.exact_quotes.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Statutory Wording / Quotes:</span>
                      {ref.exact_quotes.map((quote, qidx) => (
                        <blockquote key={qidx} className="border-l-2 border-slate-300 pl-3 italic text-xs text-slate-600 bg-slate-50 py-1.5 px-2 rounded">
                          "{quote}"
                        </blockquote>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </details>

        {/* 3. Disclosure Assessment */}
        <details className="group border border-slate-200 rounded bg-white shadow-sm" open={false}>
          <summary className="flex items-center justify-between p-3 text-[13px] font-semibold text-[var(--t1)] cursor-pointer select-none hover:bg-slate-50 transition-colors">
            <span>Disclosure Assessment</span>
            <span className="text-xs text-slate-500 font-normal">Review available</span>
          </summary>
          <div className="p-4 border-t border-slate-200 space-y-4 bg-slate-50/50">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Case for Disclosure */}
              <div className="bg-white border border-slate-200 rounded p-3.5 space-y-2 shadow-sm">
                <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-700">
                  <span className="dot dot-green" />
                  <span>Case for Disclosure</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {balance_res?.pro_disclosure_argument || 'Arguments supporting disclosure.'}
                </p>
              </div>

              {/* Case for Exemption */}
              <div className="bg-white border border-slate-200 rounded p-3.5 space-y-2 shadow-sm">
                <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-amber-700">
                  <span className="dot dot-amber" />
                  <span>Case for Exemption</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {balance_res?.pro_exemption_argument || 'Arguments supporting exemption.'}
                </p>
              </div>
            </div>

            {/* Balancing Factors */}
            <div className="bg-white border border-slate-200 rounded p-3.5 space-y-2 shadow-sm">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Key Balancing Factors</span>
              <p className="text-xs text-slate-600 leading-relaxed">
                {balance_res?.balancing_factors || 'Key factors weighed in balancing interest.'}
              </p>
            </div>
          </div>
        </details>

      </div>

      {/* Officer Decision Card */}
      <div className="card border border-slate-200 bg-white shadow-sm p-5 space-y-4">
        <span className="text-[14px] font-bold text-slate-800 uppercase tracking-wide">Officer Decision</span>
        <hr className="divider" style={{ margin: '8px 0' }} />

        <form onSubmit={handleFormSubmit} className="space-y-4">
          {/* Comments / Notes Textarea */}
          <div className="field">
            <label className="text-xs font-bold text-slate-600 block mb-1">Official Order Sheet / Comments</label>
            <textarea
              rows={6}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Record the legal basis and details for your final decision. This will be appended to the official database."
              className="w-full text-xs p-2 border border-slate-300 rounded font-sans focus:ring-1 focus:ring-slate-400 bg-white"
              required
            />
            <div className="flex items-center justify-between mt-2">
              <button
                type="button"
                onClick={handleGenerateClick}
                className="btn btn-outline btn-sm text-xs bg-white border border-slate-300 hover:bg-slate-50 text-slate-705"
                disabled={draftLoading}
              >
                {draftLoading ? 'Generating Draft...' : '✎ Generate Preliminary Draft Note'}
              </button>
              {draftUsed && (
                <span className="text-[11px] text-emerald-600 font-semibold">
                  ✓ Draft auto-populated
                </span>
              )}
            </div>
          </div>

          {/* Final Decision Selector */}
          <div className="field">
            <label className="text-xs font-bold text-slate-600 block mb-1">Final Decision</label>
            <select
              value={decision}
              onChange={e => setDecision(e.target.value)}
              className="w-full text-xs p-2 border border-slate-300 rounded focus:ring-1 focus:ring-slate-400 bg-white"
              required
            >
              <option value="">— Select decision —</option>
              <option value="Approve">Approve / Disclose Information</option>
              <option value="Partially Approve">Partially Approve</option>
              <option value="Reject">Reject / Exempt from Disclosure</option>
              <option value="Transfer (Section 6(3))">Transfer to Another Dept (Section 6(3))</option>
              <option value="Pending — Further Review">Pending — Further Review</option>
            </select>
          </div>

          {/* Review Confirmation Checkbox */}
          <div className="rounded bg-slate-50 border border-slate-200 p-3 flex items-start gap-2">
            <input
              type="checkbox"
              id="pio_confirm"
              checked={checkboxChecked}
              onChange={e => {
                setCheckboxChecked(e.target.checked)
                if (e.target.checked) setSubmitError('')
              }}
              className="mt-1 h-4 w-4 cursor-pointer accent-slate-800"
            />
            <label
              htmlFor="pio_confirm"
              className="text-[11px] text-slate-600 cursor-pointer select-none leading-relaxed"
            >
              I confirm I have reviewed this recommendation and accept full legal responsibility for this decision under RTI Act 2005, Section 5.
            </label>
          </div>

          {submitError && (
            <div className="text-[11px] text-rose-600 font-semibold leading-normal">
              {submitError}
            </div>
          )}

          {error && <ErrorBanner message={error} />}

          {/* Submit button and edit parameters */}
          <div className="space-y-2 pt-2">
            <button
              type="submit"
              className="w-full btn bg-[#1B3252] hover:bg-[#152741] text-white py-2 px-3 rounded text-xs font-bold transition-colors disabled:opacity-50"
              disabled={isLogging || !decision || !notes.trim()}
            >
              {isLogging ? 'Logging decision...' : 'Submit & Finalise Decision'}
            </button>

            <button
              type="button"
              onClick={onEditParameters}
              className="w-full btn btn-ghost text-xs text-slate-500 hover:text-slate-700 py-1.5 text-center"
              disabled={isLogging}
            >
              ← Edit Extracted Parameters
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
