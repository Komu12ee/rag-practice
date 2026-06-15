"""
3-Pass Jurisdiction Classification Engine for RTI Intelligence System.

Classifies RTI application text to the correct Chhattisgarh government
department using a progressive-confidence strategy:

    Pass 1 — Keyword matching  (fast, deterministic)
    Pass 2 — Embedding similarity via Ollama nomic-embed-text
    Pass 3 — LLM fallback via Ollama qwen2.5:3b  (only when MEDIUM confidence)

The module degrades gracefully when Ollama is unavailable, falling back to
keyword-only classification.  It never crashes.
"""

import hashlib
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sarvam_client import call_sarvam_chat, SARVAM_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR.parent / "data"
_DEPARTMENTS_FILE = _DATA_DIR / "departments.json"
_EMBEDDINGS_CACHE_FILE = _DATA_DIR / "dept_embeddings.json"

# ---------------------------------------------------------------------------
# Ollama availability probe
# ---------------------------------------------------------------------------
_OLLAMA_AVAILABLE: bool = False
try:
    import ollama as _ollama_client

    _OLLAMA_AVAILABLE = True
except ImportError:
    logger.warning(
        "ollama Python package not installed. "
        "Embedding and LLM passes will be disabled."
    )


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
# Pydantic Models
# ---------------------------------------------------------------------------
class AlternativeDepartment(BaseModel):
    """A runner-up department with its score."""

    department_id: str
    department_name: str
    score: float = Field(..., ge=0.0, le=1.0)


class RoutingResult(BaseModel):
    """Result of the 3-pass department classification.

    Attributes:
        primary_department:     Machine ID of the top department.
        department_name:        Human-readable name of the department.
        confidence_band:        'HIGH', 'MEDIUM', or 'LOW' — the ONLY value
                                shown to the PIO.
        confidence_score:       Internal numeric score (never shown to PIO).
        reasoning:              Explanation of how the department was chosen.
        alternative_departments: Runner-up departments (sorted by score desc).
        transfer_applicable:    True if the department is NOT CHiPS —
                                Section 6(3) transfer may apply.
        section_reference:      Relevant RTI Act section reference.
        requires_manual_review: True when confidence is LOW or overlap is
                                detected.
        overlap_risk:           True if top-2 scores are within 0.10.
        passes_used:            Which passes contributed ('keyword',
                                'embedding', 'llm').
    """

    primary_department: str
    department_name: str
    confidence_band: str = Field(
        ..., pattern=r"^(HIGH|MEDIUM|LOW)$",
        description="Confidence band — HIGH / MEDIUM / LOW."
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Internal score — never displayed to PIO."
    )
    reasoning: str
    alternative_departments: List[AlternativeDepartment] = Field(
        default_factory=list
    )
    transfer_applicable: bool = False
    section_reference: str = ""
    requires_manual_review: bool = False
    overlap_risk: bool = False
    passes_used: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routing Matrix
