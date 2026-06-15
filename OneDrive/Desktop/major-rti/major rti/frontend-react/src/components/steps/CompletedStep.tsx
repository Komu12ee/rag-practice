import { CheckCircle2, RotateCcw, Copy, Check, FileDown, Printer, FileSpreadsheet, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../ui/button'
import { AuditRecord } from '../../lib/types'

interface CompletedStepProps {
  loggedRecord: AuditRecord | null
  rawText: string
  onReset: () => void
}

export default function CompletedStep({ loggedRecord, rawText, onReset }: CompletedStepProps) {
  const [copied, setCopied] = useState(false)
  const [downloadingAnalysis, setDownloadingAnalysis] = useState(false)
  const [downloadingResponse, setDownloadingResponse] = useState(false)
  if (!loggedRecord) return null

  const { audit_id, timestamp, pio_action_taken, current_hash } = loggedRecord
  const formattedTime = timestamp ? new Date(timestamp).toLocaleString() : new Date().toLocaleString()

  const copyHash = () => {
    if (!current_hash) return
    navigator.clipboard.writeText(current_hash)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const routingDept = loggedRecord.routing?.primary_department || 'N/A'
  const infoClassification = loggedRecord.extracted_info?.classification_type || 'N/A'
  const triggeredRules = loggedRecord.evaluation?.exemption_flags
    ?.map(f => f.section)
    ?.join(', ') || 'None'

  const rows: { label: string; value: string; mono?: boolean }[] = [
    { label: 'Audit ID / Case ID', value: audit_id || 'N/A', mono: true },
    { label: 'Timestamp', value: formattedTime },
    { label: 'PIO Decision Action', value: pio_action_taken },
    { label: 'Assigned Department', value: routingDept.toUpperCase() },
    { label: 'Information Classification', value: infoClassification.toUpperCase() },
    { label: 'Triggered Legal Rules', value: triggeredRules },
  ]

  const downloadCSV = () => {
    const headers = ['Metadata Field', 'Value']
    const data = [
      ['Audit ID / Case ID', loggedRecord.audit_id || ''],
      ['Timestamp', formattedTime],
      ['PIO Action Taken', loggedRecord.pio_action_taken],
      ['Assigned Department', routingDept],
      ['Information Type', infoClassification],
      ['Triggered Rules', triggeredRules],
      ['Immutable Block Hash', loggedRecord.current_hash || ''],
      ['PIO Order Sheet Text', loggedRecord.reasoning_notes || ''],
    ]
    const content = [headers, ...data]
      .map(row => row.map(val => `"${val.replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `rti_audit_${(audit_id || 'record').replace(/\//g, '_')}.csv`
    link.click()
  }

  const downloadReport = async (
    endpoint: string,
    defaultFilename: string,
    setLoading: (loading: boolean) => void
  ) => {
    setLoading(true)
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          raw_text: rawText,
          logged_record: loggedRecord,
        }),
      })

      if (!response.ok) {
        throw new Error(`Failed to download: ${response.statusText}`)
      }

      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition')
      let filename = defaultFilename
      if (disposition && disposition.indexOf('attachment') !== -1) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/
        const matches = filenameRegex.exec(disposition)
        if (matches != null && matches[1]) {
          filename = matches[1].replace(/['"]/g, '')
        }
      }

      const link = document.createElement('a')
      link.href = window.URL.createObjectURL(blob)
      link.download = filename
      link.click()
      window.URL.revokeObjectURL(link.href)
    } catch (err: any) {
      console.error(err)
      alert('Error downloading document: ' + (err.message || err))
    } finally {
      setLoading(false)
    }
  }

  const caseIdClean = (audit_id || 'record').replace(/\//g, '_')

  const downloadAnalysisReport = () => {
    downloadReport('/api/download_analysis', `RTI_Analysis_${caseIdClean}.docx`, setDownloadingAnalysis)
  }

  const downloadResponseDoc = () => {
    downloadReport('/api/download_response', `RTI_Response_${caseIdClean}.docx`, setDownloadingResponse)
  }

  return (
    <div className="w-full max-w-lg mx-auto py-10 animate-scaleIn">
      <div className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded p-8 text-center space-y-6">
        <div className="mx-auto w-fit">
          <CheckCircle2 className="h-14 w-14 text-emerald-600 dark:text-emerald-500" strokeWidth={2} />
        </div>

        <div className="space-y-1">
          <h2 className="text-xl font-bold uppercase tracking-wider text-slate-900 dark:text-white">
            Decision Registered
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            The RTI decision has been signed and logged to the immutable SQLite SHA-256 blockchain registry.
          </p>
        </div>

        {/* Audit Details */}
        <div className="rounded border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/10 divide-y divide-slate-200 dark:divide-slate-800 text-left">
          {rows.map(r => (
            <div key={r.label} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{r.label}</span>
              <span className={`text-xs text-slate-700 dark:text-slate-200 text-right break-all ${r.mono ? 'font-mono' : 'font-medium'}`}>
                {r.value}
              </span>
            </div>
          ))}
          <div className="flex items-center justify-between gap-3 px-4 py-2.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Block hash</span>
            <button
              onClick={copyHash}
              className="group flex items-center gap-1.5 text-xs font-mono text-slate-750 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors max-w-[60%]"
              title="Copy full hash"
            >
              <span className="truncate">{current_hash ? `${current_hash.slice(0, 24)}…` : 'N/A'}</span>
              {copied ? (
                <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
              ) : (
                <Copy className="h-3.5 w-3.5 shrink-0 opacity-50 group-hover:opacity-100" />
              )}
            </button>
          </div>
        </div>

        {/* Export & Actions Row */}
        <div className="grid grid-cols-3 gap-2.5 pt-2 border-t border-slate-100 dark:border-slate-800">
          <button
            onClick={downloadCSV}
            className="flex flex-col items-center justify-center gap-1 py-2 border border-slate-200 dark:border-slate-800 rounded bg-slate-50/50 hover:bg-slate-100/50 dark:hover:bg-slate-800/50 text-[10px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 transition-colors"
          >
            <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
            <span>CSV Record</span>
          </button>
          <button
            onClick={downloadAnalysisReport}
            disabled={downloadingAnalysis || downloadingResponse}
            className="flex flex-col items-center justify-center gap-1 py-2 border border-slate-200 dark:border-slate-800 rounded bg-slate-50/50 hover:bg-slate-100/50 dark:hover:bg-slate-800/50 text-[10px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 transition-colors disabled:opacity-50"
          >
            {downloadingAnalysis ? (
              <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
            ) : (
              <FileDown className="h-4 w-4 text-blue-600" />
            )}
            <span>{downloadingAnalysis ? 'Generating...' : 'Analysis Report'}</span>
          </button>
          <button
            onClick={downloadResponseDoc}
            disabled={downloadingAnalysis || downloadingResponse}
            className="flex flex-col items-center justify-center gap-1 py-2 border border-slate-200 dark:border-slate-800 rounded bg-slate-50/50 hover:bg-slate-100/50 dark:hover:bg-slate-800/50 text-[10px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 transition-colors disabled:opacity-50"
          >
            {downloadingResponse ? (
              <Loader2 className="h-4 w-4 text-slate-600 animate-spin" />
            ) : (
              <Printer className="h-4 w-4 text-slate-600 dark:text-slate-350" />
            )}
            <span>{downloadingResponse ? 'Generating...' : 'Response Doc'}</span>
          </button>
        </div>

        <Button onClick={onReset} className="w-full gap-2 text-xs bg-[#1E3A5F] hover:bg-[#152e4f] text-white">
          <RotateCcw className="h-4 w-4" />
          Process Another RTI
        </Button>
      </div>
    </div>
  )
}
