import { useEffect, useState } from 'react'
import { Copy, FileDown, Loader2, Pencil, Printer, RefreshCcw, Save } from 'lucide-react'
import ErrorBanner from '../ErrorBanner'
import { logFinalDecision } from '../../lib/api'
import {
  AuditRecord,
  EvaluationResult,
  ExtractedInformation,
  RoutingResult,
} from '../../lib/types'

interface ResultStepProps {
  caseId: string
  rawText: string
  routing: RoutingResult
  extraction: ExtractedInformation
  evaluation: EvaluationResult
  draftText: string
  draftWarning: string | null
  draftVersion: number
  onEdit: () => void
  onLogged: (record: AuditRecord) => void
}

const CONSULTANT_NOTICE =
  'This system provides legal research and drafting assistance only. The final decision under the RTI Act, 2005 remains the responsibility of the concerned PIO.'

function neutralizeDecisionLanguage(text: string): string {
  return text
    .replace(
      /It is recommended to\s+(TRANSFER|REJECT|APPROVE|PARTIALLY APPROVE|PARTIALLY_APPROVE)\s+the application([^.\n]*)(\.|\n)/gi,
      'Relevant statutory and factual considerations are set out below for the PIO\'s independent determination.$3'
    )
    .replace(/Recommended\s+action\s*:\s*/gi, 'Assistance note: ')
    .replace(/recommended decision/gi, 'legal research position')
    .replace(/Final recommendation/gi, 'Legal research summary')
}

