export interface OCRResult {
  text: string;
  confidence: number;
  language: string;
  warnings: string[];
}

export interface RoutingResult {
  primary_department: string;
  department_name?: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasoning: string;
  alternatives: string[];
  transfer_applicable?: boolean;
}

export interface ExtractedInformation {
  classification_type: string;
  entities: string[];
  systems: string[];
  procurement_status: "none" | "active_tender" | "completed_tender";
  personal_data: boolean;
  public_interest: boolean;
  explanation: string;
}

export interface ExemptionFlag {
  section: string;
  title: string;
  reasoning: string;
  suggested_action: string;
  is_overridden: boolean;
  override_reason?: string;
}

export interface StatutoryReference {
  section: string;
  title: string;
  is_applicable: boolean;
  confidence_score: number;
  legal_reasoning: string;
  exact_quotes: string[];
}

export interface RetrievedReference {
  source_type: string;
  title: string;
  case_number?: string;
  public_authority?: string;
  outcome?: string;
  relevant_section: string;
  extracted_passage: string;
  why_relevant: string;
  confidence_score: number;
  metadata?: Record<string, unknown>;
}

export interface BalancerOutput {
  pro_disclosure_argument: string;
  pro_exemption_argument: string;
  balancing_factors: string;
}

export interface Recommendation {
  action: "APPROVE" | "PARTIALLY_APPROVE" | "REJECT" | "TRANSFER";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasoning: string;
  citations: string[];
  timeline: string;
}

export interface EvaluationResult {
  exemption_flags: ExemptionFlag[];
  layer_b_res: StatutoryReference[];
  balance_res: BalancerOutput;
  final_recom: Recommendation;
}

export interface AuditRecord {
  pio_action_taken: "APPROVED" | "PARTIALLY_APPROVE" | "REJECTED" | "TRANSFER" | "PENDING" | "OVERRIDDEN";
  override_department?: string;
  reasoning_notes: string;
  extracted_info: ExtractedInformation;
  routing: RoutingResult;
  evaluation: EvaluationResult;
  timestamp: string;
  audit_id?: string;
  current_hash?: string;
}

export interface AuditTrailRecord {
  audit_id: string;
  timestamp: string;
  raw_input_text: string;
  language_detected: string;
  system_recommended_department: string;
  system_confidence_band: string;
  system_reasoning: string;
  information_type: string;
  rule_engine_flags: string[];
  pio_action_taken: string;
  pio_override_department?: string | null;
  pio_comments?: string | null;
  current_hash: string;
  previous_hash: string;
  extracted_entities?: string[];
  ocr_confidence?: number;
}

export interface LegalSection {
  section_number: string;
  title: string;
  module: string;
  definition: string;
  practical_implication: string;
  chips_relevance: string;
  common_mistakes: string;
  source_reference: string;
  keywords: string[];
}

