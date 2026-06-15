import sys
from pathlib import Path

# Force UTF-8 encoding on stdout for Windows compatibility with Devanagari characters
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

from extractor import extract_information

test_text = """
Suresnyogaacharyamd@nucleustechworks.com / 7892193475 गली no. 84, 5 th main, Postal colony, Sanjaynagar,bengaluru, karnataka ,pin code - 560094, Bengaluru , KARNATAKA , India
आर.टी.आई कार्यालय का विवरण जन सूचना अधिकारी नाम Shridhar Diwan पदनाम प्रबंधक कार्यालय का नाम/ कार्यालय अनुभाग का नाम चिप्स ऑफिस /चिप्स ऑफिस कार्यालय का पता SDC Building, opp. New Circuit House, Civil Lines, Raipur, छत्तीसगढ़ राज्य CHHATTISGARH जिला RAIPUR मुख्य विभाग Ministry of Information Technology (9220075138) कार्यालय स्तर State आवेदन बीपीएल श्रेणी का है? No भुगतान विवरण आर.टी.आई आवेदन चालान क्रमांक (treasury Reference Number) 66010526000628 Payment Name RTI Fee Payment Amount 10 Rupees only Date Of Payment Initiated 03/05/2026 Date Of Payment Completed 03/05/2026 Payment Status Success आवेदन दिनांक 04/05/2026 ज.सू.अ. द्वारा दिए गए जवाब की तिथि 01/06/2026 आर.टी.आई आवेदन विवरण (220260503001167) आर.टी.आई विवरण 1.How many cases are pending in your department before law courts including High courts and Supreme courts? 2.How many cases are pending since 20 years and beyond? 3.How many cases beyond 20 years and from the time of formation of the state Chhattisgarh -2000? आवेदन की प्रति RTI information provided by PIO
"""

print("[test_extractor.py] Running extraction...")
res = extract_information(test_text)
print("\n[test_extractor.py] Extracted Information:")
print("Extracted Entities:", res.extracted_entities)
print("Information Type:", res.information_type)
print("Explanation:", res.explanation)
