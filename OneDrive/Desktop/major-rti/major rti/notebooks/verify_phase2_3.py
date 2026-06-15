import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from routing import classify_department
from extractor import extract_information
from exemption_rules import evaluate_exemptions
from llm_analyzer import analyze_exemption_applicability
from disclosure_balancer import compute_disclosure_balance
from recommendation_generator import generate_final_recommendation

# Test Query
test_text = "Please provide the private medical records, bank details, and service files of employee Ramesh Kumar."
print("RTI Text:", test_text)

# 1. Routing
print("\n--- Running Agent 1 (Jurisdiction Routing) ---")
routing_res = classify_department(test_text)
print(f"Primary Dept: {routing_res.primary_department} ({routing_res.confidence_band})")

# 2. Extractor
print("\n--- Running Agent 2 (Information Extraction) ---")
ext_res = extract_information(test_text)
print(f"Info Type: {ext_res.information_type}")
print(f"Personal Data: {ext_res.personal_data}")

# 3. Layer A Rules
print("\n--- Running Agent 3 - Layer A (Exemption Triggers) ---")
rules_res = evaluate_exemptions(ext_res)
rule_flags = [flag.section for flag in rules_res]
print(f"Triggered Rule Flags: {rule_flags}")

# 4. Layer B LLM Analyzer
print("\n--- Running Agent 3 - Layer B (LLM Exemption Analyzer via RAG) ---")
layer_b_res = analyze_exemption_applicability(test_text, rule_flags)
print(f"Overall Explanation:\n{layer_b_res.overall_explanation}")
for ea in layer_b_res.exemptions_analysis:
    print(f" - {ea.section} (is_applicable: {ea.is_applicable}, conf: {ea.confidence_score})")
    print(f"   Reasoning: {ea.legal_reasoning}")
    print(f"   Quotes: {ea.exact_quotes}")

# 5. Balancer
print("\n--- Running Agent 4 (Adversarial Disclosure Balancer) ---")
balance_res = compute_disclosure_balance(test_text, rule_flags)
print(f"Pro-Disclosure argument: {balance_res.pro_disclosure_argument}")
print(f"Pro-Exemption argument: {balance_res.pro_exemption_argument}")
print(f"Weighing factors: {balance_res.balancing_factors}")

# 6. Recommendation
print("\n--- Running Agent 5 (Recommendation Generator) ---")
final_recom = generate_final_recommendation(test_text, routing_res, ext_res, layer_b_res, balance_res)
print(f"Recommended Action: {final_recom.recommendation} ({final_recom.confidence_band})")
print(f"Reasoning:\n{final_recom.primary_reasoning}")
print(f"Citations: {final_recom.sections_applied}")
print(f"Suggested Timeline Action: {final_recom.suggested_pio_action}")
print(f"Disclosure Risk: {final_recom.disclosure_risk}")
print(f"Rejection Risk: {final_recom.rejection_risk}")

print("\n=== PIPELINE VERIFICATION SUCCESS ===")