# ---------------------------------------------------------------------------
_ROUTING_MATRIX = {
  "CHIPS_CORE": {
    "platform_owner": "CHiPS",
    "record_owner": "CHiPS",
    "department": "Electronics and Information Technology",
    "records": [
      "HR files",
      "Recruitment records",
      "Payroll",
      "Contracts",
      "SLAs",
      "Audit reports",
      "Procurement files",
      "Server procurement",
      "Network infrastructure",
      "State Data Centre",
      "CG-SWAN",
      "RTI registers",
      "Project management records"
    ]
  },

  "eDistrict": {
    "platform_owner": "CHiPS",
    "record_owner": "Concerned Department",
    "department_mapping": {
      "Caste Certificate": "Revenue Department",
      "Income Certificate": "Revenue Department",
      "Domicile Certificate": "Revenue Department",
      "Land Mutation": "Revenue Department",
      "Birth Certificate": "Urban Administration / Local Body",
      "Death Certificate": "Urban Administration / Local Body",
      "Trade License": "Urban Administration",
      "Shop Registration": "Labour Department"
    },
    "CHIPS_owns": [
      "Application uptime logs",
      "Server logs",
      "SLA reports",
      "Application architecture",
      "Vendor contracts"
    ]
  },

  "SewaSetu": {
    "platform_owner": "CHiPS",
    "record_owner": "Concerned Department",
    "department_mapping": {
      "Pension": "Social Welfare Department",
      "Scholarship": "Education Department",
      "Ration Card": "Food Department",
      "Farmer Scheme": "Agriculture Department"
    },
    "CHIPS_owns": [
      "Portal architecture",
      "API integration records",
      "Application performance metrics",
      "Hosting records"
    ]
  },

  "UPAHAR": {
    "platform_owner": "CHiPS",
    "record_owner": "Revenue Department",
    "administrative_owner": "Directorate of Land Records",
    "CHIPS_owns": [
      "Software contracts",
      "Implementation reports",
      "Project files"
    ],
    "Revenue_owns": [
      "Land records",
      "Khasra",
      "B1",
      "Mutation records",
      "Crop records",
      "Land assessment"
    ]
  },

  "KhanijOnline": {
    "platform_owner": "CHiPS",
    "record_owner": "Mineral Resources Department",
    "administrative_owner": "Directorate of Geology and Mining",
    "CHIPS_owns": [
      "Source system contracts",
      "Hosting",
      "SLA",
      "Technical architecture"
    ],
    "Mining_owns": [
      "Mining permits",
      "Transit passes",
      "Royalty collection",
      "Lease approvals",
      "Inspection reports"
    ]
  },

  "DigitalDwaar": {
    "platform_owner": "CHiPS",
    "record_owner": "Source Department",
    "CHIPS_owns": [
      "API architecture",
      "Integration agreements",
      "Technical documents"
    ],
    "Department_owns": [
      "Actual citizen data",
      "Department records"
    ]
  },

  "eProcurement": {
    "platform_owner": "CHiPS",
    "record_owner": "Tendering Department",
    "CHIPS_owns": [
      "Platform operation",
      "System logs",
      "Vendor onboarding"
    ],
    "Department_owns": [
      "Tender files",
      "Bid evaluation",
      "Award decision",
      "Purchase approval"
    ]
  },

  "Aadhaar": {
    "platform_owner": "CHiPS",
    "record_owner_mapping": {
      "Aadhaar software infrastructure": "CHiPS",
      "Aadhaar enrolment records": "UIDAI",
      "Aadhaar card issuance": "UIDAI",
      "Aadhaar operator recruitment": "District Administration",
      "Aadhaar centre attendance": "District Administration",
      "Aadhaar centre salary records": "District Administration"
    }
  }
}


_chips_report_cache: Optional[str] = None


