
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
"""Quick validation of all RTI system modules."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("Python", sys.version)
print()

# Test imports
modules = ['db', 'ocr', 'routing']
for mod in modules:
    try:
        m = __import__(mod)
        print(f'[OK] {mod}.py imported successfully')
    except Exception as e:
        print(f'[FAIL] {mod}.py import error: {e}')

print()

# Test database initialization
from db import init_db, AuditRecord, log_analysis
init_db()
print('[OK] Database initialized (rti_audit.db)')

# Test OCR module
from ocr import detect_language, OCRResult
lang = detect_language('Please provide information about government projects')
print(f'[OK] Language detection: English text -> {lang}')

# Test routing with keyword-only
from routing import classify_department
result = classify_department('Please provide details of all IT projects managed by CHiPS')
print(f'[OK] Routing: CHiPS IT query -> {result.primary_department} ({result.confidence_band})')
print(f'     Reasoning: {result.reasoning[:120]}...')

print()
print('[DONE] All modules validated successfully!')
