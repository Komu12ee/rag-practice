import os
import sys
import json
import urllib.request
from pathlib import Path

# Force UTF-8 encoding on stdout
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "backend"))

from routing import _load_chips_report, _load_departments
from sarvam_client import SARVAM_API_KEY, SARVAM_API_URL, SARVAM_MODEL

def call_raw(query: str):
    chips_report = _load_chips_report()
    if len(chips_report) > 12000:
        chips_report = chips_report[:12000] + "\n... [truncated]"
        
    departments = _load_departments()
    dept_list_items = []
    for d in departments:
        d_id = d.get("department_id", d.get("id"))
        d_name = d.get("department_name_en", d.get("name_en", d_id))
        dept_list_items.append(f'"{d_id}": "{d_name}"')
    formatted_depts = "{\n  " + ",\n  ".join(dept_list_items) + "\n}"
    
    prompt = (
        "You are an expert Public Information Officer's routing assistant for Chhattisgarh, India.\n"
        "Your task is to classify an RTI application text to the correct government department.\n\n"
        "REFERENCE CONTEXT ON CHIPS SERVICES & LIMITATIONS:\n"
        f"{chips_report}\n\n"
        "CRITICAL RULES FOR CLASSIFICATION:\n"
        "1. CHiPS (Ministry of Information Technology/CHiPS) is a technology promotion society and an IT implementation agency. It builds and maintains digital platforms (like e-District, UPAHAR, Khanij Online, Sewa Setu, e-Procurement, State Data Centre, CG-SWAN, Aadhaar facilitation).\n"
        "2. CHiPS does NOT own or have authority to deliver the underlying data or process approvals for citizens on these platforms.\n"
        "   - Example: Aadhaar. CHiPS is responsible for creating/managing Aadhaar infrastructure in the state, but if a person asks \"why was my Aadhaar delayed?\" or \"why did I not receive my Aadhaar card?\", the data delivery and administrative authority is NOT CHiPS. The RTI must be routed to the concerned department/agency (e.g. UIDAI or Home Department/General Administration Department).\n"
        "   - Example 2: Caste, Income, or Domicile certificates. e-District processes these online. However, the authority to approve, issue, or explain delays on certificates is the Revenue Department, NOT CHiPS.\n"
        "   - Example 3: UPAHAR. Commisioned by Director of Land Records. Any land record details or delays belong to the Revenue Department (Land Records), NOT CHiPS.\n"
        "   - Example 4: Khanij Online 2.0. Developed on behalf of Geology and Mining. Any mining permit details, royalties, or transport audits belong to the Mineral Resources Department, NOT CHiPS.\n"
        "   - Example 5: Sewa Setu or e-Procurement. If an applicant asks for details of bids, tenders, or registrations belonging to another government department, it belongs to that specific department, NOT CHiPS.\n"
        "3. CHiPS is ONLY responsible for queries directly related to:\n"
        "   - Its own internal administrative, personnel, and HR records (employee details, salaries, sanctioned posts, service rules).\n"
        "   - Its own financial audits, balance sheets, and CAG audit records.\n"
        "   - Signed project agreements, contract copies, work orders, service level agreements (SLAs), and project completion reports with system integrators.\n"
        "   - State Data Centre physical equipment inventories, server procurement agreements, utility consumption, and technical standard operating procedures (excluding raw databases or source codes).\n\n"
        "LIST OF VALID DEPARTMENTS (Output department_id MUST be one of the keys in this JSON):\n"
        f"{formatted_depts}\n\n"
        "RTI APPLICATION TEXT:\n"
        f"{query}\n\n"
        "Determine the primary department and the top 4 runner-up departments that have the statutory authority to deliver the requested information.\n\n"
        "Respond ONLY in JSON format with the following keys:\n"
        "{\n"
        '  "primary_department": "dept_id_from_the_keys",\n'
        '  "department_name": "exact_value_from_the_dictionary",\n'
        '  "confidence_band": "HIGH/MEDIUM/LOW",\n'
        '  "confidence_score": 0.95,\n'
        '  "reasoning": "Step-by-step reasoning explaining why the primary department was selected and why CHiPS was or was not chosen based on the rules. Separate distinct reasoning steps with a pipe character \'|\'.",\n'
        '  "alternative_departments": [\n'
        '    {"department_id": "dept_id", "department_name": "dept_name", "score": 0.85},\n'
        '    {"department_id": "dept_id", "department_name": "dept_name", "score": 0.75},\n'
        '    {"department_id": "dept_id", "department_name": "dept_name", "score": 0.65},\n'
        '    {"department_id": "dept_id", "department_name": "dept_name", "score": 0.55}\n'
        "  ]\n"
        "}\n"
        "Ensure that the JSON is properly formatted, and there is absolutely no other text in the response."
    )
    
    payload = {
        "model": SARVAM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "api-subscription-key": SARVAM_API_KEY
    }
    
    req = urllib.request.Request(
        SARVAM_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = response.read().decode("utf-8")
            res_json = json.loads(res_data)
            print("\nKeys in res_json:", res_json.keys())
            if "choices" in res_json:
                msg = res_json["choices"][0]["message"]
                print("Keys in choices[0][message]:", msg.keys())
                print("Content:", type(msg.get("content")), repr(msg.get("content"))[:300])
                print("Reasoning Content:", type(msg.get("reasoning_content")), repr(msg.get("reasoning_content"))[:300])
                print("Finish Reason:", res_json["choices"][0].get("finish_reason"))
            else:
                print("Response:", res_json)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    call_raw("why i don't get my adhar why it is getting delay")
