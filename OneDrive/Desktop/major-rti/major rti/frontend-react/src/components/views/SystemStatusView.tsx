import { useEffect, useState } from 'react'
import { fetchSystemStatus } from '../../lib/api'

interface StatusData {
  database: { path: string; connected: boolean; record_count: number }
  ollama: { reachable: boolean; models: string[] }
  ocr: { pdfplumber: boolean; pytesseract: boolean }
}

export default function SystemStatusView() {
  const [data, setData] = useState<StatusData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadData = async () => {
    setLoading(true)
    setError('')
    try {
      setData(await fetchSystemStatus())
    } catch (e: any) {
      setError(e.message || 'Failed to check system services status.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const principles = [
    { title: 'Human Final Decision', desc: 'PIO must accept legal responsibility before any decision is finalized under RTI Act 2005, Section 5.' },
    { title: 'Immutable Audit Trail', desc: 'Append-only, SHA-256 hash-chained audit log register. No updates or deletions ever allowed.' },
    { title: 'Strict Jurisdiction Routing', desc: 'Verify target jurisdiction first. Applications that concern external department records must be transferred under Section 6(3).' },
    { title: 'Exemption-by-Default Reject', desc: 'Any exemption flag or non-disclosure trigger must be explicitly confirmed with statutory legal grounds.' },
    { title: 'Proportionality Balance', desc: 'Weigh public interest override against statutory refusal risks to balance disclosure decisions.' },
  ]

  if (loading) {
    return <div className="text-left text-xs py-8 text-[var(--t3)]">Loading…</div>
  }

  const isDbOnline = data?.database.connected ?? false
  const isOcrOnline = (data?.ocr.pdfplumber || data?.ocr.pytesseract) ?? false
  const isRoutingOnline = data?.ollama.reachable ?? false

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-fadeIn text-left select-none">
      {/* Header */}
      <div>
        <span className="text-page-title">System Status</span>
        <p className="text-caption mt-1">Component health and configuration</p>
      </div>

      {error && (
        <div className="text-[13px] text-[var(--red)] font-semibold">
          Error checking status: {error}
        </div>
      )}

      {/* COMPONENT HEALTH */}
      <div className="space-y-3">
        <span className="text-section-hd">COMPONENT HEALTH</span>
        <hr className="divider" style={{ margin: '4px 0 12px' }} />

        <table className="data-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Database (SQLite)</td>
              <td>
                <span className="flex items-center gap-1.5 font-semibold">
                  <span className={`dot ${isDbOnline ? 'dot-green' : 'dot-red'}`} />
                  <span style={{ color: isDbOnline ? 'var(--green)' : 'var(--red)' }}>
                    {isDbOnline ? 'Online' : 'Offline'}
                  </span>
                </span>
              </td>
              <td>Immutable audit trail storage</td>
            </tr>
            <tr>
              <td>OCR Engine (Plumber/Tesseract)</td>
              <td>
                <span className="flex items-center gap-1.5 font-semibold">
                  <span className={`dot ${isOcrOnline ? 'dot-green' : 'dot-red'}`} />
                  <span style={{ color: isOcrOnline ? 'var(--green)' : 'var(--red)' }}>
                    {isOcrOnline ? 'Online' : 'Offline'}
                  </span>
                </span>
              </td>
              <td>PDF and image text extraction engine</td>
            </tr>
            <tr>
              <td>Routing Classifier Engine</td>
              <td>
                <span className="flex items-center gap-1.5 font-semibold">
                  <span className={`dot ${isRoutingOnline ? 'dot-green' : 'dot-red'}`} />
                  <span style={{ color: isRoutingOnline ? 'var(--green)' : 'var(--red)' }}>
                    {isRoutingOnline ? 'Online' : 'Offline'}
                  </span>
                </span>
              </td>
              <td>Department jurisdiction classifier</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* LLM MODELS (OLLAMA) */}
      <div className="space-y-3" style={{ marginTop: '24px' }}>
        <span className="text-section-hd">LLM MODELS (OLLAMA)</span>
        <hr className="divider" style={{ margin: '4px 0 12px' }} />

        <table className="data-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Status</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {!data?.ollama.models || data.ollama.models.length === 0 ? (
              <tr>
                <td colSpan={3} className="text-caption py-4">
                  No models found. Run `ollama pull qwen2.5:3b` to set up.
                </td>
              </tr>
            ) : (
              data.ollama.models.map((model, idx) => (
                <tr key={idx}>
                  <td className="font-mono text-xs">{model}</td>
                  <td>
                    <span className="flex items-center gap-1.5 font-semibold">
                      <span className="dot dot-green" />
                      <span style={{ color: 'var(--green)' }}>Online</span>
                    </span>
                  </td>
                  <td>{model.includes('nomic') ? '274 MB' : '3.1 GB'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* ARCHITECTURE PRINCIPLES */}
      <div className="space-y-3" style={{ marginTop: '24px' }}>
        <span className="text-section-hd">ARCHITECTURE PRINCIPLES</span>
        <hr className="divider" style={{ margin: '4px 0 12px' }} />

        <div className="divide-y divide-[var(--s3)] border-b border-[var(--s3)]">
          {principles.map((pr, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '16px',
                padding: '10px 0',
              }}
              className="items-start"
            >
              <div
                style={{ width: '28px' }}
                className="font-mono text-[13px] text-[var(--t3)] shrink-0"
              >
                0{idx + 1}
              </div>
              <div className="flex-1">
                <p className="text-[13px] font-semibold text-[var(--t1)]">{pr.title}</p>
                <p className="text-caption mt-0.5">{pr.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