export default function ResultStep({
  caseId,
  rawText,
  routing,
  extraction,
  evaluation,
  draftText,
  draftWarning,
  draftVersion,
  onEdit,
  onLogged,
}: ResultStepProps) {
  const [replyText, setReplyText] = useState(() => neutralizeDecisionLanguage(draftText))
  const [accepted, setAccepted] = useState(false)
  const [isLogging, setIsLogging] = useState(false)
  const [downloadType, setDownloadType] = useState<'analysis' | 'response' | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const citations = evaluation.final_recom.citations.length
    ? evaluation.final_recom.citations.join(', ')
    : 'No exemption sections triggered'

  const statutoryReferences = evaluation.layer_b_res.length
    ? evaluation.layer_b_res
    : evaluation.exemption_flags.map(flag => ({
        section: flag.section,
        title: flag.title,
        legal_reasoning: flag.reasoning,
        confidence_score: 1,
        exact_quotes: [],
        is_applicable: true,
      }))

  useEffect(() => {
    setReplyText(neutralizeDecisionLanguage(draftText))
  }, [draftText, draftVersion])

  const copyReply = async () => {
    await navigator.clipboard.writeText(replyText)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const buildRecord = (): Omit<AuditRecord, 'timestamp'> => ({
    audit_id: caseId,
    pio_action_taken: 'PENDING',
    override_department: '',
    reasoning_notes: replyText,
    extracted_info: extraction,
    routing,
    evaluation,
  })

  const handleFinalize = async () => {
    if (!accepted) {
      setError('Please accept legal responsibility before finalising this RTI reply.')
      return
    }
    setIsLogging(true)
    setError('')
    try {
      const record = await logFinalDecision(buildRecord())
      onLogged(record)
    } catch (err: any) {
      setError(err.message || 'Failed to log assistance record.')
    } finally {
      setIsLogging(false)
    }
  }

  const downloadReport = async (endpoint: string, fallbackName: string, type: 'analysis' | 'response') => {
    setDownloadType(type)
    setError('')
    try {
      const payload = {
        raw_text: rawText,
        logged_record: {
          ...buildRecord(),
          timestamp: new Date().toISOString(),
        },
      }
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(response.statusText)

      const blob = await response.blob()
      const link = document.createElement('a')
      link.href = window.URL.createObjectURL(blob)
      link.download = fallbackName
      link.click()
      window.URL.revokeObjectURL(link.href)
    } catch (err: any) {
      setError(err.message || 'Failed to download document.')
    } finally {
      setDownloadType(null)
    }
  }

  const caseFileName = caseId.replace(/\//g, '_')

  return (
    <div className="w-full grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-5 animate-fadeIn">
      <section className="card card-navy p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--s3)] flex items-center justify-between gap-3">
          <div>
            <p className="text-section-hd">Assisted Draft Reply</p>
            <h2 className="text-[20px] font-bold text-[var(--t1)]">Draft v{draftVersion}</h2>
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn btn-outline btn-sm" onClick={copyReply}>
              <Copy className="h-4 w-4" />
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button type="button" className="btn btn-amber btn-sm" onClick={onEdit}>
              <Pencil className="h-4 w-4" />
              Edit & Refine
            </button>
          </div>
        </div>

        {draftWarning && (
          <div className="mx-5 mt-4 rounded border border-[var(--amber-border)] bg-[var(--amber-bg)] px-3 py-2 text-[16px] text-[var(--amber)] font-semibold">
            {draftWarning}
          </div>
        )}

        <div className="p-5">
          <div className="mb-4 rounded border border-[var(--amber-border)] bg-[var(--amber-bg)] px-4 py-3 text-[16px] leading-relaxed text-[var(--amber)] font-semibold">
            {CONSULTANT_NOTICE}
          </div>
          <textarea
            value={replyText}
            onChange={event => setReplyText(event.target.value)}
            className="w-full min-h-[520px] resize-y bg-white text-[17px] leading-8 font-serif border border-[var(--s3)] rounded p-5 whitespace-pre-wrap"
            aria-label="Generated RTI reply"
          />
        </div>
      </section>

      <aside className="space-y-4">
        <div className="card space-y-3">
          <p className="text-section-hd">Legal Research &amp; Precedent Support</p>
          <div className="space-y-2 text-[16px]">
            <div className="flex justify-between gap-3">
              <span className="text-[var(--t3)]">Department</span>
              <span className="font-bold text-[var(--t1)] uppercase">{routing.primary_department}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-[var(--t3)]">Research confidence</span>
              <span className="font-bold text-[var(--t1)]">{evaluation.final_recom.confidence}</span>
            </div>
            <div className="pt-2 border-t border-[var(--s3)]">
              <span className="text-[var(--t3)] block mb-1">Relevant RTI Act Sections</span>
              <span className="font-semibold text-[var(--t1)]">{citations}</span>
            </div>
            <div className="pt-2 border-t border-[var(--s3)]">
              <span className="text-[var(--t3)] block mb-1">Key Legal Observations</span>
              <span className="font-semibold text-[var(--t1)]">{evaluation.final_recom.reasoning}</span>
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <p className="text-section-hd">References</p>
          <div className="space-y-3 text-[15px]">
            <div>
              <span className="text-[var(--t3)] block mb-1">RTI Act, 2005</span>
              <div className="space-y-2">
                {statutoryReferences.map((ref, index) => (
                  <div key={`${ref.section}-${index}`} className="rounded border border-[var(--s3)] bg-[var(--s0)] p-2">
                    <div className="font-bold text-[var(--t1)]">Section {ref.section} — {ref.title}</div>
                    <div className="text-[var(--t2)] mt-1">{ref.legal_reasoning}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <span className="text-[var(--t3)] block">Similar CIC/SIC Decisions</span>
              <span className="font-semibold text-[var(--t1)]">Phase 2 research source. Not queried in this run.</span>
            </div>
            <div>
              <span className="text-[var(--t3)] block">Relevant Court Judgments</span>
              <span className="font-semibold text-[var(--t1)]">Phase 2 research source. Not queried in this run.</span>
            </div>
            <div>
              <span className="text-[var(--t3)] block">Comparable Historical Cases</span>
              <span className="font-semibold text-[var(--t1)]">Available when CIC/SIC/court corpus search is enabled.</span>
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <p className="text-section-hd">Extracted Parameters</p>
          <div className="text-[16px] space-y-2">
            <div>
              <span className="text-[var(--t3)] block">Information type</span>
              <span className="font-semibold capitalize">{extraction.classification_type.replace(/_/g, ' ')}</span>
            </div>
            <div>
              <span className="text-[var(--t3)] block">Entities</span>
              <span>{extraction.entities.length ? extraction.entities.join(', ') : 'None detected'}</span>
            </div>
            <div>
              <span className="text-[var(--t3)] block">Systems</span>
              <span>{extraction.systems.length ? extraction.systems.join(', ') : 'None detected'}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <span className={extraction.personal_data ? 'badge badge-red' : 'badge badge-green'}>
                Personal data: {extraction.personal_data ? 'Yes' : 'No'}
              </span>
              <span className={extraction.public_interest ? 'badge badge-amber' : 'badge badge-grey'}>
                Public interest: {extraction.public_interest ? 'Yes' : 'No'}
              </span>
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <p className="text-section-hd">Assistance Record</p>

          <label className="flex items-start gap-2 normal-case tracking-normal text-[15px] text-[var(--t2)] cursor-pointer">
            <input
              type="checkbox"
              checked={accepted}
              onChange={event => {
                setAccepted(event.target.checked)
                if (event.target.checked) setError('')
              }}
              className="mt-1 h-4 w-4"
            />
            I understand this is legal research and drafting assistance only. The final RTI determination remains with the concerned PIO.
          </label>

          {error && <ErrorBanner message={error} />}

          <button type="button" className="btn btn-primary w-full justify-center" onClick={handleFinalize} disabled={isLogging}>
            {isLogging ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Log assistance record
          </button>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn btn-outline btn-sm justify-center"
              disabled={downloadType !== null}
              onClick={() => downloadReport('/api/download_analysis', `RTI_Analysis_${caseFileName}.docx`, 'analysis')}
            >
              {downloadType === 'analysis' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
              Analysis
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm justify-center"
              disabled={downloadType !== null}
              onClick={() => downloadReport('/api/download_response', `RTI_Response_${caseFileName}.docx`, 'response')}
            >
              {downloadType === 'response' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
              Word
            </button>
          </div>

          <div className="flex items-start gap-2 text-[15px] text-[var(--t3)]">
            <RefreshCcw className="h-4 w-4 shrink-0 mt-0.5" />
            Use Edit & Refine to change extracted parameters. Regeneration will re-run drafting only.
          </div>
        </div>
      </aside>
    </div>
  )
}
