"""
FastAPI Backend API Server for RTI Intelligence System.
======================================================
Serves REST API endpoints to support the React dashboard frontend, 
bridging the 5-Agent pipeline and SQLite database.
"""

import sys
import os
import json
import uuid
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import local backend agents and modules
from db import init_db, log_analysis, get_record, get_audit_trail, verify_chain, DB_PATH, _get_connection, AuditRecord as PythonAuditRecord
from ocr import extract_text_from_pdf, extract_text_from_image
from document_parser import parse_uploaded_file
from routing import classify_department
from extractor import extract_information
from exemption_rules import evaluate_exemptions
from llm_analyzer import analyze_exemption_applicability
from disclosure_balancer import compute_disclosure_balance
from recommendation_generator import generate_final_recommendation
from rag_engine import _load_sections

# Ensure database is initialized
init_db()

# Pre-load sections to title map for statutory citations titles lookup
try:
    SECTIONS_MAP = {s["section"]: s.get("title", "") for s in _load_sections()}
except Exception:
    SECTIONS_MAP = {}

app = FastAPI(
    title="RTI Intelligence System — PIO Backend API",
    description="FastAPI service serving the 5-Agent RTI pipeline and SQLite audit logging",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Global local-first memory cache for the active session (since it is a desktop local dashboard)
LAST_RAW_TEXT = ""
LAST_LANGUAGE = "en"


# ---------------------------------------------------------------------------
# API Request & Response Schemas
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    text: str
    language: str


class ExtractRequest(BaseModel):
    text: str


class ExtractedInformationReact(BaseModel):
    classification_type: str
    entities: List[str]
    systems: List[str]
    procurement_status: str
    personal_data: bool
    public_interest: bool
    explanation: str


class RoutingResultReact(BaseModel):
    primary_department: str
    confidence: str
    reasoning: str
    alternatives: List[str]
    transfer_applicable: Optional[bool] = False


class ExemptionFlagReact(BaseModel):
    section: str
    title: str
    reasoning: str
    suggested_action: str
    is_overridden: bool
    override_reason: Optional[str] = None


class StatutoryReferenceReact(BaseModel):
    section: str
    title: str
    is_applicable: bool
    confidence_score: float
    legal_reasoning: str
    exact_quotes: List[str]


class BalancerOutputReact(BaseModel):
    pro_disclosure_argument: str
    pro_exemption_argument: str
    balancing_factors: str


class RecommendationReact(BaseModel):
    action: str
    confidence: str
    reasoning: str
    citations: List[str]
    timeline: str


class EvaluationResultReact(BaseModel):
    exemption_flags: List[ExemptionFlagReact]
    layer_b_res: List[StatutoryReferenceReact]
    balance_res: BalancerOutputReact
    final_recom: RecommendationReact


class AuditRecordReact(BaseModel):
    audit_id: Optional[str] = None
    pio_action_taken: str
    override_department: Optional[str] = ""
    reasoning_notes: str
    extracted_info: ExtractedInformationReact
    routing: RoutingResultReact
    evaluation: EvaluationResultReact



class GenerateDraftRequest(BaseModel):
    routing: RoutingResultReact
    confirmed_info: ExtractedInformationReact
    exemption_flags: List[ExemptionFlagReact]
    layer_b_res: List[StatutoryReferenceReact]
    balance_res: BalancerOutputReact
    final_recom: RecommendationReact
    department: str
    is_chips: bool


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_endpoint():
    """Simple status check."""
    return {"status": "ok", "app": "RTI PIO API Server"}



class FastAPIUploadFileWrapper:
    def __init__(self, upload_file: UploadFile):
        self.upload_file = upload_file
        self.name = upload_file.filename

    def read(self, *args, **kwargs):
        return self.upload_file.file.read(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self.upload_file.file.seek(*args, **kwargs)


@app.post("/api/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    """Process uploaded PDF or Image file through OCR/text extraction."""
    global LAST_RAW_TEXT, LAST_LANGUAGE
    
    try:
        # Wrap the FastAPI UploadFile to match the interface expected by parse_uploaded_file
        wrapped_file = FastAPIUploadFileWrapper(file)
        
        # Parse document using the unified document_parser
        result = parse_uploaded_file(wrapped_file)
        
        # Update session memory cache
        LAST_RAW_TEXT = result.text
        LAST_LANGUAGE = result.language_detected
        
        # Package warning if present
        warnings_list = [result.warning] if result.warning else []
        
        return {
            "text": result.text,
            "confidence": result.ocr_confidence,
            "language": result.language_detected,
            "warnings": warnings_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR execution failed: {str(e)}")


@app.post("/api/route")
async def route_endpoint(req: RouteRequest):
    """Classify the query into the appropriate Chhattisgarh government department."""
    global LAST_RAW_TEXT, LAST_LANGUAGE
    try:
        # Cache raw context if not already done
        if not LAST_RAW_TEXT:
            LAST_RAW_TEXT = req.text
            LAST_LANGUAGE = req.language
            
        routing_res = classify_department(req.text, req.language)
        
        # Map alternatives from list of objects to list of strings
        alternatives = [alt.department_name for alt in routing_res.alternative_departments]
        
        return {
            "primary_department": routing_res.primary_department,
            "confidence": routing_res.confidence_band,
            "reasoning": routing_res.reasoning,
            "alternatives": alternatives,
            "transfer_applicable": routing_res.transfer_applicable
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing classification failed: {str(e)}")


@app.post("/api/extract")
async def extract_endpoint(req: ExtractRequest):
    """Perform parameter classification and entity extraction using local LLM."""
    global LAST_RAW_TEXT
    try:
        if not LAST_RAW_TEXT:
            LAST_RAW_TEXT = req.text
            
        extracted = extract_information(req.text)
        
        return {
            "classification_type": extracted.information_type,
            "entities": extracted.extracted_entities,
            "systems": extracted.systems,
            "procurement_status": extracted.procurement_status,
            "personal_data": extracted.personal_data,
            "public_interest": extracted.public_interest_override,
            "explanation": extracted.explanation
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structured parameter extraction failed: {str(e)}")


@app.post("/api/evaluate_exemptions")
async def evaluate_exemptions_endpoint(req: ExtractedInformationReact):
    """Run statutory rules, LLM analyses, balanced arguments, and synthesis compiler."""
    try:
        # Reconstruct Python's ExtractedInformation object
        from extractor import ExtractedInformation as PythonExtractedInformation
        
        info = PythonExtractedInformation(
            extracted_entities=req.entities,
            information_type=req.classification_type,
            systems=req.systems,
            procurement_status=req.procurement_status,
            personal_data=req.personal_data,
            public_interest_override=req.public_interest,
            explanation=req.explanation
        )
        
        # Obtain query text
        text_query = LAST_RAW_TEXT
        if not text_query:
            # Heuristic reconstruction if raw cache is missing
            text_query = (
                f"RTI query regarding classification: {req.classification_type}. "
                f"IT Systems: {', '.join(req.systems)}. "
                f"Key Entities: {', '.join(req.entities)}. "
                f"Context reasoning notes: {req.explanation}"
            )
            
        # 1. Deterministic Rule evaluation (Layer A)
        exemption_flags = evaluate_exemptions(info)
        rule_flags = [flag.section for flag in exemption_flags]
        
        # 2. LLM RAG statutory analysis (Layer B)
        layer_b_res = analyze_exemption_applicability(text_query, rule_flags)
        
        # 3. Side-by-side disclosure balancer (Agent 4)
        balance_res = compute_disclosure_balance(text_query, rule_flags)
        
        # 4. Generate synthesis recommendation (Agent 5)
        # Fetch current routing details to check for transfers
        routing_res = classify_department(text_query, LAST_LANGUAGE)
        final_recom = generate_final_recommendation(text_query, routing_res, info, layer_b_res, balance_res)
        
        # Map the outputs to React schemas
        flags_mapped = [
            {
                "section": flag.section,
                "title": flag.title,
                "reasoning": flag.reasoning,
                "suggested_action": flag.suggested_action,
                "is_overridden": flag.is_overridden,
                "override_reason": flag.override_reason
            }
            for flag in exemption_flags
        ]
        
        references_mapped = [
            {
                "section": ref.section,
                "title": SECTIONS_MAP.get(ref.section, "Statutory Exemption Clause"),
                "is_applicable": ref.is_applicable,
                "confidence_score": ref.confidence_score,
                "legal_reasoning": ref.legal_reasoning,
                "exact_quotes": ref.exact_quotes
            }
            for ref in layer_b_res.exemptions_analysis
        ]
        
        balancer_mapped = {
            "pro_disclosure_argument": balance_res.pro_disclosure_argument,
            "pro_exemption_argument": balance_res.pro_exemption_argument,
            "balancing_factors": balance_res.balancing_factors
        }
        
        recommendation_mapped = {
            "action": final_recom.recommendation,
            "confidence": final_recom.confidence_band,
            "reasoning": final_recom.primary_reasoning,
            "citations": final_recom.sections_applied,
            "timeline": final_recom.suggested_pio_action
        }
        
        return {
            "exemption_flags": flags_mapped,
            "layer_b_res": references_mapped,
            "balance_res": balancer_mapped,
            "final_recom": recommendation_mapped
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rules execution / synthesis evaluation failed: {str(e)}")


@app.post("/api/log_decision")
async def log_decision_endpoint(req: AuditRecordReact):
    """Log the PIO's final verified decision to the SQLite database and SHA-256 hash chain."""
    if req.audit_id:
        existing = get_record(req.audit_id)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"A decision for Case ID '{req.audit_id}' has already been registered in the database. Please generate a new Case ID to log this decision."
            )
    try:
        rule_flags = [flag.section for flag in req.evaluation.exemption_flags]
        
        # Build flat record matching python database schema
        py_record = PythonAuditRecord(
            audit_id=req.audit_id or str(uuid.uuid4()),
            raw_input_text=LAST_RAW_TEXT or f"RTI regarding classification: {req.extracted_info.classification_type}",
            extracted_text_ocr=LAST_RAW_TEXT or "",
            ocr_confidence=1.0,
            language_detected=LAST_LANGUAGE or "en",
            system_recommended_department=req.routing.primary_department,
            system_confidence_band=req.routing.confidence,
            system_reasoning=req.routing.reasoning,
            alternative_departments=req.routing.alternatives,
            extracted_entities=req.extracted_info.entities,
            information_type=req.extracted_info.classification_type,
            rule_engine_flags=rule_flags,
            pio_exemption_override=req.reasoning_notes if req.pio_action_taken == "OVERRIDDEN" or len(rule_flags) > 0 else None,
            pio_action_taken=req.pio_action_taken,
            pio_override_department=req.override_department or "",
            pio_comments=req.reasoning_notes,
            legal_disclaimer_accepted=True,
            previous_hash="",
            current_hash=""
        )
        
        # Save record and generate cryptographically chained hash values
        audit_id = log_analysis(py_record)
        
        saved_record = get_record(audit_id)
        if not saved_record:
            raise HTTPException(status_code=500, detail="Decision logged but failed to retrieve record hash verification.")
            
        # Return matched React structure back to React frontend
        return {
            "audit_id": saved_record.audit_id,
            "timestamp": saved_record.timestamp,
            "pio_action_taken": saved_record.pio_action_taken,
            "override_department": saved_record.pio_override_department,
            "reasoning_notes": saved_record.pio_comments,
            "extracted_info": req.extracted_info,
            "routing": req.routing,
            "evaluation": req.evaluation,
            "current_hash": saved_record.current_hash
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decision logging audit error: {str(e)}")

@app.get("/api/audit_trail")
async def audit_trail_endpoint(limit: int = 100):
    """Return recent audit records and hash chain validation status."""
    try:
        records = get_audit_trail(limit=limit)
        records_data = [rec.dict() for rec in records]
        chain_valid, _ = verify_chain()
        return {"records": records_data, "chain_valid": chain_valid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit trail retrieval failed: {str(e)}")

@app.get("/api/system_status")
async def system_status_endpoint():
    """Return status of database, Ollama, and OCR engines."""
    try:
        # Database status
        db_path = str(DB_PATH)
        conn_ok = False
        record_count = 0
        try:
            with _get_connection() as conn:
                conn_ok = True
                record_count = conn.execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
        except Exception:
            conn_ok = False

        # Ollama status
        ollama_reachable = False
        ollama_models = []
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                ollama_reachable = True
                data = resp.json()
                ollama_models = [model["name"] for model in data.get("models", [])]
        except Exception:
            ollama_reachable = False

        # OCR engine status
        pdfplumber_available = False
        pytesseract_available = False
        try:
            import pdfplumber
            pdfplumber_available = True
        except Exception:
            pdfplumber_available = False
        try:
            import pytesseract
            pytesseract_available = True
        except Exception:
            pytesseract_available = False

        return {
            "database": {"path": db_path, "connected": conn_ok, "record_count": record_count},
            "ollama": {"reachable": ollama_reachable, "models": ollama_models},
            "ocr": {"pdfplumber": pdfplumber_available, "pytesseract": pytesseract_available},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"System status check failed: {str(e)}")


@app.get("/api/legal_sections")
async def legal_sections_endpoint():
    """Load legal sections from data/legal_sections.json or fallback to hardcoded."""
    json_path = Path(__file__).resolve().parent.parent / "data" / "legal_sections.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            pass
    from legal_sections import get_hardcoded_sections
    return get_hardcoded_sections()


@app.post("/api/generate_draft")
async def generate_draft_endpoint(req: GenerateDraftRequest):
    """Generate a draft response letter using Sarvam AI, with a template fallback."""
    try:
        department = req.department
        is_chips = req.is_chips
        
        # Serialize objects for prompt context
        routing_dict = req.routing.dict()
        confirmed_info_dict = req.confirmed_info.dict()
        layer_b_dict = [ref.dict() for ref in req.layer_b_res]
        balance_dict = req.balance_res.dict()
        final_recom_dict = req.final_recom.dict()
        
        flags_list = []
        for flag in req.exemption_flags:
            flags_list.append({
                "section": flag.section,
                "title": flag.title,
                "reasoning": flag.reasoning,
                "is_overridden": flag.is_overridden,
                "override_reason": flag.override_reason or ""
            })
            
        if not is_chips:
            prompt = f"""You are a drafting assistant for a Public Information Officer (PIO) at Chhattisgarh Infotech Promotion Society (CHiPS), Raipur, Chhattisgarh.
Draft a concise, formal, and legally correct Section 6(3) Transfer Directive in English.

The transfer directive note should:
1. State that on examination of the RTI application, the subject matter falls outside the jurisdiction of CHiPS.
2. Specifically note that the application relates to {department} (for example, if it concerns citizen data/portals not legally owned by CHiPS).
3. State that the application is being transferred to the PIO of {department} under Section 6(3) of the RTI Act 2005.
4. Instruct that the information should be provided directly to the applicant by the transferee department.
5. Sound like an official government internal note / order sheet.
6. Be 100-180 words maximum.
7. Start exactly with: "On examination of the RTI application:"

---
RTI DATA:
- Target Department: {department}
- System recommendation reasoning: {routing_dict.get('reasoning')}
- RTI text snippet: {LAST_RAW_TEXT[:300]}...
---
"""
        else:
            prompt = f"""You are an expert drafting assistant for a Public Information Officer (PIO) at Chhattisgarh Infotech Promotion Society (CHiPS), Raipur, Chhattisgarh.
Draft a professional, authoritative, and concise internal decision note in English based on the legal analysis and parameters below.

The note MUST:
1. State the jurisdiction determination: confirm that the subject matter falls within the jurisdiction of CHiPS.
2. Summarize the information requested (referencing systems: {confirmed_info_dict.get('systems', [])}, entities: {confirmed_info_dict.get('entities', [])}).
3. State the recommended decision (Approve, Reject, or Partially Approve) and cite the exact statutory sections applied (e.g. Section 8(1)(d) for commercial confidence, Section 8(1)(j) for personal privacy, or Section 10 for severability and partial disclosure).
4. Provide the exact legal/factual basis: summarize why the exemption applies or doesn't apply based on the facts (mentioning private data concerns or public interest override allegations, if any).
5. Sound like an official government internal note / order sheet, using formal, objective, and legally precise language.
6. Be 150-250 words maximum.
7. Start exactly with: "On examination of the RTI application:"

---
LEGAL ANALYSIS CONTEXT:
- Information Classification Type: {confirmed_info_dict.get('classification_type')}
- IT Systems: {confirmed_info_dict.get('systems')}
- Entities: {confirmed_info_dict.get('entities')}
- Procurement Status: {confirmed_info_dict.get('procurement_status')}
- Personal Data Present: {confirmed_info_dict.get('personal_data')}
- Public Interest Override Alleged: {confirmed_info_dict.get('public_interest')}
- Flagged Exemption Flags (Layer A): {json.dumps(flags_list, ensure_ascii=False)}
- Exemption Applicability Analysis (Layer B): {json.dumps(layer_b_dict, ensure_ascii=False)}
- Pro-Disclosure Arguments: {balance_dict.get('pro_disclosure_argument')}
- Pro-Exemption Arguments: {balance_dict.get('pro_exemption_argument')}
- Key Balancing Factors: {balance_dict.get('balancing_factors')}
- Final Synthesized Recommendation: {final_recom_dict.get('action')}
- Primary Recommendation Reasoning: {final_recom_dict.get('reasoning')}
- Suggested Action: {final_recom_dict.get('timeline')}
- Sections Cited: {final_recom_dict.get('citations')}
---
"""
        
        try:
            from sarvam_client import call_sarvam_chat
            content = call_sarvam_chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return {"draft": content}
        except Exception as e:
            # Fallback
            if not is_chips:
                fallback = f"On examination of the RTI application:\nThe application relates to the jurisdiction of {department}, not CHiPS. Recommended action: Transfer to the concerned department under Section 6(3) of the RTI Act, 2005 within 5 days of receipt."
            else:
                exempt_sections = [flag.section for flag in req.exemption_flags]
                info_type = confirmed_info_dict.get('classification_type', 'other')
                if exempt_sections:
                    fallback = f"On examination of the RTI application:\nThe information requested pertains to CHiPS but involves {info_type} details. This information is exempt from disclosure under {', '.join(exempt_sections)} of the RTI Act, 2005. Recommended action: Reject the request point-wise, specifying the exemption clauses."
                else:
                    fallback = f"On examination of the RTI application:\nThe information requested falls within the jurisdiction of CHiPS and does not trigger any exemptions. Recommended action: Approve the request and disclose the records."
            return {"draft": fallback, "warning": "Sarvam AI is offline. A heuristic template draft was generated."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {str(e)}")


class DictNamespace:
    def __init__(self, d):
        self._d = d
        for k, v in d.items():
            if isinstance(v, dict):
                setattr(self, k, DictNamespace(v))
            elif isinstance(v, list):
                setattr(self, k, [DictNamespace(i) if isinstance(i, dict) else i for i in v])
            else:
                setattr(self, k, v)

    def get(self, key, default=None):
        val = self._d.get(key, default)
        if isinstance(val, dict):
            return DictNamespace(val)
        if isinstance(val, list):
            return [DictNamespace(i) if isinstance(i, dict) else i for i in val]
        return val

    def __getitem__(self, key):
        val = self._d[key]
        if isinstance(val, dict):
            return DictNamespace(val)
        if isinstance(val, list):
            return [DictNamespace(i) if isinstance(i, dict) else i for i in val]
        return val

    def __contains__(self, key):
        return key in self._d


class DownloadRequest(BaseModel):
    raw_text: str
    logged_record: AuditRecordReact


def build_session_state(req: DownloadRequest) -> dict:
    record = req.logged_record
    
    decision_map = {
        "APPROVED": "Approve — Full Disclosure",
        "PARTIALLY_APPROVE": "Partially Approve — Partial Disclosure",
        "REJECTED": "Reject — Exempt",
        "TRANSFER": "Transfer — Section 6(3)",
        "PENDING": "Pending — Further Review",
        "OVERRIDDEN": "Overridden"
    }
    final_decision_value = decision_map.get(record.pio_action_taken, record.pio_action_taken)
    
    info_dict = {
        "information_type": record.extracted_info.classification_type,
        "classification_type": record.extracted_info.classification_type,
        "procurement_status": record.extracted_info.procurement_status,
        "personal_data": record.extracted_info.personal_data,
        "public_interest_override": record.extracted_info.public_interest,
        "public_interest": record.extracted_info.public_interest,
        "extracted_entities": record.extracted_info.entities,
        "entities": record.extracted_info.entities,
        "systems": record.extracted_info.systems,
        "explanation": record.extracted_info.explanation
    }
    
    routing_dict = {
        "primary_department": record.routing.primary_department,
        "department": record.routing.primary_department,
        "department_name": record.routing.primary_department,
        "confidence": record.routing.confidence,
        "confidence_band": record.routing.confidence,
        "reasoning": record.routing.reasoning,
        "section_reference": "",
        "alternatives": record.routing.alternatives,
        "transfer_applicable": record.routing.transfer_applicable
    }
    
    recom_dict = {
        "action": record.evaluation.final_recom.action,
        "recommendation": record.evaluation.final_recom.action,
        "confidence": record.evaluation.final_recom.confidence,
        "confidence_band": record.evaluation.final_recom.confidence,
        "reasoning": record.evaluation.final_recom.reasoning,
        "primary_reasoning": record.evaluation.final_recom.reasoning,
        "citations": record.evaluation.final_recom.citations,
        "sections_applied": record.evaluation.final_recom.citations,
        "statutory_citations_applied": record.evaluation.final_recom.citations,
        "timeline": record.evaluation.final_recom.timeline,
        "suggested_pio_action": record.evaluation.final_recom.timeline,
        "rejection_risk": None,
        "disclosure_risk": None
    }
    
    ex_flags_list = []
    for flag in record.evaluation.exemption_flags:
        ex_flags_list.append({
            "section": flag.section,
            "title": flag.title,
            "reasoning": flag.reasoning,
            "suggested_action": flag.suggested_action,
            "is_overridden": flag.is_overridden,
            "override_reason": flag.override_reason or ""
        })
        
    layer_b_list = []
    for ref in record.evaluation.layer_b_res:
        layer_b_list.append({
            "section": ref.section,
            "title": ref.title,
            "is_applicable": ref.is_applicable,
            "confidence_score": ref.confidence_score,
            "legal_reasoning": ref.legal_reasoning,
            "exact_quotes": ref.exact_quotes
        })
    layer_b_dict = {
        "exemptions_analysis": layer_b_list,
        "overall_explanation": ""
    }
    
    balance_dict = {
        "pro_disclosure_argument": record.evaluation.balance_res.pro_disclosure_argument,
        "pro_exemption_argument": record.evaluation.balance_res.pro_exemption_argument,
        "balancing_factors": record.evaluation.balance_res.balancing_factors
    }
    
    session_state = {
        "case_id": record.audit_id or "N/A",
        "rti_text": req.raw_text,
        "extracted_text": req.raw_text,
        "language": "en",
        "ocr_confidence": 1.0,
        "routing_result": DictNamespace(routing_dict),
        "effective_department": record.override_department if record.pio_action_taken == "TRANSFER" else record.routing.primary_department,
        "is_chips_jurisdiction": record.routing.primary_department == "chips",
        "confirmed_info": DictNamespace(info_dict),
        "extracted_info": DictNamespace(info_dict),
        "exemption_flags": [DictNamespace(f) for f in ex_flags_list],
        "layer_b_res": DictNamespace(layer_b_dict),
        "balance_res": DictNamespace(balance_dict),
        "final_recom": DictNamespace(recom_dict),
        "final_decision_value": final_decision_value,
        "pio_decision_text": record.reasoning_notes,
        "pio_routing_override": record.override_department if record.override_department else None,
        "routing_correction_reason": record.reasoning_notes,
        "logged_audit_id": record.audit_id or ""
    }
    
    return session_state


from fastapi.responses import Response
from export_report import generate_analysis_docx, DOCX_AVAILABLE as EXPORT_DOCX_AVAILABLE
from response_letter import generate_response_letter, DOCX_AVAILABLE as LETTER_DOCX_AVAILABLE


@app.post("/api/download_analysis")
async def download_analysis_endpoint(req: DownloadRequest):
    try:
        session_state = build_session_state(req)
        docx_bytes = generate_analysis_docx(session_state)
        
        ext = "docx" if EXPORT_DOCX_AVAILABLE else "txt"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if EXPORT_DOCX_AVAILABLE else "text/plain"
        filename = f"RTI_Analysis_{session_state.get('case_id', 'report').replace('/', '_')}.{ext}"
        
        return Response(
            content=docx_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation of analysis report failed: {str(e)}")


@app.post("/api/download_response")
async def download_response_endpoint(req: DownloadRequest):
    try:
        session_state = build_session_state(req)
        docx_bytes = generate_response_letter(session_state)
        
        ext = "docx" if LETTER_DOCX_AVAILABLE else "txt"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if LETTER_DOCX_AVAILABLE else "text/plain"
        filename = f"RTI_Response_Letter_{session_state.get('case_id', 'report').replace('/', '_')}.{ext}"
        
        return Response(
            content=docx_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation of response letter failed: {str(e)}")


