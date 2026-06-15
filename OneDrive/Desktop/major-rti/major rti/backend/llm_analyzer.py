"""
LLM Exemption Analyzer (Agent 3 - Layer B) for RTI Intelligence System.

Performs reasoned analysis of deterministically flagged legal exemptions
using Ollama qwen2.5:3b. Employs RAG statutory context for strict citation
grounding and prevents LLM-hallucinated exemptions.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from rag_engine import retrieve_relevant_sections, _check_ollama_server, _OLLAMA_AVAILABLE
from sarvam_client import call_sarvam_chat, SARVAM_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ExemptionAnalysis(BaseModel):
    """Reasoned analysis for a single flagged exemption section."""

    section: str = Field(..., description="The section identifier (e.g. 'Section 8(1)(j)').")
    is_applicable: bool = Field(..., description="True if the exemption legally applies and information should be withheld.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="PIO confidence score in this reasoning (0-1).")
    legal_reasoning: str = Field(..., description="A detailed paragraph explaining why this section applies or does not apply, grounded in the statutory text.")
    exact_quotes: List[str] = Field(default_factory=list, description="Exact quotes from the statutory text supporting this reasoning.")


class LayerBAnalysis(BaseModel):
    """Container for the full Layer B analysis output."""

    exemptions_analysis: List[ExemptionAnalysis] = Field(default_factory=list)
    overall_explanation: str = Field(..., description="Synthesis of the legal exemption findings.")


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
# Core Analysis Logic
# ---------------------------------------------------------------------------
def analyze_exemption_applicability(text: str, rule_flags: List[str]) -> LayerBAnalysis:
    """Analyze the applicability of flagged exemptions using Qwen.
    
    Ensures analysis is strictly grounded in retrieved RAG sections and
    only evaluates sections flagged by Layer A rules.
    """
    if not rule_flags:
        return LayerBAnalysis(
            exemptions_analysis=[],
            overall_explanation="No exemptions were flagged by the deterministic rule engine (Layer A). The information is disclosable."
        )

    # 1. Retrieve statutory text via RAG
    # We query RAG with the RTI text to retrieve the top sections. We also ensure
    # the explicitly flagged sections are retrieved.
    retrieved_sections = retrieve_relevant_sections(text, top_k=4)
    
    # Guarantee that the flagged sections are included in the RAG context
    retrieved_ids = {s["section"] for s in retrieved_sections}
    
    # Load all sections to find the missing ones
    from rag_engine import _load_sections
    all_sections = _load_sections()
    sec_map = {s["section"]: s for s in all_sections}
    
    for flag in rule_flags:
        if flag in sec_map and flag not in retrieved_ids:
            # Append it to the context
            retrieved_sections.append({
                "section": flag,
                "title": sec_map[flag]["title"],
                "text": sec_map[flag]["text"],
                "similarity": 1.0  # Priority load
            })

    # Format RAG statutory context
    context_str = ""
    for idx, s in enumerate(retrieved_sections, 1):
        context_str += f"[{idx}] {s['section']} - {s['title']}\nStatutory Text: {s['text']}\n\n"

    # Build prompt
    prompt = (
        "You are the senior Assistant Public Information Officer at CHiPS, Chhattisgarh, acting as a legal analyst.\n"
        "Your task is to determine whether the deterministically flagged RTI exemptions are applicable to the query.\n\n"
        f"RTI Request Text:\n\"\"\"\n{text}\n\"\"\"\n\n"
        f"Flagged Exemptions to Analyze:\n{', '.join(rule_flags)}\n\n"
        f"Statutory Legal Context (RTI Act 2005):\n{context_str}\n"
        "--- SYSTEM CONSTRAINTS ---\n"
        "1. You MUST ONLY analyze the exemptions that have been explicitly flagged above. Do not analyze or flag any other sections.\n"
        "2. Ground your reasoning strictly in the Statutory Legal Context provided. Citing non-provided clauses, cases, or external laws is strictly forbidden.\n"
        "3. For each flagged exemption, explain if it is APPLICABLE (withholds information) or NOT APPLICABLE (requires disclosure) based on the facts.\n"
        "4. Quote exact phrases/sentences from the Statutory Legal Context to support your arguments.\n\n"
        "Provide your analysis ONLY as a JSON object matching this schema:\n"
        "{\n"
        "  \"exemptions_analysis\": [\n"
        "    {\n"
        "      \"section\": \"Section 8(1)(j)\",\n"
        "      \"is_applicable\": true,\n"
        "      \"confidence_score\": 0.90,\n"
        "      \"legal_reasoning\": \"Detailed reasoning text explaining applicability...\",\n"
        "      \"exact_quotes\": [\"exact statutory text quote 1\", \"quote 2\"]\n"
        "    }\n"
        "  ],\n"
        "  \"overall_explanation\": \"Synthesis of findings...\"\n"
        "}"
    )

    if not SARVAM_API_KEY:
        print("[llm_analyzer.py] Sarvam API Key not found. Falling back to heuristics.")
        logger.warning("Sarvam API Key not found for Layer B. Generating heuristic reasoning.")
        return _heuristic_analyze(text, rule_flags, retrieved_sections)

    try:
        print("[llm_analyzer.py] Invoking Sarvam AI for Layer B exemption analysis...")
        content = call_sarvam_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        try:
            print(f"[llm_analyzer.py] Sarvam AI response content length: {len(content)}")
            logger.debug(f"Sarvam AI response content:\n{content}")
        except Exception:
            pass
        cleaned_content = _clean_json_response(content)
        parsed = json.loads(cleaned_content)
        
        # Verify that only flagged sections are present in LLM output
        filtered_analysis = []
        for ea in parsed.get("exemptions_analysis", []):
            if ea.get("section") in rule_flags:
                filtered_analysis.append(ExemptionAnalysis(**ea))
        
        parsed["exemptions_analysis"] = filtered_analysis
        return LayerBAnalysis(**parsed)

    except Exception as e:
        logger.error(f"Layer B LLM analysis failed: {e}. Falling back to heuristics.")
        return _heuristic_analyze(text, rule_flags, retrieved_sections)


def _heuristic_analyze(text: str, rule_flags: List[str], retrieved_sections: List[Dict[str, Any]]) -> LayerBAnalysis:
    """Heuristic fallback for Layer B reasoning when LLM is offline."""
    sec_map = {s["section"]: s for s in retrieved_sections}
    analyses = []

    for flag in rule_flags:
        sec_data = sec_map.get(flag)
        if not sec_data:
            continue
            
        is_applicable = True
        quotes = []
        
        if flag == "Section 8(1)(j)":
            reason = (
                "The request seeks personal information of a citizen or employee. "
                "Under the Act, there is no obligation to disclose personal records that have no "
                "relationship to public activities and would cause an unwarranted invasion of privacy."
            )
            quotes = ["information which relates to personal information", "cause unwarranted invasion of the privacy of the individual"]
        elif flag == "Section 8(1)(d)":
            reason = (
                "The query involves commercial bids, pricing details, or trade secrets of active tenders. "
                "Disclosing active tender bids during evaluation would harm the competitive position of the vendors "
                "and compromise government procurement integrity."
            )
            quotes = ["commercial confidence, trade secrets or intellectual property", "harm the competitive position of a third party"]
        elif flag == "Section 8(1)(a)":
            reason = (
                "The request queries IT infrastructure architecture, configurations, or cybersecurity server systems. "
                "Disclosing technical specifications or configurations of core systems compromises the security interests of the State."
            )
            quotes = ["security, strategic, scientific or economic interests of the State"]
        elif flag == "Section 11":
            reason = (
                "Third-party commercial pricing or confidential financial models are requested. "
                "A mandatory notification notice must be sent to the third party within 5 days, inviting their representation."
            )
            quotes = ["relates to or has been supplied by a third party and has been treated as confidential"]
        else:
            reason = f"Heuristic analysis for {flag}: Exemption flags suggest potential refusal ground. Detailed review advised."
            quotes = [sec_data["text"][:80]]

        analyses.append(
            ExemptionAnalysis(
                section=flag,
                is_applicable=is_applicable,
                confidence_score=0.85,
                legal_reasoning=reason,
                exact_quotes=quotes
            )
        )

    return LayerBAnalysis(
        exemptions_analysis=analyses,
        overall_explanation=(
            f"Heuristic Layer B Analysis compiled for: {', '.join(rule_flags)}. "
            "Exemptions confirmed based on keyword triggers. Please audit manually before legal citation."
        )
    )


# ---------------------------------------------------------------------------
# Module Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing Layer B LLM Exemption Analyzer...")
    res = analyze_exemption_applicability(
        "Please provide the service file and private medical details of Ramesh Kumar.",
        ["Section 8(1)(j)"]
    )
    print("\nOverall Explanation:", res.overall_explanation)
    for ea in res.exemptions_analysis:
        print(f"\n- Exemption: {ea.section} (Applicable: {ea.is_applicable}, Conf: {ea.confidence_score})")
        print("  Reasoning:", ea.legal_reasoning)
        print("  Quotes Cited:", ea.exact_quotes)
