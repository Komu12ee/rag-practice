"""
Exemption Rules Engine (Agent 3 - Layer A) for RTI Intelligence System.

Deterministic rule-based evaluation of Section 8 and Section 11 exemptions
based on structured information extraction.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from extractor import ExtractedInformation

# ---------------------------------------------------------------------------
# Pydantic Model for Exemption Flags
# ---------------------------------------------------------------------------
class ExemptionFlag(BaseModel):
    """Exemption flag triggered by the rule engine."""

    section: str = Field(..., description="RTI Act section identifier (e.g. 'Section 8(1)(j)').")
    title: str = Field(..., description="Short title of the exemption.")
    reasoning: str = Field(..., description="Explanation of why this rule triggered based on extraction.")
    suggested_action: str = Field(..., description="Action recommendation for the PIO (e.g. redact, notify third party).")
    is_overridden: bool = Field(default=False, description="True if Section 8(2) public interest override is active.")
    override_reason: Optional[str] = Field(default=None, description="Explanation of the public interest override.")


# ---------------------------------------------------------------------------
# Security Keywords list for Section 8(1)(a)
# ---------------------------------------------------------------------------
SECURITY_KEYWORDS = [
    "firewall", "password", "credential", "router", "switch", "server", 
    "database", "configuration", "network", "backup", "encryption", 
    "security", "active directory", "vpn", "ip address", "architecture", 
    "source code", "schema", "admin", "login"
]


# ---------------------------------------------------------------------------
# Rule Evaluation Engine
# ---------------------------------------------------------------------------
def evaluate_exemptions(info: ExtractedInformation) -> List[ExemptionFlag]:
    """Deterministic evaluation of Section 8 and Section 11 rules.
    
    Accepts ExtractedInformation from Agent 2, returns a list of ExemptionFlags.
    """
    flags: List[ExemptionFlag] = []

    # 1. Section 8(2) Public Interest Override Check
    # This applies to all Section 8(1) exemptions but NOT Section 11 procedural requirement.
    public_interest = info.public_interest_override
    override_text = (
        "Section 8(2) Public Interest Override is ACTIVE: The RTI request contains allegations "
        "of corruption or human rights violations. Under the RTI Act, public interest in disclosure "
        "may outweigh the harm to protected interests, potentially overriding Section 8(1) exemptions."
        if public_interest else None
    )

    # 2. Section 8(1)(a) - Security & Scientific/Economic Interests
    # Trigger: info_type is cybersecurity/architecture OR any system name contains security keywords
    system_trigger_word = None
    for system in info.systems:
        system_lower = system.lower()
        if any(kw in system_lower for kw in SECURITY_KEYWORDS):
            system_trigger_word = system
            break
            
    if info.information_type in ("cybersecurity", "architecture") or system_trigger_word:
        reason = (
            f"Requested information contains cybersecurity/architecture elements. "
            f"Reference to system/term: '{system_trigger_word or info.information_type}'."
        )
        flags.append(
            ExemptionFlag(
                section="Section 8(1)(a)",
                title="Security & Scientific/Economic Interests",
                reasoning=reason,
                suggested_action="Recommend REJECTION or strict REDACTION of technical specifications, passwords, architecture diagrams, or IP addresses to prevent security vulnerability disclosure.",
                is_overridden=public_interest,
                override_reason=override_text
            )
        )

    # 3. Section 8(1)(d) - Commercial Confidence / Active Tenders
    # Trigger: procurement_status == 'active_tender' or info_type == 'procurement' with active tender
    if info.procurement_status == "active_tender" or (info.information_type == "procurement" and info.procurement_status == "active_tender"):
        reason = "RTI request references an active/ongoing procurement tender or commercial bidding process."
        flags.append(
            ExemptionFlag(
                section="Section 8(1)(d)",
                title="Commercial Confidence / Active Tenders",
                reasoning=reason,
                suggested_action="Recommend temporary REJECTION. Disclosure of active bidding details may harm the competitive position of third parties and prejudice the government's procurement process. Re-evaluate once the tender is completed.",
                is_overridden=public_interest,
                override_reason=override_text
            )
        )

    # 4. Section 8(1)(j) - Personal Information & Privacy
    # Trigger: personal_data == True or info_type == 'employee' / 'citizen_data'
    if info.personal_data or info.information_type in ("employee", "citizen_data"):
        reason = (
            f"Requested information involves personal records, private files, or employee documents. "
            f"Information type classified as '{info.information_type}'."
        )
        flags.append(
            ExemptionFlag(
                section="Section 8(1)(j)",
                title="Personal Information & Privacy",
                reasoning=reason,
                suggested_action="Recommend REDACTION under Section 10 (Severability) for all personal identifiers, contact info, and third-party private data. Disclose only if a larger public interest is proven.",
                is_overridden=public_interest,
                override_reason=override_text
            )
        )

    # 5. Section 11 - Third Party Information
    # Trigger: info_type == 'third_party_commercial'
    # Note: Section 11 is a procedural requirement (sending notice to third party).
    # It cannot be overridden by Section 8(2) directly because it's a mandatory procedural step.
    if info.information_type == "third_party_commercial":
        flags.append(
            ExemptionFlag(
                section="Section 11",
                title="Third-Party Information Notice Requirement",
                reasoning="RTI request asks for commercial information, pricing tables, or proprietary data provided in confidence by a third party.",
                suggested_action="Mandatory Procedure: Trigger Section 11 notice to the concerned third party. The PIO must write to them within 5 days of receipt of the request, allowing them 10 days to make representations before any decision is made.",
                is_overridden=False, # Section 11 procedure is absolute
                override_reason=None
            )
        )

    return flags
