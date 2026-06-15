import { useReducer, useEffect, useState } from 'react'
import { dashboardReducer, initialState } from './lib/stepMachine'
import InputStep from './components/steps/InputStep'
import ReviewStep from './components/steps/ReviewStep'
import ExemptionStep from './components/steps/ExemptionStep'
import CompletedStep from './components/steps/CompletedStep'
import { OCRResult, RoutingResult, ExtractedInformation, EvaluationResult, AuditRecord } from './lib/types'
import AuditTrailView from './components/views/AuditTrailView'
import RTIReferenceView from './components/views/RTIReferenceView'
import LegalBanner from './components/LegalBanner'
import StepIndicator from './components/StepIndicator'
import { fetchAuditTrail } from './lib/api'

type Tab = 'analysis' | 'reference' | 'audit'

const TABS: { id: Tab; label: string }[] = [
  { id: 'analysis', label: 'New Analysis' },
  { id: 'reference', label: 'RTI Act' },
  { id: 'audit', label: 'Audit Trail' },
]

export default function App() {
  const [state, dispatch] = useReducer(dashboardReducer, initialState)
  const [activeTab, setActiveTab] = useState<Tab>('analysis')
  const [pendingCount, setPendingCount] = useState<number>(0)

  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('rti_theme') as 'light' | 'dark') || 'light'
  )

  // Generate Case ID on mount, persist in sessionStorage
  const [caseId, setCaseId] = useState<string>(() => {
    const cached = sessionStorage.getItem('rti_case_id')
    if (cached) return cached
    const year = new Date().getFullYear()
    const uuid8 = crypto.randomUUID().replace(/-/g, '').slice(0, 8).toUpperCase()
    const newId = `RTI/CHiPS/${year}/${uuid8}`
    sessionStorage.setItem('rti_case_id', newId)
    return newId
  })

  // Theme effect targeting data-theme on html element
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('rti_theme', theme)
  }, [theme])



  // Fetch pending audit trail records on mount & active tab change
  useEffect(() => {
    async function checkPending() {
      try {
        const data = await fetchAuditTrail(200)
        const pending = data.records.filter(r => r.pio_action_taken === 'PENDING').length
        setPendingCount(pending)
      } catch {
        // Ignore
      }
    }
    checkPending()
    const interval = setInterval(checkPending, 30000)
    return () => clearInterval(interval)
  }, [activeTab, state.step])

  const toggleTheme = () => setTheme(prev => (prev === 'light' ? 'dark' : 'light'))

  // ----- step machine callbacks -----
  const handleAnalysisComplete = (payload: {
    text: string
    language: string
    ocr: OCRResult | null
    routing: RoutingResult
    extraction: ExtractedInformation
  }) => dispatch({ type: 'START_ANALYSIS', payload })

  const handleConfirmParameters = (confirmed: ExtractedInformation, evaluation: EvaluationResult | null) =>
    dispatch({ type: 'CONFIRM_PARAMETERS', payload: { confirmed, evaluation } })

  const handleEvaluationLoaded = (evaluation: EvaluationResult) =>
    dispatch({ type: 'SET_EVALUATION', payload: { evaluation } })

  const handleDecisionLogged = (record: AuditRecord) => {
    dispatch({ type: 'LOG_DECISION', payload: { record } })
    setPendingCount(prev => Math.max(0, prev - 1))
  }

  const handleStartOver = () => {
    const year = new Date().getFullYear()
    const uuid8 = crypto.randomUUID().replace(/-/g, '').slice(0, 8).toUpperCase()
    const newId = `RTI/CHiPS/${year}/${uuid8}`
    sessionStorage.setItem('rti_case_id', newId)
    setCaseId(newId)
    dispatch({ type: 'START_OVER' })
  }
  const handleEditParameters = () => dispatch({ type: 'EDIT_PARAMETERS' })

  const handleNewCase = () => {
    if (window.confirm("Start a new case? Current analysis will be cleared.")) {
      const year = new Date().getFullYear()
      const uuid8 = crypto.randomUUID().replace(/-/g, '').slice(0, 8).toUpperCase()
      const newId = `RTI/CHiPS/${year}/${uuid8}`
      sessionStorage.setItem('rti_case_id', newId)
      setCaseId(newId)
      dispatch({ type: 'START_OVER' })
      setActiveTab('analysis')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* ───────────────────────── ZONE 1 — Masthead ───────────────────────── */}
      {/* ───────────────────────── Top Metadata Bar ───────────────────────── */}
      <div className="h-[30px] flex items-center justify-between px-6 bg-[var(--navy)] text-white select-none shrink-0 z-30 text-[13px]">
        <div className="flex items-center gap-3 text-white/90">
          <div>
            <span className="opacity-70 mr-1">Case ID:</span>
            <span className="font-mono font-semibold">{caseId}</span>
          </div>
          <div className="w-[1px] h-3 bg-white/20" />
          <div>
            <span className="opacity-70 mr-1">Deadline:</span>
            <span className="font-semibold text-amber-300">
              {new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
          </div>
          <div className="w-[1px] h-3 bg-white/20" />
          <div>
            <span className="opacity-70 mr-1">Officer:</span>
            <span className="font-semibold">Shri Sridhar Dewan, PIO</span>
          </div>
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="h-[20px] w-[20px] flex items-center justify-center rounded text-white hover:bg-white/10 transition-colors"
          title="Toggle theme"
        >
          {theme === 'light' ? (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
            </svg>
          )}
        </button>
      </div>

      {/* ───────────────────────── Main Header Bar ───────────────────────── */}
      <header className="h-[72px] flex items-center justify-between px-6 bg-white dark:bg-slate-900 border-b border-[var(--s3)] select-none shrink-0 z-30">
        <div className="flex items-center gap-4">
          <img src="/chips-logo.webp" alt="CHiPS Logo" className="h-[52px] object-contain shrink-0" />
          <div className="w-[1px] h-8 bg-slate-350 dark:bg-slate-700" />
          <span className="text-[22px] font-bold tracking-wide text-slate-800 dark:text-white font-sans" style={{ fontFamily: '"Source Sans 3", var(--font-ui)' }}>
            RTI Intelligence System
          </span>
        </div>
      </header>

      {/* ───────────────────────── ZONE 2 — Tab Navigation ───────────────────────── */}
      <nav className="h-[40px] bg-[var(--s1)] border-b-2 border-[var(--s3)] flex items-center justify-between px-6 shrink-0 z-20">
        <div className="flex items-stretch h-full">
          {TABS.map(({ id, label }) => {
            const active = activeTab === id
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                style={{
                  borderBottom: active ? '2px solid var(--navy)' : '2px solid transparent',
                  marginBottom: '-2px',
                }}
                className={`relative flex items-center px-[20px] h-full text-[13px] font-medium transition-colors hover:bg-[var(--s2)] hover:text-[var(--t1)] focus:outline-none ${
                  active
                    ? 'text-[var(--navy)] font-semibold'
                    : 'text-[var(--t2)]'
                }`}
              >
                <span className="relative">
                  {label}
                  {id === 'audit' && pendingCount > 0 && (
                    <span 
                      style={{
                        position: 'absolute',
                        top: '-6px',
                        right: '-18px',
                        width: '16px',
                        height: '16px',
                        borderRadius: '50%',
                        background: 'var(--red)',
                        color: '#ffffff',
                        fontSize: '10px',
                        fontWeight: 'bold',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        lineHeight: 1,
                      }}
                    >
                      {pendingCount}
                    </span>
                  )}
                </span>
              </button>
            )
          })}
        </div>
        <button
          onClick={handleNewCase}
          className="btn btn-ghost btn-sm text-[12px] font-semibold text-slate-500 hover:text-slate-700 hover:bg-slate-100/50"
        >
          + New Case
        </button>
      </nav>

      <LegalBanner />

      {/* ───────────────────────── Main Content ───────────────────────── */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-6 overflow-y-auto">
        {activeTab === 'analysis' && (
          <div className="animate-fadeIn space-y-4">
            {state.step !== 'completed' && (
              <StepIndicator
                currentStep={state.step === 'input' ? 1 : state.step === 'review_extraction' ? 2 : 3}
                completedSteps={
                  state.step === 'input' ? [] : state.step === 'review_extraction' ? [1] : [1, 2]
                }
              />
            )}

            {state.step !== 'completed' ? (
              state.step === 'exemption_analysis' && state.routingResult && state.extractedInfo ? (
                <ExemptionStep
                  caseId={caseId}
                  rawText={state.rawText}
                  routing={state.routingResult}
                  confirmedInfo={state.extractedInfo}
                  evaluationResult={state.evaluationResult}
                  onEvaluationLoaded={handleEvaluationLoaded}
                  onDecisionLogged={handleDecisionLogged}
                  onEditParameters={handleEditParameters}
                />
              ) : (
                <div className="space-y-4 w-full">
                  {state.step === 'input' && (
                    <InputStep onAnalysisComplete={handleAnalysisComplete} />
                  )}

                  {state.step === 'review_extraction' && state.routingResult && state.extractedInfo && (
                    <ReviewStep
                      routing={state.routingResult}
                      extraction={state.extractedInfo}
                      onConfirm={handleConfirmParameters}
                      onStartOver={handleStartOver}
                    />
                  )}
                </div>
              )
            ) : (
              <CompletedStep loggedRecord={state.loggedRecord} rawText={state.rawText} onReset={handleStartOver} />
            )}
          </div>
        )}

        {activeTab === 'reference' && (
          <div className="animate-fadeIn">
            <RTIReferenceView />
          </div>
        )}

        {activeTab === 'audit' && (
          <div className="animate-fadeIn">
            <AuditTrailView />
          </div>
        )}
      </main>
    </div>
  )
}
