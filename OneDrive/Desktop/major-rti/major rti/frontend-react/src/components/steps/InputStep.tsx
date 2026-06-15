import { useState, ChangeEvent, DragEvent, useRef } from 'react'
import { FileUp, Loader2, FileText, X, FileCheck } from 'lucide-react'
import ErrorBanner from '../ErrorBanner'
import { uploadFileForOCR, routeApplication, extractParameters } from '../../lib/api'
import { OCRResult, RoutingResult, ExtractedInformation } from '../../lib/types'

interface InputStepProps {
  onAnalysisComplete: (payload: {
    text: string
    language: string
    ocr: OCRResult | null
    routing: RoutingResult
    extraction: ExtractedInformation
  }) => void
}

export default function InputStep({ onAnalysisComplete }: InputStepProps) {
  const [file, setFile] = useState<File | null>(null)
  const [manualText, setManualText] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [stage, setStage] = useState(0) // 0: OCR/Intake, 1: Routing, 2: Classification
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)

  // New state variables to support immediate OCR processing & quality gates
  const [isOcrLoading, setIsOcrLoading] = useState(false)
  const [ocrResult, setOcrResult] = useState<OCRResult | null>(null)
  const [ocrWarning, setOcrWarning] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const detectLanguage = (text: string): string => {
    const devanagariRegex = /[\u0900-\u097F]/g;
    const devanagariCount = (text.match(devanagariRegex) || []).length;
    const asciiCount = (text.match(/[A-Za-z]/g) || []).length;
    const total = devanagariCount + asciiCount;
    if (total === 0) return 'en';
    const ratio = devanagariCount / total;
    if (ratio > 0.30) return 'hi';
    if (ratio > 0.05) return 'mixed';
    return 'en';
  }

  const runOcrOnUpload = async (selectedFile: File) => {
    setIsOcrLoading(true)
    setError('')
    setOcrWarning(null)
    setOcrResult(null)
    try {
      const result = await uploadFileForOCR(selectedFile)
      setOcrResult(result)
      setManualText(result.text || '')
      
      if (result.warnings && result.warnings.length > 0) {
        setOcrWarning(result.warnings.join(' '))
      } else if (result.confidence < 0.85) {
        setOcrWarning(`OCR quality warning: Confidence is ${(result.confidence * 100).toFixed(0)}%. Manual review of extracted text recommended.`)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to extract text from file.')
      setFile(null)
    } finally {
      setIsOcrLoading(false)
    }
  }

  const validateAndSet = async (selectedFile: File) => {
    const validTypes = [
      'application/pdf',
      'image/png',
      'image/jpeg',
      'image/tiff',
      'image/bmp',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword'
    ]
    const ext = selectedFile.name.toLowerCase().split('.').pop()
    const validExtensions = ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp', 'docx', 'doc']

    if (validTypes.includes(selectedFile.type) || (ext && validExtensions.includes(ext))) {
      setFile(selectedFile)
      setManualText('')
      setError('')
      setOcrWarning(null)
      await runOcrOnUpload(selectedFile)
    } else {
      setError('Unsupported file format. Please upload an official PDF, scanned image (PNG/JPG/BMP/TIF), or Word Document (DOCX/DOC).')
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    if (isLoading || isOcrLoading) return
    const dropped = e.dataTransfer.files
    if (dropped && dropped.length > 0) validateAndSet(dropped[0])
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) validateAndSet(e.target.files[0])
  }

  const handleTextChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setManualText(e.target.value)
    if (e.target.value.trim() && !file) {
      setOcrResult(null)
      setOcrWarning(null)
    }
  }

  const handleStartAnalysis = async () => {
    setIsLoading(true)
    setError('')
    setStage(1) // Stage 1 is Routing

    try {
      const text = manualText.trim()
      if (!text) {
        throw new Error('RTI query text empty. Please upload an application file or enter text manually.')
      }

      const language = ocrResult && ocrResult.confidence >= 0.85 && !ocrWarning
        ? ocrResult.language
        : detectLanguage(text)

      const routingPromise = routeApplication(text, language)
      setStage(2) // Stage 2 is Parameter Extraction
      const [routingResult, extractionResult] = await Promise.all([
        routingPromise,
        extractParameters(text),
      ])

      onAnalysisComplete({ text, language, ocr: ocrResult, routing: routingResult, extraction: extractionResult })
    } catch (err: any) {
      setError(err.message || 'An error occurred during intake processing.')
    } finally {
      setIsLoading(false)
    }
  }

  const isSubmitDisabled = (!file && !manualText.trim()) || isLoading || isOcrLoading

  return (
    <div className="space-y-4 w-full mx-auto animate-fadeIn text-left">
      <div className="grid grid-cols-1 md:grid-cols-[60%_40%] gap-4 items-stretch">
        
        {/* Left Column: 60% Application Upload */}
        <div className="card flex flex-col justify-between min-h-[210px] h-auto space-y-2">
          <div className="flex flex-col space-y-1">
            <span className="text-section-hd">Upload RTI Application</span>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); if (!isLoading && !isOcrLoading) setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center border border-dashed rounded text-center transition-all min-h-[110px] h-auto p-2 ${
              file
                ? 'border-[var(--navy)] bg-[var(--navy-light)]'
                : dragging
                ? 'border-[var(--navy)] bg-[var(--navy-light)]'
                : 'border-slate-300 bg-slate-50/50 hover:border-slate-400 hover:bg-slate-50 cursor-pointer dark:border-slate-700 dark:bg-slate-800/10'
            } ${isLoading || isOcrLoading ? 'opacity-60 pointer-events-none' : ''}`}
            onClick={() => !isLoading && !isOcrLoading && !file && fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.docx,.doc,image/*"
              className="hidden"
              disabled={isLoading || isOcrLoading}
            />
            {isOcrLoading ? (
              <div className="flex flex-col items-center justify-center space-y-1">
                <Loader2 className="h-6 w-6 animate-spin text-[var(--navy)]" />
                <span className="text-[14px] font-semibold text-slate-600">Extracting text...</span>
              </div>
            ) : file && ocrResult ? (
              <div className="flex flex-col items-center justify-center space-y-1 w-full">
                <FileText className="h-6 w-6 text-[var(--navy)] mx-auto" />
                <div className="w-full text-center">
                  <p className="text-[14px] font-semibold text-slate-800 dark:text-slate-200 truncate max-w-[20rem] mx-auto">
                    {file.name}
                  </p>
                  <p className="text-[12px] text-slate-500 mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB · Ready</p>
                </div>
                
                {/* Metadata Row */}
                <div className="grid grid-cols-3 gap-2 w-full pt-1 border-t border-slate-200 dark:border-slate-700 mt-1 max-w-[280px] mx-auto text-slate-600 dark:text-slate-400 font-semibold text-[12px]">
                  <div className="text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">Source</div>
                    <div>{ocrResult.warnings && ocrResult.warnings.some(w => w.includes("docx")) ? 'DOCX' : file.name.split('.').pop()?.toUpperCase()}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">Lang</div>
                    <div>{ocrResult.language.toUpperCase()}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">Conf</div>
                    <div>{(ocrResult.confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setFile(null); setOcrResult(null); setOcrWarning(null); setManualText(''); }}
                  className="inline-flex items-center gap-1 text-[13px] font-semibold text-red-600 hover:text-red-700 transition-colors mt-2"
                >
                  <X className="h-3.5 w-3.5" /> Remove File
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center space-y-1">
                <FileUp className="h-6 w-6 text-slate-400 mx-auto" />
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-outline btn-sm h-[32px] px-4 py-1 text-[14px] font-semibold bg-white dark:bg-slate-800"
                    onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click() }}
                  >
                    Choose File
                  </button>
                  <span className="text-[14px] text-slate-500">or drag and drop</span>
                </div>
              </div>
            )}
          </div>

          <div className="text-[14px] text-slate-500 dark:text-slate-400 pt-1 border-t border-[var(--s3)]">
            Accepted: PDF DOCX DOC JPG PNG TIFF BMP
          </div>
        </div>

        {/* Right Column: 40% Paste RTI Text */}
        <div className="card flex flex-col justify-between min-h-[210px] h-auto space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-section-hd">Paste Application Text</span>
            {manualText && (
              <span className="text-[13px] text-slate-400">{manualText.trim().length} characters</span>
            )}
          </div>
          <textarea
            value={manualText}
            onChange={handleTextChange}
            placeholder="Type or paste the application text here (Hindi and English supported)..."
            style={{ height: '120px', maxHeight: '120px', resize: 'none', fontSize: '16px' }}
            className="w-full text-body"
            disabled={!!(isLoading || isOcrLoading || (file && ocrResult && ocrResult.confidence >= 0.85 && !ocrWarning))}
          />
        </div>
      </div>

      {/* OCR Warnings & Quality Gates */}
      {ocrWarning && (
        <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900 rounded text-[14px] text-amber-800 dark:text-amber-300 space-y-1">
          <div className="font-semibold flex items-center gap-1.5">
            <span>⚠️</span> Warning: {ocrWarning}
          </div>
          {ocrResult && ocrResult.confidence < 0.85 && (
            <div className="text-red-700 dark:text-red-400 font-medium">
              Processing blocked: OCR confidence too low. Please verify and correct the extracted text manually in the text panel before proceeding.
            </div>
          )}
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      <button
        onClick={handleStartAnalysis}
        disabled={isSubmitDisabled}
        className="w-full h-[48px] text-[16px] font-semibold justify-center gap-2 btn btn-primary flex items-center"
      >
        {isLoading ? (
          <>
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Process Case Stage: {stage === 1 ? 'Routing classification' : 'Parameter Extraction'}...</span>
          </>
        ) : (
          <>
            <FileCheck className="h-5 w-5" />
            <span>Process RTI Application</span>
          </>
        )}
      </button>
    </div>
  )
}
