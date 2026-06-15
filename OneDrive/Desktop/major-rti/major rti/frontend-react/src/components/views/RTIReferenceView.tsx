import { useState, useEffect } from 'react'
import { fetchLegalSections } from '../../lib/api'
import { LegalSection } from '../../lib/types'

export default function RTIReferenceView() {
  const [sections, setSections] = useState<LegalSection[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true)
        const data = await fetchLegalSections()
        setSections(data)
        setError(null)
      } catch (err: any) {
        setError(err.message || 'Failed to load legal reference sections.')
      } finally {
        setIsLoading(false)
      }
    }
    loadData()
  }, [])

  // Filter sections by search query
  const filteredSections = sections.filter(s => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    const titleMatch = (s.title || '').toLowerCase().includes(q)
    const numMatch = (s.section_number || '').toLowerCase().includes(q)
    const defMatch = (s.definition || '').toLowerCase().includes(q)
    const implMatch = (s.practical_implication || '').toLowerCase().includes(q)
    const kwMatch = s.keywords?.some(kw => kw.toLowerCase().includes(q))
    return titleMatch || numMatch || defMatch || implMatch || kwMatch
  })

  // Group sections by module
  const groupedModules: Record<string, LegalSection[]> = {}
  filteredSections.forEach(s => {
    const modName = s.module || 'General'
    if (!groupedModules[modName]) {
      groupedModules[modName] = []
    }
    groupedModules[modName].push(s)
  })

  if (isLoading) {
    return <div className="text-left text-xs py-8 text-[var(--t3)]">Loading…</div>
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-fadeIn text-left select-none">
      {/* Header */}
      <div>
        <span className="text-page-title">RTI Act Reference</span>
        <p className="text-caption mt-1">Legal knowledge base for RTI research and drafting assistance</p>
      </div>

      {/* Search Bar */}
      <div>
        <input
          type="search"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search sections by keyword…"
          style={{ maxWidth: '400px', marginBottom: '20px' }}
        />
      </div>

      {error && (
        <div className="text-[13px] text-[var(--red)] font-semibold py-4">
          Error: {error}
        </div>
      )}

      {/* Group List */}
      {Object.keys(groupedModules).length === 0 ? (
        <p className="text-caption" style={{ padding: '20px 0' }}>
          No sections found for '{searchQuery}'
        </p>
      ) : (
        Object.entries(groupedModules).map(([moduleName, moduleSections]) => (
          <div key={moduleName}>
            {/* Module Header */}
            <div
              style={{
                background: 'var(--s2)',
                padding: '8px 16px',
                borderRadius: 'var(--radius)',
                margin: '20px 0 8px',
              }}
            >
              <span className="text-section-hd">{moduleName}</span>
            </div>

            {/* Sections */}
            <div className="space-y-1">
              {moduleSections.map(section => (
                <details
                  key={section.section_number}
                  className="group"
                  style={{
                    borderBottom: 'var(--border)',
                    padding: '8px 0',
                  }}
                >
                  <summary className="flex items-center justify-between py-1 cursor-pointer select-none text-[13px] font-medium text-[var(--t1)] hover:text-[var(--navy)]">
                    <span>
                      {section.section_number} — {section.title}
                    </span>
                  </summary>

                  <div
                    className="details-body py-4 grid grid-cols-1 md:grid-cols-5 gap-4"
                    style={{
                      borderTop: '1px solid var(--s3)',
                      marginTop: '8px',
                    }}
                  >
                    {/* LEFT (60% width) */}
                    <div className="md:col-span-3 space-y-4">
                      <div className="field">
                        <span className="text-label">DEFINITION / LEGAL TEXT</span>
                        <p className="text-value leading-relaxed mt-1">{section.definition}</p>
                      </div>

                      <div className="field">
                        <span className="text-label">PRACTICAL IMPLICATION</span>
                        <p
                          className="mt-1"
                          style={{
                            background: 'var(--navy-light)',
                            padding: '10px',
                            borderRadius: 'var(--radius)',
                            color: 'var(--navy)',
                            fontSize: '13px',
                            lineHeight: '1.5',
                          }}
                        >
                          {section.practical_implication}
                        </p>
                      </div>
                    </div>

                    {/* RIGHT (40% width) */}
                    <div className="md:col-span-2 space-y-4">
                      {section.chips_relevance && (
                        <div className="field">
                          <span className="text-label">CHIPS-SPECIFIC NOTE</span>
                          <p
                            className="mt-1"
                            style={{
                              background: 'var(--green-bg)',
                              padding: '10px',
                              borderRadius: 'var(--radius)',
                              color: 'var(--green)',
                              fontSize: '13px',
                              lineHeight: '1.5',
                            }}
                          >
                            {section.chips_relevance}
                          </p>
                        </div>
                      )}

                      {section.common_mistakes && (
                        <div className="field">
                          <span className="text-label">COMMON MISTAKES</span>
                          <p
                            className="mt-1"
                            style={{
                              background: 'var(--red-bg)',
                              padding: '10px',
                              borderRadius: 'var(--radius)',
                              color: 'var(--red)',
                              fontSize: '13px',
                              lineHeight: '1.5',
                            }}
                          >
                            {section.common_mistakes}
                          </p>
                        </div>
                      )}

                      {section.source_reference && (
                        <p
                          className="text-caption"
                          style={{
                            textAlign: 'right',
                            marginTop: '8px',
                          }}
                        >
                          Source: {section.source_reference}
                        </p>
                      )}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
