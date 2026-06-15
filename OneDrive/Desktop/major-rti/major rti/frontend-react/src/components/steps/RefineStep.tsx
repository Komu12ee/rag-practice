import { useState } from 'react'
import { ArrowLeft, Loader2, RefreshCcw } from 'lucide-react'
import ErrorBanner from '../ErrorBanner'
import { generatePIODraft } from '../../lib/api'
import {
  EvaluationResult,
  ExtractedInformation,
  RoutingResult,
} from '../../lib/types'

interface RefineStepProps {
  routing: RoutingResult
  extraction: ExtractedInformation
  evaluation: EvaluationResult
  onCancel: () => void
  onRegenerated: (payload: {
    routing: RoutingResult
    extraction: ExtractedInformation
    draft: string
    warning?: string | null
  }) => void
}

const departments = [
  { value: 'chips', label: 'CHiPS' },
  { value: 'revenue', label: 'Revenue Department' },
  { value: 'pwd', label: 'Public Works Department' },
  { value: 'health', label: 'Health & Family Welfare' },
  { value: 'finance', label: 'Finance Department' },
  { value: 'other', label: 'Other Department' },
]

const infoTypes = [
  { value: 'citizen_data', label: 'Citizen private data' },
  { value: 'employee', label: 'Employee records' },
  { value: 'procurement', label: 'Procurement files' },
  { value: 'cybersecurity', label: 'Cybersecurity logs' },
  { value: 'other', label: 'Other records' },
]

export default function RefineStep({
  routing,
  extraction,
  evaluation,
  onCancel,
  onRegenerated,
}: RefineStepProps) {
  const [editedRouting, setEditedRouting] = useState<RoutingResult>({ ...routing })
  const [editedExtraction, setEditedExtraction] = useState<ExtractedInformation>({
    ...extraction,
    entities: [...extraction.entities],
    systems: [...extraction.systems],
  })
  const [editReason, setEditReason] = useState('')
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState('')

  const updateExtraction = <K extends keyof ExtractedInformation>(
    key: K,
    value: ExtractedInformation[K]
  ) => {
    setEditedExtraction(prev => ({ ...prev, [key]: value }))
  }

  const regenerate = async () => {
    if (!editReason.trim()) {
      setError('Please record a short reason for the parameter change before regenerating.')
      return
    }

    setIsRegenerating(true)
    setError('')
    try {
      const routingWithReason: RoutingResult = {
        ...editedRouting,
        reasoning: `PIO refinement: ${editReason.trim()} | ${routing.reasoning}`,
      }
      const draftResult = await generatePIODraft({
        routing: routingWithReason,
        confirmed_info: editedExtraction,
        exemption_flags: evaluation.exemption_flags,
        layer_b_res: evaluation.layer_b_res,
        balance_res: evaluation.balance_res,
        final_recom: evaluation.final_recom,
        department: routingWithReason.primary_department,
        is_chips: routingWithReason.primary_department === 'chips',
      })

      onRegenerated({
        routing: routingWithReason,
        extraction: {
          ...editedExtraction,
          explanation: `${editedExtraction.explanation}\nPIO refinement reason: ${editReason.trim()}`,
        },
        draft: draftResult.draft,
        warning: draftResult.warning || null,
      })
    } catch (err: any) {
      setError(err.message || 'Draft-only regeneration failed. The previous draft is still preserved.')
    } finally {
      setIsRegenerating(false)
    }
  }

  return (
    <div className="w-full max-w-5xl mx-auto animate-fadeIn space-y-5">
      <div className="card card-amber space-y-2">
        <p className="text-section-hd">Edit & Refine</p>
        <h2 className="text-[20px] font-bold text-[var(--t1)]">Adjust AI-extracted parameters</h2>
        <p className="text-caption">
          These changes happen after the first generated reply. Regeneration below re-runs drafting only and keeps
          OCR, extraction trace, legal analysis, and statutory balancing intact for auditability.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card space-y-4">
          <p className="text-section-hd">Routing</p>
          <div className="field">
            <label>Primary department</label>
            <select
              value={editedRouting.primary_department}
              onChange={event =>
                setEditedRouting(prev => ({ ...prev, primary_department: event.target.value }))
              }
            >
              {departments.map(dept => (
                <option key={dept.value} value={dept.value}>
                  {dept.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Routing confidence</label>
            <select
              value={editedRouting.confidence}
              onChange={event =>
                setEditedRouting(prev => ({
                  ...prev,
                  confidence: event.target.value as RoutingResult['confidence'],
                }))
              }
            >
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <div className="rounded border border-[var(--s3)] bg-[var(--s0)] p-3 text-[16px] text-[var(--t2)]">
            Original: <span className="font-semibold uppercase">{routing.primary_department}</span>
          </div>
        </div>

        <div className="card space-y-4">
          <p className="text-section-hd">Classification</p>
          <div className="field">
            <label>Information type</label>
            <select
              value={editedExtraction.classification_type}
              onChange={event => updateExtraction('classification_type', event.target.value)}
            >
              {infoTypes.map(type => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Procurement status</label>
            <select
              value={editedExtraction.procurement_status}
              onChange={event =>
                updateExtraction(
                  'procurement_status',
                  event.target.value as ExtractedInformation['procurement_status']
                )
              }
            >
              <option value="none">None</option>
              <option value="active_tender">Active tender</option>
              <option value="completed_tender">Completed tender</option>
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex items-center gap-2 normal-case tracking-normal text-[16px] text-[var(--t1)]">
              <input
                type="checkbox"
                checked={editedExtraction.personal_data}
                onChange={event => updateExtraction('personal_data', event.target.checked)}
              />
              Contains personal data
            </label>
            <label className="flex items-center gap-2 normal-case tracking-normal text-[16px] text-[var(--t1)]">
              <input
                type="checkbox"
                checked={editedExtraction.public_interest}
                onChange={event => updateExtraction('public_interest', event.target.checked)}
              />
              Public interest alleged
            </label>
          </div>
        </div>
      </div>

      <div className="card space-y-4">
        <p className="text-section-hd">Entities and Systems</p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="field">
            <label>Entities</label>
            <textarea
              rows={3}
              value={editedExtraction.entities.join(', ')}
              onChange={event =>
                updateExtraction(
                  'entities',
                  event.target.value.split(',').map(item => item.trim()).filter(Boolean)
                )
              }
            />
          </div>
          <div className="field">
            <label>Systems</label>
            <textarea
              rows={3}
              value={editedExtraction.systems.join(', ')}
              onChange={event =>
                updateExtraction(
                  'systems',
                  event.target.value.split(',').map(item => item.trim()).filter(Boolean)
                )
              }
            />
          </div>
        </div>
        <div className="field">
          <label>Extraction explanation</label>
          <textarea
            rows={3}
            value={editedExtraction.explanation}
            onChange={event => updateExtraction('explanation', event.target.value)}
          />
        </div>
        <div className="field">
          <label>Reason for change</label>
          <textarea
            rows={3}
            value={editReason}
            onChange={event => {
              setEditReason(event.target.value)
              if (event.target.value.trim()) setError('')
            }}
            placeholder="Example: The application concerns procurement records, not employee service records."
          />
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="flex justify-between items-center gap-3 border-t border-[var(--s3)] pt-4">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={isRegenerating}>
          <ArrowLeft className="h-4 w-4" />
          Back to result
        </button>
        <button type="button" className="btn btn-primary" onClick={regenerate} disabled={isRegenerating}>
          {isRegenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
          Regenerate reply draft only
        </button>
      </div>
    </div>
  )
}
