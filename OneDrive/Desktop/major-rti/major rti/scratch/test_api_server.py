"""
Test Script to Verify FastAPI endpoints.
=========================================
Performs requests against http://localhost:8000 to validate API mapping 
and integration correctness.
"""

import json
import urllib.request
import urllib.error

API_URL = "http://localhost:8000/api"

def make_request(path: str, data: dict = None) -> dict:
    url = f"{API_URL}{path}"
    headers = {"Content-Type": "application/json"}
    
    req_body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_body, headers=headers, method="POST" if data else "GET")
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code} on {path}: {e.read().decode('utf-8')}")
        raise e
    except Exception as e:
        print(f"Connection error on {path}: {str(e)}")
        raise e

def test_pipeline():
    print("=== STARTING API GATEWAY VALIDATION ===")
    
    # 1. Health check
    print("\n1. Testing /api/health...")
    health = make_request("/health")
    print("Response:", health)
    assert health.get("status") == "ok"
    
    # 2. Routing
    test_text = "Please provide the private medical files and bank account details of government employee Ramesh Kumar."
    print("\n2. Testing /api/route...")
    route = make_request("/route", {"text": test_text, "language": "en"})
    print("Route Primary Dept:", route.get("primary_department"))
    print("Route Confidence:", route.get("confidence"))
    print("Route Alternatives:", route.get("alternatives"))
    
    # 3. Extraction
    print("\n3. Testing /api/extract...")
    extract = make_request("/extract", {"text": test_text})
    print("Extracted Info Type:", extract.get("classification_type"))
    print("Extracted Entities:", extract.get("entities"))
    print("Extracted Systems:", extract.get("systems"))
    print("Extracted Personal Data:", extract.get("personal_data"))
    print("Extracted Public Interest:", extract.get("public_interest"))
    
    # 4. Exemption rules evaluation
    print("\n4. Testing /api/evaluate_exemptions...")
    evaluation = make_request("/evaluate_exemptions", extract)
    print("Final Action Recommendation:", evaluation.get("final_recom", {}).get("action"))
    print("Citations Mapped:", evaluation.get("final_recom", {}).get("citations"))
    print("Balancing Factors:", evaluation.get("balance_res", {}).get("balancing_factors")[:100], "...")
    print("Layer B references count:", len(evaluation.get("layer_b_res", [])))
    
    # 5. Log final decision
    print("\n5. Testing /api/log_decision...")
    audit_payload = {
        "pio_action_taken": "OVERRIDDEN",
        "override_department": "chips",
        "reasoning_notes": "We are overriding the rejection for verification testing purposes.",
        "extracted_info": extract,
        "routing": route,
        "evaluation": evaluation
    }
    log_res = make_request("/log_decision", audit_payload)
    print("Logged Decision ID:", log_res.get("audit_id"))
    print("Logged Cryptographic Block Hash:", log_res.get("current_hash"))
    
    print("\n=== ALL ENDPOINTS VERIFIED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_pipeline()
