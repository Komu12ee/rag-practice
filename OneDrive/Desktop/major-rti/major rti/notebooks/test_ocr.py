
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
import sys
sys.path.insert(0, '.')
from ocr import OCRResult, detect_language, extract_text_from_pdf

print('ocr.py: IMPORT OK')
print('detect_language tests:')
print(f'  English: {detect_language("This is an RTI application regarding IT infrastructure")}')
print(f'  Hindi: {detect_language("यह सूचना का अधिकार आवेदन है")}')
print(f'  Mixed: {detect_language("RTI application सूचना अधिकार regarding infrastructure बुनियादी ढांचा")}')
print()

# Test PDF extraction on the existing PDF
try:
    result = extract_text_from_pdf(str(Path(__file__).resolve().parent.parent / "data" / "5_6104888577781406923.pdf"))
    print(f"PDF extraction: SUCCESS")
    print(f"  Text length: {len(result.text)} chars")
    print(f"  Language: {result.language}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Low confidence flag: {result.low_confidence_flag}")
    print(f"  Warnings: {result.warnings}")
    print(f"  First 200 chars: {result.text[:200]}")
except Exception as e:
    print(f"PDF extraction: {e}")
