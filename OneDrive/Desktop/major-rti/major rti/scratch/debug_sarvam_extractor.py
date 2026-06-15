import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

from sarvam_client import call_sarvam_chat

test_text = """
Suresnyogaacharyamd@nucleustechworks.com / 7892193475 गली no. 84, 5 th main, Postal colony, Sanjaynagar,bengaluru, karnataka ,pin code - 560094, Bengaluru , KARNATAKA , India
आर.टी.आई कार्यालय का विवरण जन सूचना अधिकारी नाम Shridhar Diwan पदनाम प्रबंधक कार्यालय का नाम/ कार्यालय अनुभाग का नाम चिप्स ऑफिस /चिप्स ऑफिस कार्यालय का पता SDC Building, opp. New Circuit House, Civil Lines, Raipur, छत्तीसगढ़ राज्य CHHATTISGARH जिला RAIPUR मुख्य विभाग Ministry of Information Technology (9220075138) कार्यालय स्तर State आवेदन बीपीएल श्रेणी का है? No भुगतान विवरण आर.टी.आई आवेदन चालान क्रमांक (treasury Reference Number) 66010526000628 Payment Name RTI Fee Payment Amount 10 Rupees only Date Of Payment Initiated 03/05/2026 Date Of Payment Completed 03/05/2026 Payment Status Success आवेदन दिनांक 04/05/2026 ज.सू.अ. द्वारा दिए गए जवाब की तिथि 01/06/2026 आर.टी.आई आवेदन विवरण (220260503001167) आर.टी.आई विवरण 1.How many cases are pending in your department before law courts including High courts and Supreme courts? 2.How many cases are pending since 20 years and beyond? 3.How many cases beyond 20 years and from the time of formation of the state Chhattisgarh -2000? आवेदन की प्रति RTI information provided by PIO
"""

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
{test_text[:2500]}

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

print("[debug_sarvam_extractor.py] Calling Sarvam...")
content = call_sarvam_chat(
    messages=[{"role": "user", "content": prompt}],
    temperature=0.1
)

output_file = _ROOT_DIR / "scratch" / "sample_response_extractor.txt"
output_file.write_text(content, encoding="utf-8")
print(f"[debug_sarvam_extractor.py] Saved raw content to: {output_file}")
