import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from extractor import extract_information
from exemption_rules import evaluate_exemptions

# Test cases
test_cases = [
    {
        "name": "Personal data request",
        "text": "Please provide the service book and medical records of employee Ramesh Kumar, who works as a senior assistant."
    },
    {
        "name": "Active tender query",
        "text": "Please provide the bid details, pricing, and tender evaluation files for the ongoing e-District system modernization tender which is currently active and open for bidding."
    },
    {
        "name": "Cybersecurity request",
        "text": "Please provide the firewall configuration files, system architecture diagram, and network IP routing tables for the core database server of CHiPS."
    },
    {
        "name": "Procurement query with corruption allegation",
        "text": "Please provide details of active tender T-8787. I am requesting this because there is a severe corruption scandal and bribe allegations involving the selection committee."
    },
    {
        "name": "Third-party commercial query",
        "text": "Please provide the proprietary pricing models and corporate tax returns submitted to CHiPS by Tech Mahindra in commercial confidence during their partnership."
    }
]

print("=== STARTING PHASE 1 EXTRACTION & EXEMPTION VERIFICATION ===")

for i, tc in enumerate(test_cases, 1):
    print(f"\n--- Test Case {i}: {tc['name']} ---")
    print(f"RTI Input: {tc['text']}")
    
    # 1. Extractor
    print("Running Extractor (Agent 2)...")
    info = extract_information(tc['text'])
    print(f"  Classified Info Type: {info.information_type}")
    print(f"  Systems Detected: {info.systems}")
    print(f"  Procurement Status: {info.procurement_status}")
    print(f"  Personal Data: {info.personal_data}")
    print(f"  Public Interest Override: {info.public_interest_override}")
    print(f"  Entities: {info.extracted_entities}")
    print(f"  Explanation: {info.explanation}")
    
    # 2. Exemption Rules
    print("Running Exemption Engine (Agent 3 - Layer A)...")
    flags = evaluate_exemptions(info)
    if not flags:
        print("  Result: [DISCLOSABLE] No exemption flags triggered.")
    for flag in flags:
        print(f"  - Triggered: {flag.section} ({flag.title})")
        print(f"    Reasoning: {flag.reasoning}")
        print(f"    PIO Action: {flag.suggested_action}")
        if flag.is_overridden:
            print(f"    [OVERRIDE WARNING]: {flag.override_reason}")

print("\n=== VERIFICATION COMPLETE ===")
