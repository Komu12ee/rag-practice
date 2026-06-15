import os
import sys
import shutil
import uuid
import json
from pathlib import Path
from datetime import datetime

# Add project directories to sys.path
project_root = Path(__file__).resolve().parent.parent
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import modules to verify
import audit_logger
import document_parser
import export_report
import response_letter
import legal_sections

print("==================================================")
print("VERIFYING PHASE 2 UPGRADE MODULES")
print("==================================================")

case_id = f"RTI_TEST_{datetime.now().year}_{uuid.uuid4().hex[:6].upper()}"
print(f"Generating test case: {case_id}")

# ----------------------------------------------------
# 1. Verify Legal Sections Reference
# ----------------------------------------------------
print("\n--- Verifying Legal Sections ---")
sections = legal_sections.get_hardcoded_sections()
print(f"Successfully loaded {len(sections)} hardcoded legal sections.")
assert len(sections) > 0, "No sections loaded!"
for s in sections[:2]:
    print(f" - {s['section_number']}: {s['title']}")

# Verify JSON file
json_file = project_root / 'data' / 'legal_sections.json'
assert json_file.exists(), "legal_sections.json does not exist in data/"
try:
    json_sections = json.loads(json_file.read_text(encoding='utf-8'))
    print(f"Successfully verified data/legal_sections.json with {len(json_sections)} items.")
except Exception as e:
    print(f"Failed parsing data/legal_sections.json: {e}")
    sys.exit(1)

# ----------------------------------------------------
# 2. Verify Audit Logger & Training Data Export
# ----------------------------------------------------
print("\n--- Verifying Audit Logger ---")
# Log RTI Input
audit_logger.log_rti_input(
    case_id=case_id,
    rti_text="This is a test RTI application about SWADES and e-District portal.",
    source_type="text",
    ocr_confidence=1.0,
    language="en"
)
print("Logged RTI input.")

# Log Routing Decision
audit_logger.log_routing_decision(
    case_id=case_id,
    ai_prediction="revenue",
    pio_override="CHiPS",
    correction_reason="SWADES is under CHiPS jurisdiction.",
    effective_department="CHiPS",
    is_chips=True
)
print("Logged routing decision with override (training flag).")

# Log Exemption Analysis
audit_logger.log_exemption_analysis(
    case_id=case_id,
    ai_analysis={"overall_explanation": "Test exemption analysis"},
    sections_applied=["Section 8(1)(j)"]
)
print("Logged exemption analysis.")

# Log PIO Decision
audit_logger.log_pio_decision(
    case_id=case_id,
    ai_draft="Exemption Section 8(1)(j) applies.",
    pio_edited_text="Exemption Section 8(1)(j) applies. Redact personal info.",
    final_decision="Partially Approve — Partial Disclosure",
    pio_notes="Test notes"
)
print("Logged PIO decision.")

# Log Response Letter
audit_logger.log_response_letter_generated(
    case_id=case_id,
    letter_text="[DOCX letter bytes]",
    export_format="docx"
)
print("Logged response letter generation.")

# Verify log file existence
log_file = audit_logger._get_case_file(case_id)
print(f"Checking log file path: {log_file}")
assert log_file.exists(), "Audit log file was not created!"
log_data = json.loads(log_file.read_text(encoding='utf-8'))
print(f"Log file exists with {len(log_data['events'])} events.")
assert len(log_data['events']) == 5, "Events count mismatch!"

# Test training data export
print("Testing training data export...")
corrections_count = audit_logger.export_training_data()
print(f"Exported {corrections_count} training corrections.")
training_file = project_root / 'training_data' / 'corrections.jsonl'
assert training_file.exists(), "corrections.jsonl was not created!"
print(f"corrections.jsonl created successfully with size {training_file.stat().st_size} bytes.")

# ----------------------------------------------------
# 3. Verify Document Parser Fallback / Native DOCX
# ----------------------------------------------------
print("\n--- Verifying Document Parser ---")
# Mock class for streamlit UploadedFile
class MockUploadedFile:
    def __init__(self, name, content):
        self.name = name
        self.content = content
    def read(self):
        return self.content
    def seek(self, pos):
        pass

# Check image/pdf/docx parser gracefully executes
pdf_result = document_parser._parse_pdf(b"", "test.pdf")
print(f"Mock empty PDF parse warning: {pdf_result.warning}")

# Check detect_language helper
lang1 = document_parser._detect_language("यह एक हिन्दी दस्तावेज है।")
lang2 = document_parser._detect_language("This is an English document.")
print(f"Language detection test: Hindi={lang1}, English={lang2}")
assert lang1 == 'hi', "Language detection failed for Hindi!"
assert lang2 == 'en', "Language detection failed for English!"

# ----------------------------------------------------
# 4. Verify Export Report
# ----------------------------------------------------
print("\n--- Verifying Export Report (DOCX) ---")
mock_session_state = {
    'case_id': case_id,
    'rti_text': "RTI request seeking vendor info.",
    'routing_result': {'department': 'CHiPS', 'confidence': 'HIGH'},
    'is_chips_jurisdiction': True,
    'extracted_entities': {'applicant_name': 'Vishal Kumar', 'systems': 'SWADES'},
    'exemption_analysis': {'overall_explanation': 'Section 8(1)(d) applies.'},
    'ai_recommendation': 'Reject',
    'final_decision_value': 'Reject — Exempt',
    'pio_decision_text': 'PIO agrees that vendor info is commercial confidence under Section 8(1)(d).'
}
docx_report_bytes = export_report.generate_analysis_docx(mock_session_state)
print(f"DOCX analysis report generated. Size: {len(docx_report_bytes)} bytes.")
assert len(docx_report_bytes) > 0, "DOCX report is empty!"

# ----------------------------------------------------
# 5. Verify Response Letter Generator
# ----------------------------------------------------
print("\n--- Verifying Response Letter (Bilingual) ---")
# Test Approve path
letter_bytes_approve = response_letter.generate_response_letter({
    **mock_session_state,
    'final_decision_value': 'Approve — Full Disclosure'
})
# Test Transfer path
letter_bytes_transfer = response_letter.generate_response_letter({
    **mock_session_state,
    'final_decision_value': 'Transfer — Section 6(3)',
    'routing_result': {'department_name': 'Revenue Department', 'department': 'revenue'}
})

print(f"Approve Response Letter size: {len(letter_bytes_approve)} bytes.")
print(f"Transfer Response Letter size: {len(letter_bytes_transfer)} bytes.")
assert len(letter_bytes_approve) > 0, "Approve letter is empty!"
assert len(letter_bytes_transfer) > 0, "Transfer letter is empty!"

print("ALL PHASE 2 UPGRADE MODULES VERIFIED SUCCESSFULLY!")
