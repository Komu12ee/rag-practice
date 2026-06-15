interface StepIndicatorProps {
  currentStep: 1 | 2 | 3
  completedSteps: number[]
}

const STEPS = [
  { num: 1, label: '1 Intake' },
  { num: 2, label: '2 Processing' },
  { num: 3, label: '3 Reply' },
]

export default function StepIndicator({ currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        padding: '6px 12px',
        background: 'var(--s1)',
        border: 'var(--border)',
        borderRadius: 'var(--radius)',
        width: '100%',
        height: '40px',
        boxSizing: 'border-box',
      }}
      className="select-none shadow-sm"
    >
      {STEPS.map((step, index) => {
        const isComplete = completedSteps.includes(step.num)
        const isActive = currentStep === step.num
        const isLast = index === STEPS.length - 1

        return (
          <div key={step.num} style={{ display: 'flex', alignItems: 'center' }}>
            <div
              style={{
                fontSize: '15px',
                fontWeight: isActive ? 700 : 600,
                color: isActive ? 'var(--navy)' : isComplete ? 'var(--green)' : 'var(--t3)',
                background: isActive ? 'var(--navy-light)' : 'transparent',
                padding: '2px 8px',
                borderRadius: 'var(--radius)',
                border: isActive ? '1px solid var(--navy)' : '1px solid transparent',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              {isComplete && <span style={{ color: 'var(--green)', fontWeight: 'bold' }}>✓</span>}
              <span>{step.label}</span>
            </div>
            {!isLast && (
              <span style={{ margin: '0 6px', color: 'var(--s3)', fontSize: '14px', fontWeight: 'bold' }}>➔</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
