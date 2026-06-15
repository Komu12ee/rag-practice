"""
Information Extractor (Agent 2) for RTI Intelligence System.

Extracts structured metadata from RTI application text using a local LLM
(qwen2.5:3b) with strict Pydantic parsing and validation.
"""

import json
import logging
import re
from typing import List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Sarvam AI API Configuration
# ---------------------------------------------------------------------------
from sarvam_client import call_sarvam_chat, SARVAM_API_KEY


def _check_ollama_server() -> bool:
    """Return True if the Ollama server is reachable."""
    if not _OLLAMA_AVAILABLE:
        return False
    try:
        _ollama_client.list()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pydantic Model for Structured Extraction
# ---------------------------------------------------------------------------
class ExtractedInformation(BaseModel):
    """Structured information extracted from RTI text by Agent 2.
    
    This classification determines the legal path for exemption analysis.
    """

    extracted_entities: List[str] = Field(
        default_factory=list,
        description="Key entities mentioned in the request (e.g. names of individuals, specific documents, file reference numbers)."
    )
    information_type: str = Field(
        default="other",
        description="Classification of the information. Must be one of: citizen_data, internal, confidential, architecture, procurement, employee, cybersecurity, third_party_commercial, other."
    )
    systems: List[str] = Field(
        default_factory=list,
        description="Names of any specific IT systems, portals, databases, or software networks referenced (e.g., e-District portal, PMGSY road portal, Core Network Router, HRMS database)."
    )
    procurement_status: str = Field(
        default="none",
        description="Status of any commercial procurement or government tender mentioned. Must be one of: active_tender, completed_tender, none."
    )
    personal_data: bool = Field(
        default=False,
        description="True if the request asks for personal details, private files, service records, medical files, or personal information of specific citizens or employees."
    )
    public_interest_override: bool = Field(
        default=False,
        description="True if the RTI request explicitly makes allegations of corruption or human rights violations (triggers Section 8(2) or Section 24 override)."
    )
    explanation: str = Field(
        default="No explanation provided.",
        description="A concise reason/justification for the classification and extraction."
    )


def _clean_json_response(raw: str) -> str:
    """Extract and clean outer JSON string from LLM responses."""
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*$", "", raw)
    raw = raw.strip()
    raw = re.sub(r",\s*([\]}])", r"\1", raw)
    return raw


# ---------------------------------------------------------------------------
# Core Extraction logic
# ---------------------------------------------------------------------------
def extract_information(text: str) -> ExtractedInformation:
    """Extract structured information from the RTI text.
    
    Uses Ollama's qwen2.5:3b model with a JSON formatting constraint.
    If Ollama is not available or the LLM output is malformed,
    it falls back to basic heuristic rules.
    """
    if not text or not text.strip():
        return ExtractedInformation(
            extracted_entities=[],
            information_type="other",
            systems=[],
            procurement_status="none",
            personal_data=False,
            public_interest_override=False,
            explanation="Empty RTI text provided."
        )

    if not SARVAM_API_KEY:
        print("[extractor.py] Sarvam API Key not found. Falling back to heuristics.")
        logger.warning("Sarvam API Key not found. Running heuristic fallback extractor.")
        return _heuristic_extract(text)

    # Construct the instruction prompt
    prompt = f"""You are an expert legal information extraction assistant for the RTI (Right to Information) Act processing system.
Your task is to analyze the provided RTI application text and extract structured metadata in JSON format.

─────────────────────────────────────────────
INFORMATION TYPE DEFINITIONS
─────────────────────────────────────────────
Here are the definitions of categories for 'information_type':
- `citizen_data`: Private or personal records of a specific citizen (e.g., land maps, certificates, personal grievances).
- `employee`: Personnel records, service files, salary slips, or service history of specific government employees.
- `procurement`: Information regarding tenders, bidding, vendor selections, contracts, or government purchases.
- `cybersecurity`: IT network designs, router configuration, firewall logs, system passwords, encryption keys, IP addresses, cybersecurity audit logs.
- `architecture`: System technical design, source code, server hardware specs, database schemas, code modules.
- `internal`: Routine administrative notes, file sheets, office memos, draft policies, internal correspondence.
- `confidential`: Sensitive government deliberations, high-level policy plans, cabinet notes, state security matters.
- `third_party_commercial`: Trade secrets, patent submissions, proprietary commercial details, or pricing tables submitted by private vendors in confidence.
- `other`: General public notifications, public statistics, generic project updates, guidelines, or non-sensitive general queries.

─────────────────────────────────────────────
RTI APPLICATION TEXT
─────────────────────────────────────────────
{text[:2500]}

─────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────
Provide your output ONLY as a JSON object matching this schema:
{{
  "extracted_entities": ["list", "of", "entities"],
  "information_type": "one of the 9 types listed above",
  "systems": ["list", "of", "systems"],
  "procurement_status": "active_tender | completed_tender | none",
  "personal_data": true | false,
  "public_interest_override": true | false,
  "explanation": "short reasoning text"
}}

Ensure all keys and string values are properly enclosed in double quotes.
Ensure there is absolutely NO conversational preamble, NO thought process, NO explanation, NO reconsiderations, and NO other text before or after the JSON block. Start directly with '{{' and end with '}}'.
"""

    try:
        print("[extractor.py] Invoking Sarvam AI for entity and metadata extraction...")
        content = call_sarvam_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        try:
            print(f"[extractor.py] Sarvam AI response content length: {len(content)}")
            logger.debug(f"Sarvam AI response content:\n{content}")
        except Exception:
            pass
        
        # Clean and parse JSON
        cleaned_content = _clean_json_response(content)
        parsed = json.loads(cleaned_content)
        
        # Clean/sanitize output values to ensure they conform to valid choices
        valid_types = {
            "citizen_data", "internal", "confidential", "architecture",
            "procurement", "employee", "cybersecurity", "third_party_commercial", "other"
        }
        if parsed.get("information_type") not in valid_types:
            # Try fuzzy matching or default to other
            pt = str(parsed.get("information_type", "")).lower()
            found = False
            for vt in valid_types:
                if vt in pt or pt in vt:
                    parsed["information_type"] = vt
                    found = True
                    break
            if not found:
                parsed["information_type"] = "other"

        valid_proc_statuses = {"active_tender", "completed_tender", "none"}
        if parsed.get("procurement_status") not in valid_proc_statuses:
            parsed["procurement_status"] = "none"

        # Validate with Pydantic
        return ExtractedInformation(**parsed)

    except Exception as exc:
        logger.error(f"Error during LLM extraction: {exc}. Falling back to heuristics.")
        return _heuristic_extract(text)


