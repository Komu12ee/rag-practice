import { z } from 'zod';
import {
  OCRResult,
  RoutingResult,
  ExtractedInformation,
  EvaluationResult,
  AuditRecord,
  AuditTrailRecord,
  LegalSection,
  ExemptionFlag,
  StatutoryReference,
  BalancerOutput,
  Recommendation
} from './types';

// Zod schema for Step 2 Form parameter validation
export const ExtractedInformationSchema = z.object({
  classification_type: z.enum(['citizen_data', 'employee', 'procurement', 'cybersecurity', 'other'], {
    required_error: "Classification type is required.",
  }),
  entities: z.array(z.string()),
  systems: z.array(z.string()),
  procurement_status: z.enum(['none', 'active_tender', 'completed_tender']),
  personal_data: z.boolean(),
  public_interest: z.boolean(),
  explanation: z.string().min(1, "Please provide an explanation notes."),
});

// Zod schema for Step 3 PIO decision logging validation
export const PIOLogSchema = z.object({
  pio_action_taken: z.enum(['APPROVED', 'PARTIALLY_APPROVE', 'REJECTED', 'TRANSFER', 'PENDING', 'OVERRIDDEN']),
  override_department: z.string().optional(),
  reasoning_notes: z.string().min(5, "Decision notes must be at least 5 characters long."),
  disclaimer_checkbox: z.literal(true, {
    errorMap: () => ({ message: "You must accept legal responsibility to proceed." }),
  }),
});

/**
 * Upload scanned file for OCR extraction
 */
export async function uploadFileForOCR(file: File): Promise<OCRResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/ocr', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`OCR processing failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Route application to target department
 */
export async function routeApplication(text: string, language: string): Promise<RoutingResult> {
  const response = await fetch('/api/route', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  });

  if (!response.ok) {
    throw new Error(`routing failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Extract parameters from text
 */
export async function extractParameters(text: string): Promise<ExtractedInformation> {
  const response = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw new Error(`parameter extraction failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Evaluate exemptions and generate RAG analyses, balancing arguments, and final synthesis recommendation
 */
export async function evaluateExemptionsAndSynthesis(verifiedInfo: ExtractedInformation): Promise<EvaluationResult> {
  const response = await fetch('/api/evaluate_exemptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(verifiedInfo),
  });

  if (!response.ok) {
    throw new Error(`exemption rules evaluation failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Log final PIO decision to the immutable hash chain
 */
export async function logFinalDecision(auditRecord: Omit<AuditRecord, 'timestamp'>): Promise<AuditRecord> {
  const payload = {
    ...auditRecord,
    timestamp: new Date().toISOString(),
  };

  const response = await fetch('/api/log_decision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errMsg = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errMsg = errJson.detail;
      }
    } catch {
      // Ignore
    }
    throw new Error(`decision logging failed: ${errMsg}`);
  }

  return response.json();
}

/**
 * Fetch audit trail records and chain validation status.
 */
export async function fetchAuditTrail(limit: number = 100): Promise<{ records: AuditTrailRecord[]; chain_valid: boolean }> {
  const response = await fetch(`/api/audit_trail?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch audit trail: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch system status information (database, Ollama, OCR engines).
 */
export async function fetchSystemStatus(): Promise<
  {
    database: { path: string; connected: boolean; record_count: number };
    ollama: { reachable: boolean; models: string[] };
    ocr: { pdfplumber: boolean; pytesseract: boolean };
  }
> {
  const response = await fetch('/api/system_status');
  if (!response.ok) {
    throw new Error(`Failed to fetch system status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch legal sections database.
 */
export async function fetchLegalSections(): Promise<LegalSection[]> {
  const response = await fetch('/api/legal_sections');
  if (!response.ok) {
    throw new Error(`Failed to fetch legal sections: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Generate AI-generated draft response.
 */
export async function generatePIODraft(params: {
  routing: RoutingResult;
  confirmed_info: ExtractedInformation;
  exemption_flags: ExemptionFlag[];
  layer_b_res: StatutoryReference[];
  balance_res: BalancerOutput;
  final_recom: Recommendation;
  department: string;
  is_chips: boolean;
}): Promise<{ draft: string; warning?: string }> {
  const response = await fetch('/api/generate_draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    throw new Error(`Failed to generate draft: ${response.statusText}`);
  }
  return response.json();
}

