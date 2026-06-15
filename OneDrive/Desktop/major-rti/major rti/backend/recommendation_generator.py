"""
Recommendation Generator (Agent 5) for RTI Intelligence System.

Synthesizes routing, extraction, deterministic rule checks, LLM exemption analysis,
and disclosure arguments into a final structured legal recommendation for the PIO.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from routing import RoutingResult
from extractor import ExtractedInformation
from llm_analyzer import LayerBAnalysis, ExemptionAnalysis
from disclosure_balancer import DisclosureBalance
from rag_engine import _check_ollama_server, _OLLAMA_AVAILABLE
from sarvam_client import call_sarvam_chat, SARVAM_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic Schemas for Synthesis
# ---------------------------------------------------------------------------
class ApplicableExemption(BaseModel):
    section: str = Field(..., description="Statutory section applied (e.g. '8(1)(j)').")
    reasoning: str = Field(..., description="Brief reasoning why this clause applies.")
    strength: str = Field("STRONG", description="Strength of the withholding argument (STRONG | MODERATE | WEAK).")


class InapplicableExemption(BaseModel):
    section: str = Field(..., description="Exemption section evaluated but dismissed (e.g. '8(1)(d)').")
    reason: str = Field(..., description="Explanation of why this clause is inapplicable in this case.")


class FinalRecommendation(BaseModel):
    """Unified legal recommendation structured output for the PIO."""

    recommendation: str = Field(..., description="PIO Action recommendation: TRANSFER | APPROVE | PARTIALLY_APPROVE | REJECT.")
    confidence_band: str = Field(..., description="Confidence band: HIGH | MEDIUM | LOW.")
    primary_reasoning: str = Field(..., description="Plain language explanation, maximum 150 words.")
    sections_applied: List[str] = Field(default_factory=list, description="All RTI Act sections cited (e.g. ['Section 6(3)', 'Section 8(1)(j)']).")
    exemptions_applicable: List[ApplicableExemption] = Field(default_factory=list, description="Sections deemed applicable to refuse access.")
    exemptions_considered_inapplicable: List[InapplicableExemption] = Field(default_factory=list, description="Exemptions flagged but dismissed.")
    disclosure_risk: str = Field(..., description="Key risk/consequence if the information is disclosed.")
    rejection_risk: str = Field(..., description="Key risk/consequence if the information is wrongfully rejected (e.g. Section 20 penalty).")
    suggested_pio_action: str = Field(..., description="Actionable next step with timeline for the PIO.")
    requires_third_party_notice: bool = Field(default=False, description="True if Section 11 notice procedure is required.")
    requires_legal_consultation: bool = Field(default=False, description="True if legal counsel review is recommended.")


def _clean_json_response(raw: str) -> str:
    """Extract and clean outer JSON string from LLM responses using bracket matching."""
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
        
    raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*$", "", raw)
    raw = raw.strip()
    raw = re.sub(r",\s*([\]}])", r"\1", raw)
    return raw



# ---------------------------------------------------------------------------
# Core Synthesis Generator
# ---------------------------------------------------------------------------
def generate_final_recommendation(
    text: str,
    routing: RoutingResult,
    extraction: ExtractedInformation,
    layer_b: LayerBAnalysis,
    balance: DisclosureBalance
) -> FinalRecommendation:
    """Compile and synthesize all analytical outputs into a FinalRecommendation."""
    
    # Format the inputs for the LLM prompt
    routing_str = f"Target Dept: {routing.primary_department} ({routing.confidence_band}). Reasoning: {routing.reasoning}"
    
    extraction_str = (
        f"Info Type: {extraction.information_type}. "
        f"Entities: {extraction.extracted_entities}. "
        f"Systems: {extraction.systems}. "
        f"Personal Data: {extraction.personal_data}. "
        f"Public Interest Override: {extraction.public_interest_override}."
    )
    
    layer_b_list = []
    for ea in layer_b.exemptions_analysis:
        layer_b_list.append(f"- {ea.section} (Applicable: {ea.is_applicable}, Conf: {ea.confidence_score}): {ea.legal_reasoning}")
    layer_b_str = "\n".join(layer_b_list) if layer_b_list else "None."

    balance_str = (
        f"Pro-Disclosure Argument: {balance.pro_disclosure_argument}\n"
        f"Pro-Exemption Argument: {balance.pro_exemption_argument}\n"
        f"Weighing Factors: {balance.balancing_factors}"
    )

    prompt = (
        "You are the Chief Legal Advisor for the Public Information Officer at CHiPS.\n"
        "Your task is to synthesize all prior analysis outputs (routing, extraction, LLM analysis, and balanced arguments) into a final structured legal recommendation.\n\n"
        "--- ANALYSIS OUTPUTS ---\n"
        f"1. Routing Analysis:\n{routing_str}\n\n"
        f"2. Extracted Information:\n{extraction_str}\n\n"
        f"3. Exemption Analysis:\n{layer_b_str}\n\n"
        f"4. Balanced Arguments:\n{balance_str}\n\n"
        "--- RULES FOR SYNTHESIS ---\n"
        "1. recommendation choice:\n"
        "   - Choose TRANSFER if routing.transfer_applicable is True.\n"
        "   - Choose REJECT if one or more flagged exemptions are is_applicable = True and there is no public interest override.\n"
        "   - Choose PARTIALLY_APPROVE if some parts are exempt (e.g. personal data exists) but other details can be severed and disclosed under Section 10.\n"
        "   - Choose APPROVE if no exemptions apply.\n"
        "2. sections_applied: Include 'Section 6(3)' if transferring, and the relevant Section 8/9/11 identifiers.\n"
        "3. suggested_pio_action: Give specific actionable timelines (e.g. transfer in 5 days under Section 6(3), notify third party in 5 days under Section 11, or disclose in 30 days under Section 7(1)).\n"
        "4. Write concise, professional legal summaries.\n\n"
        "Provide your recommendation ONLY as a JSON object matching this schema:\n"
        "{\n"
        "  \"recommendation\": \"TRANSFER | APPROVE | PARTIALLY_APPROVE | REJECT\",\n"
        "  \"confidence_band\": \"HIGH | MEDIUM | LOW\",\n"
        "  \"primary_reasoning\": \"Brief explanation (under 150 words)...\",\n"
        "  \"sections_applied\": [\"Section 8(1)(j)\", \"Section 6(3)\"],\n"
        "  \"exemptions_applicable\": [\n"
        "    {\n"
        "      \"section\": \"8(1)(j)\",\n"
        "      \"reasoning\": \"Reasoning text...\",\n"
        "      \"strength\": \"STRONG\"\n"
        "    }\n"
        "  ],\n"
        "  \"exemptions_considered_inapplicable\": [\n"
        "    {\n"
        "      \"section\": \"8(1)(d)\",\n"
        "      \"reason\": \"Reason why dismissed...\"\n"
        "    }\n"
        "  ],\n"
        "  \"disclosure_risk\": \"Privacy breach / security compromise risk...\",\n"
        "  \"rejection_risk\": \"Wrongful rejection / CIC penalty risk under Section 20...\",\n"
        "  \"suggested_pio_action\": \"Specific action timeline...\",\n"
        "  \"requires_third_party_notice\": true | false,\n"
        "  \"requires_legal_consultation\": true | false\n"
        "}"
    )

    if not SARVAM_API_KEY:
        print("[recommendation_generator.py] Sarvam API Key not found. Falling back to heuristics.")
        logger.warning("Sarvam API Key not found for recommendation generation. Falling back to heuristics.")
        return _heuristic_recommendation(routing, extraction, layer_b, balance)

    try:
        print("[recommendation_generator.py] Invoking Sarvam AI for recommendation synthesis...")
        content = call_sarvam_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        try:
            print(f"[recommendation_generator.py] Sarvam AI response content length: {len(content)}")
            logger.debug(f"Sarvam AI response content:\n{content}")
        except Exception:
            pass
        cleaned_content = _clean_json_response(content)
        parsed = json.loads(cleaned_content)
        return FinalRecommendation(**parsed)

    except Exception as e:
        logger.error(f"Recommendation synthesis LLM execution failed: {e}. Falling back to heuristics.")
        return _heuristic_recommendation(routing, extraction, layer_b, balance)


def _heuristic_recommendation(
    routing: RoutingResult,
    extraction: ExtractedInformation,
    layer_b: LayerBAnalysis,
    balance: DisclosureBalance
) -> FinalRecommendation:
    """Heuristic fallback for compiling recommendations when LLM is offline."""
    
    # 1. Determine recommended action
    recom = "APPROVE"
    sections_applied = []
    applicable_ex = []
    inapplicable_ex = []
    
    if routing.transfer_applicable:
        recom = "TRANSFER"
        sections_applied.append("Section 6(3)")
        suggested_action = f"Transfer the application to the Public Information Officer of {routing.department_name} under Section 6(3) of the RTI Act within 5 days of receipt."
    
    # Process exemptions
    has_ex = False
    requires_notice = False
    for ea in layer_b.exemptions_analysis:
        if ea.is_applicable:
            has_ex = True
            sections_applied.append(ea.section)
            applicable_ex.append(ApplicableExemption(
                section=ea.section.replace("Section ", ""),
                reasoning=ea.legal_reasoning,
                strength="STRONG" if ea.confidence_score > 0.8 else "MODERATE"
            ))
            if "11" in ea.section:
                requires_notice = True
        else:
            inapplicable_ex.append(InapplicableExemption(
                section=ea.section.replace("Section ", ""),
                reason="The criteria for this exemption were evaluated but dismissed during legal balance check."
            ))

    if not routing.transfer_applicable:
        if has_ex:
            # If personal data, prefer partially approve (redact & release)
            if extraction.personal_data:
                recom = "PARTIALLY_APPROVE"
                suggested_action = "Redact all personal identifiers (names, contacts, medical files) under Section 10 (Severability) and disclose the remaining public records within 30 days."
            else:
                recom = "REJECT"
                suggested_action = "Issue a formal rejection letter citing the applicable Section 8(1) clauses, outlining the appeal procedure within 30 days of receipt."
        else:
            recom = "APPROVE"
            suggested_action = "Provide access to the requested records within 30 days of receipt under Section 7(1)."

    if requires_notice:
        suggested_action = "Issue a Section 11 notice to the concerned third party within 5 days. Wait 10 days for representation before making disclosure choice."

    # General reasoning compilation
    reason = (
        f"Recommendation is to {recom}. "
        f"The jurisdiction belongs to {routing.primary_department.upper()}. "
    )
    if has_ex:
        reason += f"Exemption grounds found under: {', '.join(sections_applied)}. "
    else:
        reason += "No exemption grounds apply."

    disc_risk = "N/A"
    rej_risk = "Wrongful refusal of access may lead to a standard penalty of Rs. 250 per day up to Rs. 25,000 under Section 20(1) of the RTI Act, 2005."
    
    if "Section 8(1)(j)" in sections_applied:
        disc_risk = "Disclosing private records causes unwarranted invasion of individual privacy, violating statutory protections under Section 8(1)(j)."
    elif "Section 8(1)(d)" in sections_applied:
        disc_risk = "Disclosing active bidding details compromises commercial secrets and prejudices government bargaining power."
    elif "Section 8(1)(a)" in sections_applied:
        disc_risk = "Disclosing internal IT architecture or passwords exposes government network systems to hostile cybersecurity attacks."

    return FinalRecommendation(
        recommendation=recom,
        confidence_band=routing.confidence_band,
        primary_reasoning=reason,
        sections_applied=sections_applied,
        exemptions_applicable=applicable_ex,
        exemptions_considered_inapplicable=inapplicable_ex,
        disclosure_risk=disc_risk,
        rejection_risk=rej_risk,
        suggested_pio_action=suggested_action,
        requires_third_party_notice=requires_notice,
        requires_legal_consultation=has_ex
    )