def _load_chips_report() -> str:
    """Load the CHiPS Research Report text.
    
    Tries to read the cached text file from scratch/chips_report.txt.
    If it doesn't exist, it reads the original CHiPS RTI & Research Report.docx
    using python-docx, extracts paragraphs, writes to scratch/chips_report.txt,
    and returns it.
    """
    global _chips_report_cache
    if _chips_report_cache is not None:
        return _chips_report_cache

    project_root = Path(__file__).resolve().parent.parent
    cache_path = project_root / "scratch" / "chips_report.txt"
    docx_path = project_root / "CHiPS RTI & Research Report.docx"

    # 1. Try reading the cached text file
    if cache_path.exists():
        try:
            text = cache_path.read_text(encoding="utf-8")
            _chips_report_cache = text.strip()
            return _chips_report_cache
        except Exception as e:
            logger.warning(f"Failed to read cached CHiPS report: {e}")

    # 2. Extract from DOCX
    if docx_path.exists():
        try:
            import docx
            doc = docx.Document(str(docx_path))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            
            # Cache it
            cache_path.parent.mkdir(exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            
            _chips_report_cache = text.strip()
            return _chips_report_cache
        except Exception as e:
            logger.warning(f"Failed to extract CHiPS report from DOCX: {e}")

    # 3. Fallback summary
    fallback = (
        "CHiPS (Chhattisgarh Infotech Promotion Society) is the nodal agency for IT in Chhattisgarh.\n"
        "Key Projects: e-District, UPAHAR, Khanij Online, Sewa Setu, e-Procurement, State Data Centre, CG-SWAN.\n"
        "Important rule: CHiPS implements the IT portals, but the actual data/certificates belong to respective departments.\n"
        "For example, e-District processes caste certificates, but the issuing authority is the Revenue Department.\n"
        "UPAHAR handles land records, but the owner is the Revenue Department (Land Records).\n"
        "Geology and Mining Department owns Khanij Online mining permits.\n"
        "RTI applications asking for delays in caste certificates, Aadhaar, land records, or mining permits should be transferred under Section 6(3) to the respective department, NOT CHiPS.\n"
        "CHiPS only handles queries about its own internal admin, finances, HR, server counts, and system integrator project SLAs/agreements."
    )
    _chips_report_cache = fallback
    return _chips_report_cache


# ---------------------------------------------------------------------------
# Department Data Loader
# ---------------------------------------------------------------------------
_departments_cache: Optional[List[Dict[str, Any]]] = None


def _load_departments() -> List[Dict[str, Any]]:
    """Load department definitions from *departments.json* (cached)."""
    global _departments_cache
    if _departments_cache is not None:
        return _departments_cache

    if not _DEPARTMENTS_FILE.exists():
        raise FileNotFoundError(
            f"departments.json not found at {_DEPARTMENTS_FILE}. "
            "Create it in the data/ directory."
        )

    with open(_DEPARTMENTS_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    # departments.json is a flat array, not wrapped in {"departments": [...]}
    if isinstance(data, list):
        _departments_cache = data
    else:
        _departments_cache = data.get("departments", [])
    return _departments_cache


# ---------------------------------------------------------------------------
# Text Tokenisation Helpers
# ---------------------------------------------------------------------------
_DEVANAGARI_WORD_RE = re.compile(r"[\u0900-\u097F]+")
_EN_WORD_RE = re.compile(r"[A-Za-z0-9\-]+")


def _tokenize(text: str) -> List[str]:
    """Tokenise *text* into lowercase words (Latin + Devanagari)."""
    en_tokens = [w.lower() for w in _EN_WORD_RE.findall(text)]
    hi_tokens = _DEVANAGARI_WORD_RE.findall(text)
    return en_tokens + hi_tokens


# ---------------------------------------------------------------------------
# Pass 1 — Keyword Matching
# ---------------------------------------------------------------------------
def _keyword_score(
    tokens: List[str], department: Dict[str, Any]
) -> Tuple[float, List[str]]:
    """Score a department against *tokens* using keyword matching.

    Returns (score_0_to_1, matched_keywords).
    """
    keywords_en = [k.lower() for k in department.get("keywords_en", [])]
    keywords_hi = department.get("keywords_hi", [])
    all_keywords = keywords_en + keywords_hi

    if not all_keywords:
        return 0.0, []

    matched: List[str] = []
    weighted_hits: float = 0.0

    token_set = set(tokens)
    token_text = " ".join(tokens)

    for kw in all_keywords:
        kw_lower = kw.lower() if kw.isascii() else kw
        if kw_lower in token_set:
            # Exact single-word match
            weighted_hits += 1.0
            matched.append(kw)
        elif len(kw_lower.split()) > 1 and kw_lower in token_text:
            # Multi-word keyword found as substring
            weighted_hits += 1.0
            matched.append(kw)
        elif any(kw_lower in tok for tok in token_set):
            # Partial match (keyword is substring of a token)
            weighted_hits += 0.5
            matched.append(f"{kw}(partial)")

    # Normalise using absolute match count rather than fraction.
    # This ensures 1-2 strong matches still produce a meaningful score
    # even for departments with 20+ keywords.
    if len(matched) == 0:
        return 0.0, matched

    # Check for department name mention (strong signal)
    dept_name_en = department.get("department_name_en", department.get("name_en", ""))
    dept_name_lower = dept_name_en.lower()
    dept_id = department.get("department_id", department.get("id", ""))
    dept_id_lower = dept_id.lower()
    if dept_id_lower and (dept_id_lower in token_set or dept_id_lower in token_text):
        weighted_hits += 3.0  # Strong boost for direct department name match
        matched.append(f"{dept_id_lower}(name)")

    # Scoring tiers based on absolute match count:
    # 1 match  → 0.40 base
    # 2 matches → 0.60 base
    # 3 matches → 0.75 base
    # 4+ matches → 0.85+ base (capped at 1.0)
    import math
    score = min(1.0, 0.25 + 0.20 * math.log2(1 + weighted_hits))
    return round(score, 4), matched


def _pass1_keyword(text: str) -> List[Dict[str, Any]]:
    """Run keyword matching on every department.

    Returns list of dicts: {dept, score, matched_keywords}, sorted desc.
    """
    departments = _load_departments()
    tokens = _tokenize(text)

    results: List[Dict[str, Any]] = []
    for dept in departments:
        score, matched = _keyword_score(tokens, dept)
        results.append(
            {"dept": dept, "score": score, "matched_keywords": matched}
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Pass 2 — Embedding Similarity
# ---------------------------------------------------------------------------
def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(text: str) -> Optional[List[float]]:
    """Get embedding from Ollama's nomic-embed-text model."""
    if not _OLLAMA_AVAILABLE:
        return None
    try:
        response = _ollama_client.embed(model="nomic-embed-text", input=text)
        # ollama.embed returns {"embeddings": [[...]]}
        embeddings = response.get("embeddings")
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        return None
    except Exception as exc:
        logger.warning(f"Ollama embedding call failed: {exc}")
        return None


def _load_or_compute_dept_embeddings() -> Optional[Dict[str, List[float]]]:
    """Load cached department embeddings or compute & cache them.

    Returns dict mapping dept_id → embedding vector, or None on failure.
    """
    # Try loading cache
    if _EMBEDDINGS_CACHE_FILE.exists():
        try:
            with open(_EMBEDDINGS_CACHE_FILE, "r", encoding="utf-8") as fh:
                cached = json.load(fh)

            # Validate: check that all current departments are present
            departments = _load_departments()
            dept_ids = {d.get("department_id", d.get("id")) for d in departments if d.get("department_id") or d.get("id")}
            if dept_ids.issubset(set(cached.keys())):
                logger.info("Loaded department embeddings from cache.")
                return cached
            else:
                logger.info(
                    "Cache is stale (missing departments). Recomputing."
                )
        except Exception:
            logger.warning("Failed to load embedding cache. Recomputing.")

    # Compute embeddings
    if not _check_ollama_server():
        logger.warning("Ollama server not reachable — skipping embeddings.")
        return None

    departments = _load_departments()
    embeddings: Dict[str, List[float]] = {}

    for dept in departments:
        # Build a rich text representation for embedding
        d_id = dept.get("department_id", dept.get("id", ""))
        dept_name = dept.get("department_name_en", dept.get('name_en', dept.get('name', d_id)))
        dept_desc = dept.get('jurisdiction_description', dept.get('description', ''))
        desc_text = (
            f"{dept_name}. {dept_desc} "
            f"Keywords: {', '.join(dept.get('keywords_en', []))}"
        )
        emb = _get_embedding(desc_text)
        if emb is None:
            logger.warning(
                f"Could not compute embedding for {d_id}. "
                "Aborting embedding pass."
            )
            return None
        embeddings[d_id] = emb

    # Cache to disk
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_EMBEDDINGS_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(embeddings, fh)
        logger.info(f"Department embeddings cached to {_EMBEDDINGS_CACHE_FILE}")
    except Exception as exc:
        logger.warning(f"Failed to cache embeddings: {exc}")

    return embeddings


def _pass2_embedding(
    text: str, keyword_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Refine keyword scores with embedding similarity.

    Combines keyword score (weight 0.4) and embedding similarity (weight 0.6).
    Falls back to keyword-only scores if embeddings are unavailable.
    """
    dept_embeddings = _load_or_compute_dept_embeddings()
    if dept_embeddings is None:
        logger.info("Embedding pass skipped — using keyword scores only.")
        return keyword_results

    query_emb = _get_embedding(text)
    if query_emb is None:
        logger.warning("Could not embed query text — using keyword scores.")
        return keyword_results

    KEYWORD_WEIGHT = 0.4
    EMBEDDING_WEIGHT = 0.6

    for entry in keyword_results:
        dept_id = entry["dept"].get("department_id", entry["dept"].get("id"))
        dept_emb = dept_embeddings.get(dept_id)
        if dept_emb is None:
            continue
        sim = _cosine_similarity(query_emb, dept_emb)
        # Normalise cosine similarity from [-1, 1] to [0, 1]
        sim_norm = (sim + 1.0) / 2.0
        combined = (
            KEYWORD_WEIGHT * entry["score"]
            + EMBEDDING_WEIGHT * sim_norm
        )
        entry["embedding_similarity"] = round(sim_norm, 4)
        entry["score"] = round(combined, 4)

    keyword_results.sort(key=lambda r: r["score"], reverse=True)
    return keyword_results


# ---------------------------------------------------------------------------
# Pass 3 — LLM Fallback
# ---------------------------------------------------------------------------
def _pass3_llm(text: str, current_top: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call Sarvam AI's model for tiebreaker reasoning (MEDIUM confidence only).

    Returns dict with 'department', 'reasoning', 'confidence' or None.
    """
    if not SARVAM_API_KEY:
        print("[routing.py - Pass 3] Sarvam API Key not found. Skipping LLM pass.")
        logger.info("Sarvam API Key not found. Skipping LLM pass.")
        return None

    print("[routing.py - Pass 3] Invoking Sarvam AI for routing tiebreaker...")
    departments = _load_departments()
    dept_list = ", ".join(
        f"{d.get('department_id', d.get('id'))} ({d.get('department_name_en', d.get('name_en', d.get('name', d.get('department_id', d.get('id')))))})" for d in departments
    )

    prompt = (
        "You are a government department routing assistant for Chhattisgarh, India.\n"
        "Given this RTI application text, determine which department should handle it.\n\n"
        f"Available departments: {dept_list}\n\n"
        f"RTI Text: {text[:2000]}\n\n"  # Truncate for context window safety
        'Respond ONLY in JSON: {"department": "dept_id", "reasoning": "...", "confidence": "HIGH/MEDIUM/LOW"}\n'
        "Do not include any other text."
    )

    try:
        content = call_sarvam_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        try:
            print(f"[routing.py - Pass 3] Sarvam AI response content length: {len(content)}")
            logger.debug(f"Sarvam AI response content:\n{content}")
        except Exception:
            pass

        # Try to extract JSON from the response
        json_match = re.search(r"\{[^}]+\}", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            print(f"[routing.py - Pass 3] Successfully parsed JSON: {parsed}")
            return parsed
        else:
            logger.warning(f"LLM response not valid JSON: {content[:200]}")
            print(f"[routing.py - Pass 3] Failed: LLM response not valid JSON")
            return None
    except Exception as exc:
        logger.warning(f"LLM call failed: {exc}")
        print(f"[routing.py - Pass 3] Exception occurred: {exc}")
        return None


# ---------------------------------------------------------------------------
# Confidence Band Logic
# ---------------------------------------------------------------------------
def _score_to_band(score: float) -> str:
    """Map a numeric score to a confidence band.

    > 0.90 → HIGH  (auto-route suggestion)
    0.70–0.90 → MEDIUM  (PIO review + optional LLM confirmation)
    < 0.70 → LOW  (mandatory manual review)
    """
    if score > 0.90:
        return "HIGH"
    elif score >= 0.70:
        return "MEDIUM"
    else:
        return "LOW"


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def classify_department(text: str, language: str = "en") -> RoutingResult:
    """Classify RTI application text to the appropriate government department.

    Uses Sarvam AI to classify the department using the CHiPS Research Report
    context and matches against departments in departments.json.
    Falls back to keyword-embedding matching on error.
    """
    if not text or not text.strip():
        return RoutingResult(
            primary_department="UNKNOWN",
            department_name="Unknown",
            confidence_band="LOW",
            confidence_score=0.0,
            reasoning="Empty or blank RTI text provided.",
            requires_manual_review=True,
            section_reference="",
            passes_used=[],
        )

    # 1. Try Sarvam AI classification first
    if SARVAM_API_KEY:
        try:
            print("[routing.py] Executing Sarvam AI department classification...")
            
            # Load departments
            departments = _load_departments()
            dept_lookup = {d.get("department_id", d.get("id")): d for d in departments}
            
            # Format list of departments as a compact dictionary string to save context tokens
            dept_list_items = []
            for d in departments:
                d_id = d.get("department_id", d.get("id"))
                d_name = d.get("department_name_en", d.get("name_en", d_id))
                dept_list_items.append(f'"{d_id}": "{d_name}"')
            formatted_depts = "{\n  " + ",\n  ".join(dept_list_items) + "\n}"
            
            # Compact routing matrix representation as requested
            routing_matrix_str = json.dumps(_ROUTING_MATRIX, indent=2)

            prompt = f"""You are a Senior RTI Jurisdiction Officer and Public Information Officer (PIO) Routing Assistant for Chhattisgarh Infotech Promotion Society (CHiPS).

Your responsibility is NOT to classify RTIs based on keywords.

Your responsibility is to determine:

1. Whether CHiPS is the lawful record-holding authority.
2. If CHiPS is not the record holder, identify the department/public authority that maintains the requested records.
3. Whether the RTI should be transferred under Section 6(3) of the RTI Act, 2005.

─────────────────────────────────────────────
LEGAL PRINCIPLE
─────────────────────────────────────────────

The correct authority is the authority that maintains, controls, creates, approves, or preserves the requested records.

The subject matter alone does NOT determine jurisdiction.

Always identify the record owner.

Examples:

Aadhaar software infrastructure
→ CHiPS

Aadhaar operator recruitment records
→ District Administration / Revenue Department

e-District software uptime reports
→ CHiPS

Caste certificate approval files
→ Revenue Department

Mining software platform maintenance
→ CHiPS

Mining permits, royalties, transit passes
→ Mineral Resources Department

Sewa Setu application source code
→ CHiPS

Beneficiary records submitted through Sewa Setu
→ Concerned Department

─────────────────────────────────────────────
CHIPS RECORD OWNERSHIP
─────────────────────────────────────────────

CHiPS owns records relating to:

1. CHiPS administration
2. CHiPS recruitment
3. CHiPS HR files
4. CHiPS salary records
5. CHiPS audits
6. CHiPS budget and finance
7. CHiPS tenders
8. CHiPS procurement
9. CHiPS work orders
10. CHiPS contracts
11. CHiPS SLA agreements
12. CHiPS project implementation files
13. State Data Centre infrastructure
14. CG-SWAN infrastructure
15. Server procurement
16. Data centre operations
17. Network management
18. Security audits
19. CHiPS RTI records
20. CHiPS project management records

─────────────────────────────────────────────
CHIPS DOES NOT OWN
─────────────────────────────────────────────

CHiPS generally does NOT own:

1. Caste certificates
2. Income certificates
3. Domicile certificates
4. Land ownership records
5. Mutation records
6. Revenue case files
7. Mining permits
8. Royalty collections
9. School records
10. Teacher appointments
11. Health records
12. Hospital records
13. Beneficiary records
14. Pension approvals
15. Scholarship approvals
16. Departmental recruitment files
17. District-level employee attendance records
18. Departmental salary disbursement records

Even when these services operate on a platform developed by CHiPS.

─────────────────────────────────────────────
COMPACT ROUTING MATRIX (KNOWLEDGE BASE)
─────────────────────────────────────────────
{routing_matrix_str}

─────────────────────────────────────────────
MANDATORY REASONING PROCESS
─────────────────────────────────────────────

STEP 1

Extract:

* Records requested
* Documents requested
* Offices mentioned
* Officials mentioned
* Schemes mentioned
* Platforms mentioned

STEP 2

Identify:

For each requested record determine:

* Who creates it?
* Who approves it?
* Who maintains it?
* Who stores it?

STEP 3

Determine:

Record Holding Authority

Examples:

Appointment order
→ Establishment Branch

Attendance register
→ Employer Office

Salary register
→ Accounts Branch

Certificate approval file
→ Issuing Department

Tender file
→ Procuring Department

STEP 4

Determine whether CHiPS is the lawful custodian.

STEP 5

If CHiPS is not the custodian:

Identify transfer department.

STEP 6

Score all candidate departments:

Record Ownership = 50%
Administrative Control = 30%
Statutory Authority = 20%

Select highest score.

─────────────────────────────────────────────
CRITICAL CONSTRAINT (MUST FOLLOW)
─────────────────────────────────────────────

The "primary_department" and all "department_id" entries in "alternative_departments" MUST be selected strictly from the keys in the AVAILABLE DEPARTMENTS section below (e.g., 'home_department', 'chips', 'general_administration_department', etc.). 

Do NOT return external agencies like 'UIDAI', 'UIDAI / Concerned Department', or 'District Administration' as the primary_department ID. If the record belongs to an external agency or is not within CHiPS, map it to the closest valid Chhattisgarh state department (e.g., map Aadhaar delivery delay to 'home_department' or 'general_administration_department').

─────────────────────────────────────────────
AVAILABLE DEPARTMENTS
─────────────────────────────────────────────
{formatted_depts}

─────────────────────────────────────────────
RTI APPLICATION
─────────────────────────────────────────────
{text[:3000]}

─────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────

Return ONLY valid JSON matching this schema:

{{
"belongs_to_chips": true,
"transfer_required": false,
"record_holding_authority": "CHiPS",
"primary_department": "chips",
"department_name": "Ministry of Information Technology(CHiPS)",
"confidence_score": 0.95,
"records_requested": [
  "State Data Centre inventory list"
],
"offices_identified": [
  "CHiPS Raipur Office"
],
"reasoning": [
  "Step 1: Extract records requested - State Data Centre physical equipment server inventory list.",
  "Step 2: Identify creator/maintainer - CHiPS physically maintains SDC hardware.",
  "Step 3: Record holding authority is CHiPS SDC Division.",
  "Step 4: CHiPS is the lawful custodian of its own physical data centre inventory.",
  "Step 5: No transfer is required.",
  "Step 6: Score candidate departments - CHiPS score is 1.0 (Record Ownership 50%, Admin Control 30%, Statutory Authority 20%)."
],
"alternative_departments": [
  {{
    "department_id": "electronics_and_information_technology",
    "department_name": "Electronics & Information Technology Department",
    "score": 0.80
  }}
]
}}
Ensure that the JSON is properly formatted, and there is absolutely no other text in the response.
"""
            
            content = call_sarvam_chat(messages=[{"role": "user", "content": prompt}], temperature=0.1)
            
            def _clean_json_response(raw: str) -> str:
                # Extract outer {...} using bracket matching
                start = raw.find('{')
                if start == -1:
                    return raw
                
                depth = 0
                in_string = False
                escape = False
                end_idx = -1
                
                for i in range(start, len(raw)):
                    char = raw[i]
                    if in_string:
                        if escape:
                            escape = False
                        elif char == '\\':
                            escape = True
                        elif char == '"':
                            in_string = False
                    else:
                        if char == '"':
                            in_string = True
                        elif char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                end_idx = i
                                break
                                
                if end_idx != -1:
                    raw = raw[start:end_idx+1]
                    
                # Remove markdown formats
                raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
                raw = re.sub(r"```\s*$", "", raw)
                raw = raw.strip()
                # Fix trailing commas
                raw = re.sub(r",\s*([\]}])", r"\1", raw)
                return raw
                
            # Parse JSON
            cleaned_content = _clean_json_response(content)
            parsed = json.loads(cleaned_content)
            
            primary_id = parsed.get("primary_department", "UNKNOWN")
            primary_name = parsed.get("department_name", "Unknown")
            score = parsed.get("confidence_score", 0.5)
            
            # Map score to band
            if score >= 0.8:
                band = "HIGH"
            elif score >= 0.5:
                band = "MEDIUM"
            else:
                band = "LOW"
                
            # Construct reasoning string by joining lists of steps
            reasoning_steps = parsed.get("reasoning", [])
            if isinstance(reasoning_steps, list):
                reasoning_str = " | ".join(str(step) for step in reasoning_steps if step)
            else:
                reasoning_str = str(reasoning_steps)
                
            # Add record holding authority information if present
            rec_auth = parsed.get("record_holding_authority", "")
            if rec_auth:
                reasoning_str = f"Record Holding Authority: {rec_auth} | " + reasoning_str
            
            # Sanitize and resolve primary ID
            if primary_id not in dept_lookup:
                # Case insensitive lookup
                found = False
                for d_id, d_data in dept_lookup.items():
                    if d_id.lower() == primary_id.lower():
                        primary_id = d_id
                        primary_name = d_data.get("department_name_en", primary_name)
                        found = True
                        break
                if not found:
                    primary_id = "chips"  # default fallback if completely unrecognized
                    primary_name = dept_lookup["chips"].get("department_name_en")
            
            # Sanitize alternatives
            alternatives = []
            for alt in parsed.get("alternative_departments", [])[:4]:
                alt_id = alt.get("department_id")
                alt_name = alt.get("department_name", alt_id)
                alt_score = alt.get("score", 0.0)
                
                if alt_id:
                    # Sanitize alternative ID
                    if alt_id not in dept_lookup:
                        for d_id, d_data in dept_lookup.items():
                            if d_id.lower() == alt_id.lower():
                                alt_id = d_id
                                alt_name = d_data.get("department_name_en", alt_name)
                                break
                    if alt_id in dept_lookup:
                        alternatives.append(
                            AlternativeDepartment(
                                department_id=alt_id,
                                department_name=alt_name,
                                score=alt_score
                            )
                        )
            
            belongs_to_chips = parsed.get("belongs_to_chips", True)
            transfer_required = parsed.get("transfer_required", False)
            
            # Reconcile primary_id and transfer status
            is_self = primary_id == "chips"
            transfer_applicable = not is_self or transfer_required
            
            section_ref = ""
            reasoning_list = [r.strip() for r in reasoning_str.split("|") if r.strip()]
            
            if transfer_applicable:
                section_ref = (
                    "Section 6(3) of RTI Act, 2005: Transfer of application to "
                    "concerned public authority within 5 days."
                )
                reasoning_list.append(
                    f"Transfer under Section 6(3) applicable — '{primary_id}' is not CHiPS."
                )
            else:
                reasoning_list.append("RTI is within CHiPS jurisdiction.")
            
            reasoning_str = " | ".join(reasoning_list)
            requires_review = band == "LOW" or (len(alternatives) > 0 and (score - alternatives[0].score) < 0.10)
            overlap_risk = len(alternatives) > 0 and (score - alternatives[0].score) < 0.10
            
            print(f"[routing.py] Sarvam AI classified primary: {primary_id} ({primary_name}) with {band} confidence.")
            
            return RoutingResult(
                primary_department=primary_id,
                department_name=primary_name,
                confidence_band=band,
                confidence_score=score,
                reasoning=reasoning_str,
                alternative_departments=alternatives,
                transfer_applicable=transfer_applicable,
                section_reference=section_ref,
                requires_manual_review=requires_review,
                overlap_risk=overlap_risk,
                passes_used=["llm"],
            )
        except Exception as e:
            print(f"[routing.py] Sarvam routing failed: {e}. Falling back to default keyword/embedding classifier.")
            logger.error(f"Sarvam routing failed: {e}")

    # ---- FALLBACK: DEFAULT KEYWORD/EMBEDDING PIPELINE ----
    passes_used: List[str] = []
    reasoning_parts: List[str] = []

    # ---- Pass 1: Keyword Matching ----
    keyword_results = _pass1_keyword(text)
    passes_used.append("keyword")

    top_kw = keyword_results[0] if keyword_results else None
    if top_kw:
        reasoning_parts.append(
            f"Keyword pass: top match '{top_kw['dept'].get('department_id', top_kw['dept'].get('id'))}' "
            f"(score={top_kw['score']:.2f}, "
            f"keywords={top_kw['matched_keywords'][:5]})"
        )

    # ---- Pass 2: Embedding Similarity ----
    ollama_alive = _check_ollama_server()
    if ollama_alive:
        keyword_results = _pass2_embedding(text, keyword_results)
        passes_used.append("embedding")
        top_emb = keyword_results[0] if keyword_results else None
        if top_emb:
            emb_sim = top_emb.get("embedding_similarity", "N/A")
            reasoning_parts.append(
                f"Embedding pass: top match '{top_emb['dept'].get('department_id', top_emb['dept'].get('id'))}' "
                f"(combined={top_emb['score']:.2f}, emb_sim={emb_sim})"
            )
    else:
        reasoning_parts.append(
            "Embedding pass: skipped (Ollama not available)."
        )

    # ---- Determine top-2 and overlap ----
    top1 = keyword_results[0] if len(keyword_results) >= 1 else None
    top2 = keyword_results[1] if len(keyword_results) >= 2 else None

    overlap_risk = False
    if top1 and top2:
        gap = top1["score"] - top2["score"]
        if gap < 0.10:
            overlap_risk = True
            reasoning_parts.append(
                f"Overlap risk: top-2 gap only {gap:.2f} "
                f"({top1['dept'].get('department_id', top1['dept'].get('id'))} vs {top2['dept'].get('department_id', top2['dept'].get('id'))})."
            )

    # ---- Pass 3: LLM Fallback (only for MEDIUM confidence) ----
    final_score = top1["score"] if top1 else 0.0
    band = _score_to_band(final_score)

    if band == "MEDIUM" and ollama_alive:
        llm_result = _pass3_llm(text, top1)
        if llm_result:
            passes_used.append("llm")
            llm_dept = llm_result.get("department", "")
            llm_reasoning = llm_result.get("reasoning", "")
            llm_conf = llm_result.get("confidence", "MEDIUM")

            reasoning_parts.append(
                f"LLM pass: suggested '{llm_dept}' "
                f"(confidence={llm_conf}, reason='{llm_reasoning[:100]}')"
            )

            # If LLM agrees with keyword/embedding top pick, boost confidence
            top1_dept_id = top1["dept"].get("department_id", top1["dept"].get("id"))
            if llm_dept == top1_dept_id:
                final_score = min(1.0, final_score + 0.05)
                band = _score_to_band(final_score)
                reasoning_parts.append("LLM confirms keyword/embedding choice.")
            else:
                # LLM disagrees — check if LLM's pick is in our candidates
                for entry in keyword_results:
                    entry_dept_id = entry["dept"].get("department_id", entry["dept"].get("id"))
                    if entry_dept_id == llm_dept:
                        reasoning_parts.append(
                            f"LLM disagrees: prefers '{llm_dept}'. "
                            "Flagging for manual review."
                        )
                        overlap_risk = True
                        break
        else:
            reasoning_parts.append(
                "LLM pass: no valid response received."
            )
    elif band == "MEDIUM":
        reasoning_parts.append(
            "LLM pass: skipped (Ollama not available)."
        )

    # ---- Build result ----
    departments = _load_departments()
    dept_lookup = {d.get("department_id", d.get("id")): d for d in departments}

    primary_dept = top1["dept"] if top1 else {}
    primary_id = primary_dept.get("department_id", primary_dept.get("id", "UNKNOWN"))
    primary_name = primary_dept.get("department_name_en", primary_dept.get("name_en", primary_dept.get("name", "Unknown")))

    # Transfer applicability: if department is NOT CHiPS
    is_self = primary_id == "chips"
    transfer_applicable = not is_self
    section_ref = ""
    if transfer_applicable:
        section_ref = (
            "Section 6(3) of RTI Act, 2005: Transfer of application to "
            "concerned public authority within 5 days."
        )
        reasoning_parts.append(
            f"Transfer under Section 6(3)(2) applicable — "
            f"'{primary_id}' is not CHiPS."
        )

    # Build alternatives
    alternatives: List[AlternativeDepartment] = []
    for entry in keyword_results[1:4]:  # top 3 alternatives
        if entry["score"] > 0.0:
            e_dept = entry["dept"]
            e_id = e_dept.get("department_id", e_dept.get("id"))
            e_name = e_dept.get("department_name_en", e_dept.get("name_en", e_dept.get("name", e_id)))
            alternatives.append(
                AlternativeDepartment(
                    department_id=e_id,
                    department_name=e_name,
                    score=round(entry["score"], 4),
                )
            )

    requires_review = band == "LOW" or overlap_risk

    return RoutingResult(
        primary_department=primary_id,
        department_name=primary_name,
        confidence_band=band,
        confidence_score=round(final_score, 4),
        reasoning=" | ".join(reasoning_parts),
        alternative_departments=alternatives,
        transfer_applicable=transfer_applicable,
        section_reference=section_ref,
        requires_manual_review=requires_review,
        overlap_risk=overlap_risk,
        passes_used=passes_used,
    )
