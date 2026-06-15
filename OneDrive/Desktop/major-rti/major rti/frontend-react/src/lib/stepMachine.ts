import { 
  OCRResult, 
  RoutingResult, 
  ExtractedInformation, 
  EvaluationResult, 
  AuditRecord 
} from './types';

export type Step = "input" | "review_extraction" | "exemption_analysis" | "completed";

export interface DashboardState {
  step: Step;
  rawText: string;
  language: string;
  ocrResult: OCRResult | null;
  routingResult: RoutingResult | null;
  extractedInfo: ExtractedInformation | null;
  evaluationResult: EvaluationResult | null;
  loggedRecord: AuditRecord | null;
}

export type DashboardAction =
  | { type: 'START_ANALYSIS'; payload: { text: string; language: string; ocr: OCRResult | null; routing: RoutingResult; extraction: ExtractedInformation } }
  | { type: 'CONFIRM_PARAMETERS'; payload: { confirmed: ExtractedInformation; evaluation: EvaluationResult | null } }
  | { type: 'SET_EVALUATION'; payload: { evaluation: EvaluationResult } }
  | { type: 'LOG_DECISION'; payload: { record: AuditRecord } }
  | { type: 'START_OVER' }
  | { type: 'EDIT_PARAMETERS' };

export const initialState: DashboardState = {
  step: 'input',
  rawText: '',
  language: 'en',
  ocrResult: null,
  routingResult: null,
  extractedInfo: null,
  evaluationResult: null,
  loggedRecord: null,
};

export function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'START_ANALYSIS':
      return {
        ...state,
        step: 'review_extraction',
        rawText: action.payload.text,
        language: action.payload.language,
        ocrResult: action.payload.ocr,
        routingResult: action.payload.routing,
        extractedInfo: action.payload.extraction,
      };

    case 'CONFIRM_PARAMETERS':
      return {
        ...state,
        step: 'exemption_analysis',
        extractedInfo: action.payload.confirmed,
        evaluationResult: action.payload.evaluation,
      };

    case 'SET_EVALUATION':
      return {
        ...state,
        evaluationResult: action.payload.evaluation,
      };

    case 'EDIT_PARAMETERS':
      return {
        ...state,
        step: 'review_extraction',
      };

    case 'LOG_DECISION':
      return {
        ...state,
        step: 'completed',
        loggedRecord: action.payload.record,
      };

    case 'START_OVER':
      return initialState;

    default:
      return state;
  }
}
