import { useEffect, useMemo, useState } from 'react'
import { fetchAuditTrail } from '../../lib/api'
import type { AuditTrailRecord } from '../../lib/types'
import ErrorBanner from '../ErrorBanner'

const DEPARTMENTS: Record<string, string> = {
  chips: 'CHiPS (Chhattisgarh Infotech)',
  revenue: 'Revenue Department',
  pwd: 'Public Works Department',
  health: 'Health & Family Welfare',
  finance: 'Finance Department',
  other: 'Other Department',
}

export default function AuditTrailView() {
  const [records, setRecords] = useState<AuditTrailRecord[]>([])
  const [chainValid, setChainValid] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Search & Filter state
  const [query, setQuery] = useState('')
  const [filterAction, setFilterAction] = useState('')
  const [filterDept, setFilterDept] = useState('')
  const [filterConfidence, setFilterConfidence] = useState('')
  const [filterDate, setFilterDate] = useState('')
  const [sortBy, setSortBy] = useState('newest')

  const loadData = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchAuditTrail(200)
      setRecords(data.records)
      setChainValid(data.chain_valid)
    } catch (e: any) {
      setError(e.message || 'Failed to fetch audit trail records.')
    } finally {
      setLoading(false)
    }
  };

  useEffect(() => {
    loadData()
  }, [])

  // Calculate Metrics
  const metrics = useMemo(() => {
    const total = records.length
    const approved = records.filter(r => r.pio_action_taken === 'APPROVED').length
    const overridden = records.filter(
      r => r.pio_action_taken === 'OVERRIDDEN' || r.pio_action_taken === 'PARTIALLY_APPROVE' || r.pio_override_department
    ).length
    const overrideRate = total > 0 ? Math.round((overridden / total) * 100) : 0
    return { total, approved, overridden, overrideRate }
  }, [records])

  // Unique departments for filter list
  const uniqueDepartments = useMemo(() => {
    const depts = new Set<string>()
    records.forEach(r => {
      if (r.system_recommended_department) depts.add(r.system_recommended_department)
      if (r.pio_override_department) depts.add(r.pio_override_department)
    })
    return Array.from(depts)
  }, [records])

  // Filter and Sort records
  const filteredRecords = useMemo(() => {
    const q = query.trim().toLowerCase()

    let result = records.filter(r => {
      // Search logic
      if (q) {
        const idMatch = r.audit_id.toLowerCase().includes(q)
        const deptMatch = (r.system_recommended_department || '').toLowerCase().includes(q)
        const commentsMatch = (r.pio_comments || '').toLowerCase().includes(q)
        const reasoningMatch = (r.system_reasoning || '').toLowerCase().includes(q)
        
        // Joined entities search (SQLite field rule_engine_flags or raw_input_text)
        const entitiesString = (r.extracted_entities || []).join(' ').toLowerCase()
        const entitiesMatch = entitiesString.includes(q)
        const textMatch = (r.raw_input_text || '').toLowerCase().includes(q)

        if (!idMatch && !deptMatch && !commentsMatch && !reasoningMatch && !entitiesMatch && !textMatch) {
          return false
        }
      }

      // PIO Action filter
      if (filterAction) {
        if (filterAction === 'APPROVED') {
          if (r.pio_action_taken !== 'APPROVED') return false
        } else if (filterAction === 'OVERRIDDEN') {
          const isOverridden = r.pio_action_taken === 'OVERRIDDEN' || r.pio_action_taken === 'PARTIALLY_APPROVE' || r.pio_override_department
          if (!isOverridden) return false
        } else if (filterAction === 'REJECTED') {
          if (r.pio_action_taken !== 'REJECTED' && r.pio_action_taken !== 'REJECT') return false
        } else if (filterAction === 'PENDING') {
          if (r.pio_action_taken !== 'PENDING') return false
        }
      }

      // Department filter
      if (filterDept) {
        if (r.system_recommended_department !== filterDept && r.pio_override_department !== filterDept) {
          return false
        }
      }

      // Confidence band filter
      if (filterConfidence) {
        if (r.system_confidence_band !== filterConfidence) return false
      }

      // Date range filter
      if (filterDate) {
        const now = new Date()
        const recordTime = new Date(r.timestamp)
        const diffTime = Math.abs(now.getTime() - recordTime.getTime())
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

        if (filterDate === 'Today' && diffDays > 1) return false
        if (filterDate === 'Last 7 Days' && diffDays > 7) return false
        if (filterDate === 'Last 30 Days' && diffDays > 30) return false
      }

      return true
    })

    // Sort logic
    result.sort((a, b) => {
      if (sortBy === 'newest') {
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      } else if (sortBy === 'oldest') {
        return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      } else if (sortBy === 'action') {
        return (a.pio_action_taken || '').localeCompare(b.pio_action_taken || '')
      } else if (sortBy === 'department') {
        const nameA = DEPARTMENTS[a.system_recommended_department] || a.system_recommended_department || ''
        const nameB = DEPARTMENTS[b.system_recommended_department] || b.system_recommended_department || ''
        return nameA.localeCompare(nameB)
      } else if (sortBy === 'confidence') {
        const priority: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 }
        const scoreA = priority[a.system_confidence_band] || 0
        const scoreB = priority[b.system_confidence_band] || 0
        return scoreB - scoreA
      }
      return 0
    })

    return result
  }, [records, query, filterAction, filterDept, filterConfidence, filterDate, sortBy])

  // CSV Exporter
  const handleCSVExport = () => {
    const headers = [
      'Audit ID', 'Timestamp', 'PIO Action Taken', 'Override Department',
      'PIO Comments', 'System Recommended Department', 'System Confidence Band',
      'Information Type', 'Block Hash'
    ]
    const data = filteredRecords.map(r => [
      r.audit_id,
      new Date(r.timestamp).toLocaleString(),
      r.pio_action_taken,
      r.pio_override_department || '',
      r.pio_comments || '',
      r.system_recommended_department,
      r.system_confidence_band,
      r.information_type,
      r.current_hash
    ])
    const csvContent = [headers, ...data]
      .map(row => row.map(val => `"${String(val).replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const dateStr = new Date().toISOString().split('T')[0]
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `RTI_Audit_${dateStr}.csv`
    link.click()
  }

  // Get status dot styles
  const getStatusDotClass = (action: string) => {
    if (action === 'APPROVED' || action === 'APPROVED') return 'dot-green'
    if (action === 'OVERRIDDEN' || action === 'PARTIALLY_APPROVE' || action === 'TRANSFER') return 'dot-amber'
    if (action === 'REJECTED' || action === 'REJECT') return 'dot-red'
    return 'dot-grey'
  }

  // Get badge styles
  const getBadgeClass = (action: string) => {
    if (action === 'APPROVED') return 'badge-green'
    if (action === 'OVERRIDDEN' || action === 'PARTIALLY_APPROVE' || action === 'TRANSFER') return 'badge-amber'
    if (action === 'REJECTED' || action === 'REJECT') return 'badge-red'
    return 'badge-grey'
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-fadeIn select-none">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--s3)] pb-3">
        <div className="text-left">
          <span className="text-page-title">Audit Trail Registry</span>
          <p className="text-caption mt-1">Immutable SHA-256 hash-chained register records</p>
        </div>
        <button
          onClick={loadData}
          className="btn btn-outline btn-sm"
          disabled={loading}
        >
          Refresh Register
        </button>
      </div>

      {/* Chain Integrity Banner */}
      <div
        className={`flex items-center gap-3 rounded border p-4 ${
          chainValid
            ? 'border-[var(--green-border)] bg-[var(--green-bg)] text-[var(--green)]'
            : 'border-[var(--red-border)] bg-[var(--red-bg)] text-[var(--red)]'
        }`}
      >
        <span className="font-semibold text-xs uppercase tracking-wider">
          {chainValid ? '✓ Hash Chain Integrity Verified' : '⚠ Hash Chain Compromised'}
        </span>
        <span className="text-caption" style={{ color: 'inherit' }}>|</span>
        <span className="text-[13px] opacity-90">
          {chainValid
            ? 'All cryptographic signatures and block linkage verified — tamper check completed.'
            : 'Integrity validation failed. Database records mismatch detected.'}
        </span>
      </div>

      {/* METRIC ROW */}
      <div className="four-col">
        <div className="card text-center">
          <span className="text-label">TOTAL ANALYSES</span>
          <div className="text-[28px] font-bold mt-2" style={{ color: 'var(--navy)' }}>
            {metrics.total}
          </div>
        </div>
        <div className="card text-center">
          <span className="text-label">APPROVED</span>
          <div className="text-[28px] font-bold mt-2" style={{ color: 'var(--green)' }}>
            {metrics.approved}
          </div>
        </div>
        <div className="card text-center">
          <span className="text-label">OVERRIDDEN</span>
          <div className="text-[28px] font-bold mt-2" style={{ color: 'var(--amber)' }}>
            {metrics.overridden}
          </div>
        </div>
        <div className="card text-center">
          <span className="text-label">OVERRIDE RATE (%)</span>
          <div className="text-[28px] font-bold mt-2" style={{ color: 'var(--navy)' }}>
            {metrics.overrideRate}%
          </div>
        </div>
      </div>

      {/* FILTER + SORT BAR */}
      <div className="card space-y-4">
        {/* ROW 1 — Search */}
        <div className="flex flex-col text-left">
          <label className="text-label">Search register</label>
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search case ID, department, entities, notes…"
            style={{ maxWidth: '380px' }}
            className="mt-1"
          />
        </div>

        {/* ROW 2 — Filters */}
        <div className="flex flex-wrap gap-3 items-end pt-1">
          <div className="flex flex-col text-left max-w-[160px] flex-1">
            <label className="text-label">PIO Action</label>
            <select value={filterAction} onChange={e => setFilterAction(e.target.value)}>
              <option value="">All</option>
              <option value="APPROVED">APPROVED</option>
              <option value="OVERRIDDEN">OVERRIDDEN</option>
              <option value="REJECTED">REJECTED</option>
              <option value="PENDING">PENDING</option>
            </select>
          </div>

          <div className="flex flex-col text-left max-w-[160px] flex-1">
            <label className="text-label">Department</label>
            <select value={filterDept} onChange={e => setFilterDept(e.target.value)}>
              <option value="">All</option>
              {uniqueDepartments.map(dept => (
                <option key={dept} value={dept}>
                  {DEPARTMENTS[dept] || dept}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col text-left max-w-[160px] flex-1">
            <label className="text-label">Confidence</label>
            <select value={filterConfidence} onChange={e => setFilterConfidence(e.target.value)}>
              <option value="">All</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>

          <div className="flex flex-col text-left max-w-[160px] flex-1">
            <label className="text-label">Date Range</label>
            <select value={filterDate} onChange={e => setFilterDate(e.target.value)}>
              <option value="">All Time</option>
              <option value="Today">Today</option>
              <option value="Last 7 Days">Last 7 Days</option>
              <option value="Last 30 Days">Last 30 Days</option>
            </select>
          </div>
        </div>

        {/* ROW 3 — Sort + count + export */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-[var(--s3)] mt-2">
          <div className="flex items-center gap-2">
            <span className="text-label">Sort by:</span>
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value)}
              style={{ maxWidth: '180px' }}
              className="py-1"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="action">Action A–Z</option>
              <option value="department">Department A–Z</option>
              <option value="confidence">Confidence High→Low</option>
            </select>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-[12px] text-[var(--t3)]">
              Showing {filteredRecords.length} of {records.length}
            </span>
            <button onClick={handleCSVExport} className="btn btn-outline btn-sm">
              Export CSV
            </button>
          </div>
        </div>
      </div>

      {/* RECORD LIST */}
      {loading ? (
        <div className="text-center py-12 text-caption">Loading audit log register…</div>
      ) : error ? (
        <ErrorBanner message={error} />
      ) : filteredRecords.length === 0 ? (
        <div className="card text-center" style={{ padding: '40px' }}>
          <div className="text-[13px] text-[var(--t2)] font-semibold">
            No records match your filters.
          </div>
          <div className="text-caption mt-1">Try adjusting the search or filter criteria.</div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {filteredRecords.map(rec => {
            const formattedDate = new Date(rec.timestamp).toLocaleDateString('en-GB', {
              day: '2-digit',
              month: 'short',
              year: 'numeric',
            })

            const displayDept = DEPARTMENTS[rec.system_recommended_department] || rec.system_recommended_department || 'N/A'
            const dotClass = getStatusDotClass(rec.pio_action_taken)
            const badgeClass = getBadgeClass(rec.pio_action_taken)

            return (
              <details
                key={rec.audit_id}
                className="group select-none"
                style={{
                  border: 'none',
                  background: 'none',
                }}
              >
                <summary
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '10px 16px',
                    background: 'var(--s1)',
                    border: 'var(--border)',
                    borderRadius: 'var(--radius)',
                    marginBottom: '4px',
                  }}
                  className="cursor-pointer hover:bg-[var(--s2)] transition-colors list-none justify-between"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {/* Status Dot */}
                    <span className={`dot ${dotClass}`} />
                    
                    {/* Date */}
                    <span
                      style={{ width: '90px' }}
                      className="text-[12px] font-mono text-[var(--t3)] shrink-0"
                    >
                      {formattedDate}
                    </span>

                    {/* Case ID */}
                    <span className="text-[13px] font-mono text-[var(--t1)] truncate shrink-0 max-w-[210px] pr-2">
                      {rec.audit_id}
                    </span>

                    {/* Department */}
                    <span className="text-[13px] text-[var(--t2)] truncate flex-1 pr-2">
                      {displayDept}
                    </span>
                  </div>

                  {/* Action Badge */}
                  <span className={`badge ${badgeClass} shrink-0`}>
                    {rec.pio_action_taken}
                  </span>
                </summary>

                {/* Expanded Details Body */}
                <div
                  className="details-body two-col"
                  style={{
                    background: 'var(--s1)',
                    border: 'var(--border)',
                    borderRadius: 'var(--radius)',
                    padding: '20px 24px',
                    marginTop: '-2px',
                    marginBottom: '8px',
                    boxShadow: 'var(--shadow)',
                  }}
                >
                  {/* Left Column */}
                  <div className="space-y-3">
                    <div className="field">
                      <span className="text-label">Audit ID / Case ID</span>
                      <p className="text-value font-mono">{rec.audit_id}</p>
                    </div>

                    <div className="field">
                      <span className="text-label">System Recommendation</span>
                      <p className="text-value uppercase">{DEPARTMENTS[rec.system_recommended_department] || rec.system_recommended_department}</p>
                    </div>

                    <div className="field">
                      <span className="text-label">Confidence Band</span>
                      <p className="text-value mt-1">
                        <span
                          className={`badge ${
                            rec.system_confidence_band === 'HIGH'
                              ? 'badge-green'
                              : rec.system_confidence_band === 'MEDIUM'
                              ? 'badge-amber'
                              : 'badge-red'
                          }`}
                        >
                          {rec.system_confidence_band}
                        </span>
                      </p>
                    </div>

                    <div className="field">
                      <span className="text-label">Information Type</span>
                      <p className="text-value uppercase">{rec.information_type || 'N/A'}</p>
                    </div>

                    <div className="field">
                      <span className="text-label">Extracted Entities</span>
                      <p className="text-value">
                        {rec.extracted_entities && rec.extracted_entities.length > 0
                          ? rec.extracted_entities.join(', ')
                          : 'None'}
                      </p>
                    </div>

                    <div className="field">
                      <span className="text-label">Rule Engine Flags</span>
                      <p className="text-value">
                        {rec.rule_engine_flags && rec.rule_engine_flags.length > 0
                          ? rec.rule_engine_flags.join(', ')
                          : 'None'}
                      </p>
                    </div>

                    <div className="field">
                      <span className="text-label">Reasoning text</span>
                      <p className="text-value text-[13px] leading-relaxed">
                        {rec.system_reasoning || 'No system reasoning logged.'}
                      </p>
                    </div>

                    <div className="field">
                      <span className="text-label">PIO Comments / Notes</span>
                      <p className="text-value text-[13px] leading-relaxed">
                        {rec.pio_comments || 'No comment notes recorded.'}
                      </p>
                    </div>
                  </div>

                  {/* Right Column */}
                  <div className="space-y-3">
                    <div className="field">
                      <span className="text-label">PIO Action Taken</span>
                      <p className="text-value font-semibold uppercase">{rec.pio_action_taken}</p>
                    </div>

                    <div className="field">
                      <span className="text-label">Language Detected</span>
                      <p className="text-value uppercase">{rec.language_detected}</p>
                    </div>

                    <div className="field">
                      <span className="text-label">OCR Confidence (%)</span>
                      <p className="text-value">
                        {rec.ocr_confidence !== undefined
                          ? `${Math.round(rec.ocr_confidence * 100)}%`
                          : '100%'}
                      </p>
                    </div>

                    {rec.pio_override_department && (
                      <div className="field">
                        <span className="text-label">Overridden To</span>
                        <p className="text-value font-semibold text-[var(--amber)] uppercase">
                          {DEPARTMENTS[rec.pio_override_department] || rec.pio_override_department}
                        </p>
                      </div>
                    )}

                    <div className="field">
                      <span className="text-label">Immutable Block Hash</span>
                      <p className="text-mono font-mono text-[11px] text-[var(--t2)] break-all bg-[var(--s2)] p-2 rounded">
                        {rec.current_hash ? `${rec.current_hash.slice(0, 16)}…` : 'Genesis Block'}
                      </p>
                    </div>
                  </div>
                </div>
              </details>
            )
          })}
        </div>
      )}
    </div>
  )
}
