"""
Disclosure Balancer (Agent 4) for RTI Intelligence System.

Generates balanced, side-by-side legal arguments (pro-disclosure vs. pro-exemption)
to protect against confirmation bias and ensure compliance with Section 7(1).
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
# Pydantic Schema for Balancer Output
# ---------------------------------------------------------------------------
class DisclosureBalance(BaseModel):
    """Side-by-side adversarial legal arguments regarding disclosure."""

    pro_disclosure_argument: str = Field(..., description="Strongest case for disclosing the requested records, invoking severability or public interest.")
    pro_exemption_argument: str = Field(..., description="Strongest case for withholding/redacting the requested records, invoking statutory exemptions and harms.")
    balancing_factors: str = Field(..., description="Core criteria the PIO must weigh (e.g. privacy vs public spend accountability).")


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
# Core Balancer Logic
# ---------------------------------------------------------------------------
def compute_disclosure_balance(text: str, rule_flags: List[str]) -> DisclosureBalance:
    """Generate side-by-side legal arguments for and against disclosure.
    
    Uses Qwen-3B to compile balanced arguments based on RAG statutory context.
    """
    # 1. Retrieve statutory context
    retrieved_sections = retrieve_relevant_sections(text, top_k=3)
    context_str = ""
    for idx, s in enumerate(retrieved_sections, 1):
        context_str += f"[{idx}] {s['section']} - {s['title']}\nStatutory Text: {s['text']}\n\n"

    prompt = (
        "You are an impartial legal advisor supporting a Chhattisgarh Public Information Officer.\n"
        "Your task is to compile a balanced legal analysis presenting the case for and against disclosure.\n\n"
        f"RTI Request Text:\n\"\"\"\n{text}\n\"\"\"\n\n"
        f"Triggered Exemptions:\n{', '.join(rule_flags) if rule_flags else 'None'}\n\n"
        f"Retrieved RTI Act Statutory context:\n{context_str}\n"
        "--- INSTRUCTIONS ---\n"
        "1. Write a strong, legally reasoned case FOR disclosing the information. Suggest redacting personal details (Section 10 severability) or point out public accountability reasons if applicable.\n"
        "2. Write a strong, legally reasoned case AGAINST disclosing (withholding/redacting) the information, focusing on security, competitive harm, or private details.\n"
        "3. Summarize the balancing factors the PIO must weigh in their final decision.\n"
        "4. Rely strictly on the statutory wording. Do not hallucinate external laws.\n\n"
        "Provide your analysis ONLY as a JSON object matching this schema:\n"
        "{\n"
        "  \"pro_disclosure_argument\": \"Detailed argument for disclosure...\",\n"
        "  \"pro_exemption_argument\": \"Detailed argument for exemption...\",\n"
        "  \"balancing_factors\": \"Detailed key factors to weigh...\"\n"
        "}"
    )

    if not SARVAM_API_KEY:
        print("[disclosure_balancer.py] Sarvam API Key not found. Falling back to heuristics.")
        logger.warning("Sarvam API Key not found for disclosure balancer. Falling back to heuristics.")
        return _heuristic_balance(text, rule_flags)

    try:
        print("[disclosure_balancer.py] Invoking Sarvam AI for public interest balancing...")
        content = call_sarvam_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        try:
            print(f"[disclosure_balancer.py] Sarvam AI response content length: {len(content)}")
            logger.debug(f"Sarvam AI response content:\n{content}")
        except Exception:
            pass
        cleaned_content = _clean_json_response(content)
        parsed = json.loads(cleaned_content)
        
        # Standardize keys to handle LLM synonym output
        std_keys = {
            "pro_disclosure_argument": ["pro_disclosure_argument", "pro_disclosure", "pro_disclosure_arguments", "disclosure_argument", "pro_disclosure_case", "pro_disclosure_argument_case"],
            "pro_exemption_argument": ["pro_exemption_argument", "pro_exemption", "pro_exemption_arguments", "exemption_argument", "pro_exemption_case", "pro_rejection_argument", "pro_rejection_case"],
            "balancing_factors": ["balancing_factors", "balancing_factor", "factors", "weighing_factors"]
        }
        
        cleaned = {}
        for target, synonyms in std_keys.items():
            found = False
            for syn in synonyms:
                if syn in parsed:
                    cleaned[target] = parsed[syn]
                    found = True
                    break
            if not found:
                for k in parsed.keys():
                    if any(s in k.lower() for s in synonyms):
                        cleaned[target] = parsed[k]
                        found = True
                        break
            if not found:
                cleaned[target] = "Not analyzed."
                
        return DisclosureBalance(**cleaned)
    except Exception as e:
        logger.error(f"Disclosure balancer LLM execution failed: {e}. Falling back to heuristics.")
        return _heuristic_balance(text, rule_flags)


def _heuristic_balance(text: str, rule_flags: List[str]) -> DisclosureBalance:
    """Heuristic fallback for disclosure arguments when LLM is offline."""
    if not rule_flags:
        return DisclosureBalance(
            pro_disclosure_argument="No statutory exemptions apply. Under Section 3 of the RTI Act, all citizens have the right to information. Full disclosure is recommended.",
            pro_exemption_argument="No statutory exemption has been triggered. Refusal of access without a valid Section 8/9 ground is a violation of the Act and exposes the PIO to penalties under Section 20.",
            balancing_factors="Verify that the requested records belong to CHiPS and do not contain generic unflagged personal identifiers."
        )

    # Compile based on triggered sections
    pro_disc = []
    pro_ex = []
    factors = []

    if "Section 8(1)(j)" in rule_flags:
        pro_disc.append("Apply Section 10 (Severability) to redact only private coordinates (phone, medical data, address) and disclose the general official records, salaries, or designations, preserving public transparency.")
        pro_ex.append("Protect employee/citizen privacy under Section 8(1)(j). Individual medical reports or performance reviews are personal information with no public interest link, and disclosure causes unwarranted privacy invasion.")
        factors.append("Weigh private individual interest in confidentiality against any public activity/interest in the record.")

    if "Section 8(1)(d)" in rule_flags:
        pro_disc.append("Under Section 8(1)(d), disclosure is warranted if a larger public interest is served, e.g., verifying procurement transparency or expenditure of public funds once evaluation is complete.")
        pro_ex.append("Active tender details represent commercial confidence. Disclosing bids before award harms competitive positioning of third parties and prejudices the government's bargaining power.")
        factors.append("Identify if the tender is still active. Completed tenders are generally disclosable, whereas active bids must be withheld.")

    if "Section 8(1)(a)" in rule_flags:
        pro_disc.append("Disclose only high-level project goals or public guidelines. Redact core configurations or passwords, keeping system security intact while fulfilling public interest.")
        pro_ex.append("Cybersecurity data (IP routing, firewalls, source code) represents critical infrastructure configuration. Disclosure exposes government IT systems to hostile cyber attacks, prejudicing state interests.")
        factors.append("Weigh public security threats against any general transparency regarding public database deployment.")

    if "Section 11" in rule_flags:
        pro_disc.append("Permit disclosure if the third party gives consent, or if the public interest in disclosure outweighs the commercial injury to the vendor.")
        pro_ex.append("Information was shared in confidence. Proceeding with disclosure without third-party notice violates mandatory procedures under Section 11.")
        factors.append("Trigger the Section 11 notice procedure. Wait for vendor representations before making a disclosure choice.")

    # Default fallbacks
    if not pro_disc:
        pro_disc.append("Disclose the general elements of the records, sanitizing sensitive columns under Section 10.")
    if not pro_ex:
        pro_ex.append("Refuse access under the triggered Section 8(1) grounds to protect sensitive government records.")
    if not factors:
        factors.append("Assess if public interest warrants disclosure under Section 8(2).")

    return DisclosureBalance(
        pro_disclosure_argument=" | ".join(pro_disc),
        pro_exemption_argument=" | ".join(pro_ex),
        balancing_factors=" | ".join(factors)
    )


# ---------------------------------------------------------------------------
# Module Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing Disclosure Balancer...")
    res = compute_disclosure_balance(
        "Please provide the service file and private medical details of Ramesh Kumar.",
        ["Section 8(1)(j)"]
    )
    print("\nPro-Disclosure Argument:", res.pro_disclosure_argument)
    print("\nPro-Exemption Argument:", res.pro_exemption_argument)
    print("\nWeighing Factors:", res.balancing_factors)
