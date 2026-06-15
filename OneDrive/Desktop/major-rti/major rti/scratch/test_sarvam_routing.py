import os
import sys
from pathlib import Path

# Force UTF-8 encoding on stdout for Windows compatibility with Devanagari characters
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add backend to path
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

from routing import classify_department

def run_test(query: str, desc: str):
    print(f"\n========================================\nTEST: {desc}\nQUERY: '{query}'\n========================================")
    result = classify_department(query)
    
    print("\n--- RESULTS ---")
    print(f"Primary Dept ID   : {result.primary_department}")
    print(f"Primary Dept Name : {result.department_name}")
    print(f"Confidence Band   : {result.confidence_band}")
    print(f"Confidence Score  : {result.confidence_score}")
    print(f"Transfer App      : {result.transfer_applicable}")
    print(f"Section Ref       : {result.section_reference}")
    print(f"Overlap Risk      : {result.overlap_risk}")
    
    print("\n--- Alternatives ---")
    for alt in result.alternative_departments:
        print(f"  - {alt.department_id} ({alt.department_name}): score={alt.score}")
        
    print("\n--- Reasoning ---")
    for step in result.reasoning.split("|"):
        print(f"  * {step.strip()}")

if __name__ == "__main__":
    # Test 1: Aadhaar delay (should transfer to Revenue/Home/GAD/UIDAI, not CHiPS)
    run_test(
        query="why i don't get my adhar why it is getting delay",
        desc="Aadhaar delay query (Should NOT route to CHiPS)"
    )
    
    # Test 2: SDC server SLA agreements (should route to CHiPS)
    run_test(
        query="Provide certified copies of the State Data Centre (SDC) server procurement agreements and active SLA documents with the System Integrator.",
        desc="SDC Procurement & SLA agreements query (Should route to CHiPS)"
    )
