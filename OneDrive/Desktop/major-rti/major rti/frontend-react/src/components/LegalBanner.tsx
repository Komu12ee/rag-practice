import { useState } from 'react'

export default function LegalBanner() {
  const [isDismissed, setIsDismissed] = useState<boolean>(() => {
    return localStorage.getItem('rti_banner_dismissed') === '1'
  })

  const handleDismiss = () => {
    localStorage.setItem('rti_banner_dismissed', '1')
    setIsDismissed(true)
  }

  if (isDismissed) {
    return (
      <div 
        style={{
          background: 'var(--s2)',
          borderBottom: 'var(--border)',
          padding: '6px 24px',
        }}
        className="flex items-center w-full select-none"
      >
        <span 
          style={{
            fontSize: '12px',
            color: 'var(--amber)',
            fontWeight: 500,
          }}
        >
          Legal research assistance only — final RTI decisions remain the PIO's responsibility
        </span>
      </div>
    )
  }

  return (
    <div 
      style={{
        borderLeft: '3px solid var(--amber)',
        background: 'var(--amber-bg)',
        padding: '12px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
      }}
      className="w-full rounded-[var(--radius)]"
    >
      <div className="flex-1 pr-4">
        <div 
          style={{
            fontSize: '11px',
            textTransform: 'uppercase',
            color: 'var(--amber)',
            fontWeight: 600,
            marginBottom: '4px',
            letterSpacing: '0.06em',
          }}
        >
          ⚠ Legal Notice
        </div>
        <div 
          style={{
            fontSize: '13px',
            color: 'var(--t2)',
            lineHeight: '1.5',
          }}
        >
          This system provides legal research and drafting assistance only. The final decision under the RTI Act, 2005 remains the responsibility of the concerned PIO.
        </div>
      </div>
      <button
        onClick={handleDismiss}
        className="btn btn-ghost btn-sm shrink-0"
        style={{
          color: 'var(--amber)',
        }}
      >
        ✓ Understood
      </button>
    </div>
  )
}
