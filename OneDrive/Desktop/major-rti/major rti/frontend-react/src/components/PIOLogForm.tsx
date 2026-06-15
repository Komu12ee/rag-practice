import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Lock, ShieldCheck, Loader2, Sparkles, Trash2, ArrowLeft } from 'lucide-react'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import { Select } from './ui/select'
import { PIOLogSchema } from '../lib/api'
import { z } from 'zod'

type PIOLogFormValues = z.infer<typeof PIOLogSchema>

interface PIOLogFormProps {
  onSubmit: (values: PIOLogFormValues) => void
  departments: Record<string, string>
  isLoading: boolean
  onEdit?: () => void
  onGenerateDraft: () => Promise<{ draft: string; warning?: string }>
}

export default function PIOLogForm({ onSubmit, departments, isLoading, onEdit, onGenerateDraft }: PIOLogFormProps) {
  const [autofieldUsed, setAutofieldUsed] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationWarning, setGenerationWarning] = useState('')

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<PIOLogFormValues>({
    resolver: zodResolver(PIOLogSchema),
    defaultValues: {
      pio_action_taken: 'APPROVED',
      override_department: '',
      reasoning_notes: '',
    },
  })

  const pioActionTaken = watch('pio_action_taken')
  const reasoningNotes = watch('reasoning_notes')
  const disclaimerCheckbox = watch('disclaimer_checkbox')

  const handleGenerate = async () => {
    setIsGenerating(true)
    setGenerationWarning('')
    try {
      const res = await onGenerateDraft()
      setValue('reasoning_notes', res.draft, { shouldValidate: true })
      setAutofieldUsed(true)
      if (res.warning) {
        setGenerationWarning(res.warning)
      }
    } catch (err: any) {
      alert(err.message || 'Failed to generate AI draft.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleClear = () => {
    setValue('reasoning_notes', '')
    setAutofieldUsed(false)
    setGenerationWarning('')
  }

  const isDisabled =
    !disclaimerCheckbox || !pioActionTaken || (reasoningNotes?.trim().length ?? 0) < 5 || isLoading

  return (
    <div className="surface overflow-hidden">
      <div className="flex items-center gap-2.5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 px-6 py-4">
        <span className="grid place-items-center h-8 w-8 rounded-lg bg-brand-gradient">
          <ShieldCheck className="h-4 w-4 text-white" />
        </span>
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">PIO Decision Entry</h3>
          <p className="text-[11px] text-slate-400">Logged to the immutable SHA-256 hash chain</p>
        </div>
      </div>

      <div className="p-6 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="eyebrow">Final Decision</label>
            <Select {...register('pio_action_taken')}>
              <option value="APPROVED">Approve — Full Disclosure</option>
              <option value="PARTIALLY_APPROVE">Partially Approve — Partial Disclosure</option>
              <option value="REJECTED">Reject — Exempt</option>
              <option value="TRANSFER">Transfer — Section 6(3)</option>
              <option value="PENDING">Pending — Further Review Required</option>
              <option value="OVERRIDDEN">Override — Custom Department</option>
            </Select>
          </div>

          {(pioActionTaken === 'OVERRIDDEN' || pioActionTaken === 'TRANSFER') && (
            <div className="space-y-1.5 animate-fadeIn">
              <label className="eyebrow">Target Department</label>
              <Select {...register('override_department')}>
                <option value="">Select target department…</option>
                {Object.entries(departments).map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </Select>
              {errors.override_department && (
                <p className="text-xs text-red-500">{errors.override_department.message}</p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex justify-between items-center">
            <label className="eyebrow">Decision Notes / Order Sheet Text</label>
            {!autofieldUsed ? (
              <button
                type="button"
                onClick={handleGenerate}
                disabled={isGenerating}
                className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-600 dark:text-amber-500 hover:underline uppercase"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3 w-3" /> Generate Draft
                  </>
                )}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleClear}
                className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-500 dark:text-slate-400 hover:underline uppercase"
              >
                <Trash2 className="h-3 w-3" /> Clear Draft
              </button>
            )}
          </div>
          <Textarea
            {...register('reasoning_notes')}
            placeholder="Required. Provide the legal justification or order sheet note here, or click 'Generate Draft' for an AI-generated layout based on the case evaluation..."
            className="min-h-[150px]"
          />
          {errors.reasoning_notes && (
            <p className="text-xs text-red-500">{errors.reasoning_notes.message}</p>
          )}

          {autofieldUsed && (
            <div className="flex flex-col gap-1.5 mt-1.5">
              <div className="inline-flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400 font-semibold bg-amber-50/50 dark:bg-amber-950/10 border border-amber-200/50 dark:border-amber-900/30 rounded px-3 py-1.5">
                <span>⚠ AI-Generated Draft — review and edit before finalising.</span>
              </div>
              {generationWarning && (
                <span className="text-[10px] text-slate-400 italic pl-1">
                  Note: {generationWarning}
                </span>
              )}
            </div>
          )}
        </div>

        <label
          htmlFor="disclaimer_checkbox"
          className="flex gap-3 items-start rounded border border-slate-200 bg-slate-50/60 p-4 cursor-pointer transition-colors hover:bg-slate-50 dark:border-slate-700/70 dark:bg-slate-800/40 dark:hover:bg-slate-800/60"
        >
          <input
            type="checkbox"
            id="disclaimer_checkbox"
            {...register('disclaimer_checkbox')}
            className="h-[18px] w-[18px] mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500 dark:border-slate-600 dark:bg-slate-700"
          />
          <span className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-800 dark:text-slate-100">
              I confirm I have reviewed this recommendation and accept full legal responsibility for this decision under RTI Act 2005.
            </strong>{' '}
            I understand the AI output is advisory only and does not constitute a legal decision.
          </span>
        </label>
        {errors.disclaimer_checkbox && (
          <p className="text-xs text-red-500 -mt-3">{errors.disclaimer_checkbox.message}</p>
        )}

        <div className="flex flex-col sm:flex-row justify-between gap-3 pt-1">
          {onEdit ? (
            <Button
              type="button"
              variant="outline"
              onClick={onEdit}
              disabled={isLoading}
              className="w-full sm:w-auto gap-1.5 order-2 sm:order-1"
            >
              <ArrowLeft className="h-4 w-4" /> Edit Parameters
            </Button>
          ) : (
            <div className="hidden sm:block order-2 sm:order-1" />
          )}
          <Button
            type="button"
            onClick={handleSubmit(onSubmit)}
            disabled={isDisabled}
            className="w-full sm:w-auto gap-2 order-1 sm:order-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Logging decision…
              </>
            ) : (
              <>
                <Lock className="h-4 w-4" /> Log final decision
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
