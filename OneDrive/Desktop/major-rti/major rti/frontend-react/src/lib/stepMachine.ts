import { 
  OCRResult, 
  RoutingResult, 
  ExtractedInformation, 
  EvaluationResult, 
  AuditRecord 
} from './types';

export type Step = "input" | "processing" | "result" | "refine" | "completed";

export interface DashboardState {
  step: Step;
  rawText: string;
  language: string;
  ocrResult: OCRResult | null;
  routingResult: RoutingResult | null;
  extractedInfo: ExtractedInformation | null;
  evaluationResult: EvaluationResult | null;
  draftText: string;
  draftWarning: string | null;
  draftVersion: number;
  loggedRecord: AuditRecord | null;
}

export type DashboardAction =
  | { type: 'SUBMIT_APPLICATION'; payload: { text: string; language: string; ocr: OCRResult | null } }
  | { type: 'PIPELINE_COMPLETE'; payload: { routing: RoutingResult; extraction: ExtractedInformation; evaluation: EvaluationResult; draft: string; warning?: string | null } }
  | { type: 'LOG_DECISION'; payload: { record: AuditRecord } }
  | { type: 'START_OVER' }
  | { type: 'EDIT_PARAMETERS' }
  | { type: 'REGENERATE_DRAFT'; payload: { routing: RoutingResult; extraction: ExtractedInformation; draft: string; warning?: string | null } }
  | { type: 'BACK_TO_RESULT' };

export const initialState: DashboardState = {
  step: 'input',
  rawText: '',
  language: 'en',
  ocrResult: null,
  routingResult: null,
  extractedInfo: null,
  evaluationResult: null,
  draftText: '',
  draftWarning: null,
  draftVersion: 1,
  loggedRecord: null,
};

export function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'SUBMIT_APPLICATION':
      return {
        ...state,
        step: 'processing',
        rawText: action.payload.text,
        language: action.payload.language,
        ocrResult: action.payload.ocr,
        routingResult: null,
        extractedInfo: null,
        evaluationResult: null,
        draftText: '',
        draftWarning: null,
        draftVersion: 1,
        loggedRecord: null,
      };

    case 'PIPELINE_COMPLETE':
      return {
        ...state,
        step: 'result',
        routingResult: action.payload.routing,
        extractedInfo: action.payload.extraction,
        evaluationResult: action.payload.evaluation,
        draftText: action.payload.draft,
        draftWarning: action.payload.warning || null,
      };

    case 'EDIT_PARAMETERS':
      return {
        ...state,
        step: 'refine',
      };

    case 'REGENERATE_DRAFT':
      return {
        ...state,
        step: 'result',
        routingResult: action.payload.routing,
        extractedInfo: action.payload.extraction,
        draftText: action.payload.draft,
        draftWarning: action.payload.warning || null,
        draftVersion: state.draftVersion + 1,
      };

    case 'BACK_TO_RESULT':
      return {
        ...state,
        step: 'result',
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