def _heuristic_extract(text: str) -> ExtractedInformation:
    """Fallback extractor using regex and keyword heuristic matching."""
    text_lower = text.lower()
    
    extracted_entities = []
    systems = []
    
    # Simple regex for entities/names (like IDs or dates)
    dates = re.findall(r"\b\d{2}[-/.]\d{2}[-/.]\d{4}\b", text)
    for d in dates:
        extracted_entities.append(f"Date: {d}")
        
    doc_nums = re.findall(r"\b(?:doc|id|ref|tender|file|no|no\.)[-:\s]*([a-z0-9/_-]+)\b", text_lower)
    for dn in doc_nums:
        if len(dn) > 4:
            extracted_entities.append(f"Ref Number: {dn}")

    # Heuristic systems
    system_keywords = ["e-district", "pmgsy", "hrms", "database", "portal", "website", "server", "router", "network"]
    for kw in system_keywords:
        if kw in text_lower:
            systems.append(kw.upper())
            
    # Classify information type
    info_type = "other"
    personal_data = False
    procurement_status = "none"
    public_interest_override = False

    # Check for cybersecurity keywords
    cyber_kws = ["firewall", "password", "credential", "ip address", "server config", "network security", "port scan", "cyber"]
    if any(k in text_lower for k in cyber_kws):
        info_type = "cybersecurity"
    # Check for procurement keywords
    elif any(k in text_lower for k in ["tender", "bid", "quotation", "procurement", "purchase order", "contractor"]):
        info_type = "procurement"
        if any(k in text_lower for k in ["active", "ongoing", "live", "advertised", "not open"]):
            procurement_status = "active_tender"
        else:
            procurement_status = "completed_tender"
    # Check for architecture keywords
    elif any(k in text_lower for k in ["source code", "architecture diagram", "database schema", "system design", "software code"]):
        info_type = "architecture"
    # Check for employee keywords
    elif any(k in text_lower for k in ["service book", "salary slip", "leave record", "performance report", "pension file", "employee"]):
        info_type = "employee"
        personal_data = True
    # Check for citizen data
    elif any(k in text_lower for k in ["land record", "caste certificate", "ration card", "grievance details", "my application", "birth certificate"]):
        info_type = "citizen_data"
        personal_data = True
    # Check for confidential
    elif any(k in text_lower for k in ["cabinet note", "state security", "confidential minutes", "secret"]):
        info_type = "confidential"
    # Check for internal
    elif any(k in text_lower for k in ["file sheet", "noting", "office memo", "internal circular"]):
        info_type = "internal"
    # Check for third-party commercial
    elif any(k in text_lower for k in ["third party", "proprietary", "trade secret", "commercial confidence"]):
        info_type = "third_party_commercial"

    # Personal data check
    personal_kws = ["personal", "medical", "address", "phone number", "salary", "bank account", "aadhaar", "pan card"]
    if any(k in text_lower for k in personal_kws):
        personal_data = True

    # Corruption / Human Rights override check
    override_kws = ["corruption", "human rights", "violation", "bribe", "scam", "fraud", "scandal", "torture"]
    if any(k in text_lower for k in override_kws):
        public_interest_override = True

    explanation = (
        f"Heuristic classification: identified type as '{info_type}' "
        f"based on keyword matches. Personal data={personal_data}, "
        f"public interest={public_interest_override}."
    )

    return ExtractedInformation(
        extracted_entities=extracted_entities,
        information_type=info_type,
        systems=systems,
        procurement_status=procurement_status,
        personal_data=personal_data,
        public_interest_override=public_interest_override,
        explanation=explanation
    )
