import os
import sys
from pathlib import Path

# Force UTF-8 encoding on stdout for Windows compatibility with Devanagari characters
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add backend directory to path
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

from response_letter import generate_response_letter
from export_report import generate_analysis_docx

# Create assets and templates folders in workspace for testing
( _ROOT_DIR / "assets" ).mkdir(exist_ok=True)
( _ROOT_DIR / "templates" ).mkdir(exist_ok=True)

def run_test(case_name: str, rti_text: str, decision: str, notes: str, overrides: dict = None):
    print(f"\n========================================")
    print(f"TEST: {case_name}")
    print(f"DECISION: {decision}")
    print(f"========================================")
    
    from extractor import ExtractedInformation
    
    session_state = {
        'case_id': f"RTI_CHiPS_2026_{case_name.replace(' ', '_')}",
        'rti_text': rti_text,
        'final_decision_value': decision,
        'pio_decision_text': notes,
        'decision_finalized': True,
        'exemption_flags': []
    }
    
    if overrides:
        session_state.update(overrides)
    
    from response_letter import DOCX_AVAILABLE
    ext = 'docx' if DOCX_AVAILABLE else 'txt'
    
    print("Generating response letter...")
    doc_bytes = generate_response_letter(session_state)
    out_path = _ROOT_DIR / "scratch" / f"test_output_{case_name.lower().replace(' ', '_')}.{ext}"
    out_path.write_bytes(doc_bytes)
    print(f"SUCCESS: Generated response letter saved to: {out_path}")

    print("Generating analysis report...")
    report_bytes = generate_analysis_docx(session_state)
    report_path = _ROOT_DIR / "scratch" / f"test_report_{case_name.lower().replace(' ', '_')}.{ext}"
    report_path.write_bytes(report_bytes)
    print(f"SUCCESS: Generated analysis report saved to: {report_path}")


if __name__ == "__main__":
    from extractor import ExtractedInformation
    from exemption_rules import ExemptionFlag
    
    # Test Case 1: Hindi query regarding CG SWAN network engineer recruitment (Overridden Transfer)
    hindi_text = """
आर.टी.आई. आवेदन पत्र (सूचना का अधिकार अधिनियम, 2005)
आवेदक: श्री राजेश कुमार गुप्ता, पता: 45, सिविल लाइन्स, बिलासपुर, छत्तीसगढ़।
विषय: CG SWAN परियोजना के अंतर्गत भर्ती किए गए नेटवर्क इंजीनियरों के संबंध में जानकारी।
जानकारी: 
1. CG SWAN परियोजना के तहत बिलासपुर जिले में कुल कितने नेटवर्क इंजीनियरों की नियुक्ति की गई है?
2. इन इंजीनियरों की उपस्थिति पंजी तथा मासिक वेतन भुगतान का विवरण उपलब्ध कराएं।
"""
    
    # Simulate PIO overrides: PIO corrected name, address, and target department
    hindi_overrides = {
        'effective_department': 'जिला कलेक्टर कार्यालय बिलासपुर (राजस्व विभाग)',
        'pio_routing_override': 'bilaspur_collector',
        'confirmed_info': ExtractedInformation(
            extracted_entities=['श्री राजेश कुमार गुप्ता', '45, सिविल लाइन्स, बिलासपुर', 'CG SWAN परियोजना'],
            information_type='employee',
            systems=['CG SWAN'],
            procurement_status='none',
            personal_data=True,
            public_interest_override=False,
            explanation='आवेदन बिलासपुर में नेटवर्क इंजीनियरों की उपस्थिति और वेतन से संबंधित है।'
        )
    }
    
    run_test(
        case_name="CG SWAN Hindi Transfer",
        rti_text=hindi_text,
        decision="Transfer — Section 6(3)",
        notes="बिलासपुर जिले के नेटवर्क इंजीनियरों की उपस्थिति और भुगतान से संबंधित अभिलेख जिला कलेक्टर कार्यालय बिलासपुर के पास संधारित हैं।",
        overrides=hindi_overrides
    )
    
    # Test Case 2: English query regarding State Data Centre server agreements (Approve with Exemption flags)
    english_text = """
RTI Request (Right to Information Act, 2005)
Applicant: Shri Amit Sharma, Address: Sector-3, Devendra Nagar, Raipur, CG.
Subject: Server Procurement Agreements of State Data Centre (SDC).
Details:
Please provide certified copies of the original procurement agreement, service level agreement (SLA), and server inventory counts for the State Data Centre (SDC) Raipur.
"""
    
    # Simulate PIO overrides: approved but with some overridden and active exemption flags
    english_overrides = {
        'effective_department': 'CHiPS SDC Division',
        'confirmed_info': ExtractedInformation(
            extracted_entities=['Shri Amit Sharma', 'Sector-3, Devendra Nagar, Raipur', 'State Data Centre (SDC)', 'procurement agreement'],
            information_type='procurement',
            systems=['SDC'],
            procurement_status='completed_tender',
            personal_data=False,
            public_interest_override=False,
            explanation='RTI seeks SDC procurement agreement copies and server inventory logs.'
        ),
        'exemption_flags': [
            # Active flag (should be processed)
            ExemptionFlag(
                section='Section 8(1)(d)',
                title='Commercial Confidence',
                reasoning='Pricing details in procurement agreements contain commercial secrets.',
                suggested_action='Redact pricing tables',
                is_overridden=False
            ),
            # Overridden flag (should be ignored by generator)
            ExemptionFlag(
                section='Section 8(1)(g)',
                title='Safety of Life or Physical Safety',
                reasoning='Location of SDC servers might pose security risk.',
                suggested_action='Withhold',
                is_overridden=True,
                override_reason='SDC location is public knowledge; safety threat is not applicable.'
            )
        ]
    }
    
    run_test(
        case_name="SDC English Approve",
        rti_text=english_text,
        decision="Partially Approve — Partial Disclosure",
        notes="Pricing values are severed under Section 10 since they fall under commercial confidence. The remaining server agreements are provided.",
        overrides=english_overrides
    )

