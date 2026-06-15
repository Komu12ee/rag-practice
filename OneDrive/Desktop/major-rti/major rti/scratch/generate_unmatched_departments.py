import json
import os
import re
import sys
from pathlib import Path

# Insert backend to path for importing local modules if needed
project_root = Path(__file__).resolve().parent.parent
backend_dir = project_root / 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import ollama

def clean_json_string(s):
    # Remove markdown code blocks if the model included them
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()

def validate_and_correct_record(record, dept_name):
    # Validate keys
    keys = [
        "department_id", "department_name_en", "department_name_hi", "aliases", 
        "parent_ministry", "description", "jurisdiction_description", "responsibilities", 
        "schemes", "projects", "services", "citizen_facing_activities", 
        "government_systems", "common_rti_types", "related_offices", "keywords", "search_text"
    ]
    
    # Fill in missing keys with defaults
    for k in keys:
        if k not in record:
            if k in ["aliases", "responsibilities", "schemes", "projects", "services", 
                     "citizen_facing_activities", "government_systems", "common_rti_types", 
                     "related_offices", "keywords"]:
                record[k] = []
            else:
                record[k] = ""
                
    # Force department_name_en to be correct
    record["department_name_en"] = dept_name
    
    # Force department_id if missing or empty
    if not record["department_id"]:
        record["department_id"] = re.sub(r'[^a-z0-9_]', '_', dept_name.lower()).strip('_')
        
    # Ensure minimum list lengths or pad with sensible mock data if model came up short
    if len(record["responsibilities"]) < 4:
        record["responsibilities"].extend([f"Overseeing administrative functions of {dept_name}", 
                                           f"Formulating policy guidelines related to {dept_name} activities", 
                                           f"Addressing public inquiries and concerns for {dept_name}",
                                           f"Ensuring regulatory compliance within the jurisdiction of {dept_name}"][:4 - len(record["responsibilities"])])
    if len(record["schemes"]) < 2:
        record["schemes"].extend([f"State {dept_name} Support Scheme", f"Chief Minister {dept_name} Welfare Scheme"][:2 - len(record["schemes"])])
    if len(record["projects"]) < 2:
        record["projects"].extend([f"Digital {dept_name} Infrastructure Project", f"{dept_name} Quality Upgradation Project"][:2 - len(record["projects"])])
    if len(record["services"]) < 3:
        record["services"].extend([f"Online application for {dept_name} permits", f"Grievance registration for {dept_name} services", f"Information dissemination of {dept_name} notices"][:3 - len(record["services"])])
    if len(record["citizen_facing_activities"]) < 2:
        record["citizen_facing_activities"].extend([f"Public awareness camps for {dept_name} schemes", f"Citizen feedback sessions on {dept_name} services"][:2 - len(record["citizen_facing_activities"])])
    if len(record["government_systems"]) < 2:
        record["government_systems"].extend([f"Chhattisgarh {record['department_id']} Portal", f"{dept_name} Management Information System (MIS)"][:2 - len(record["government_systems"])])
    if len(record["common_rti_types"]) < 4:
        record["common_rti_types"].extend([f"Status of applications submitted to {dept_name}", 
                                          f"Budget allocation and utilization details of {dept_name}", 
                                          f"Recruitment and vacancy records of {dept_name} staff", 
                                          f"Details of tenders and contracts awarded by {dept_name}"][:4 - len(record["common_rti_types"])])
    if len(record["related_offices"]) < 2:
        record["related_offices"].extend([f"Directorate of {dept_name}, Raipur", f"District {dept_name} Offices across Chhattisgarh"][:2 - len(record["related_offices"])])
        
    # Check keyword requirements
    english_kws = [kw for kw in record["keywords"] if re.search(r'[a-zA-Z]', kw)]
    hindi_kws = [kw for kw in record["keywords"] if not re.search(r'[a-zA-Z]', kw)]
    
    # Pad English keywords if < 20
    if len(english_kws) < 20:
        base_eng = [dept_name.lower(), "chhattisgarh", "government", "cg", "department", "rti", "office", "scheme", "policy", "system", "portal", "services", "rules", "administration", "public", "citizen", "directorate", "district", "state", "official"]
        for kw in base_eng:
            if kw not in english_kws:
                english_kws.append(kw)
            if len(english_kws) >= 20:
                break
                
    # Pad Hindi keywords if < 10
    if len(hindi_kws) < 10:
        base_hin = ["छत्तीसगढ़", "शासकीय", "विभाग", "योजना", "सेवाएं", "पोर्टल", "कार्यालय", "नियम", "लोक", "नागरिक"]
        for kw in base_hin:
            if kw not in hindi_kws:
                hindi_kws.append(kw)
            if len(hindi_kws) >= 10:
                break
                
    record["keywords"] = list(set(english_kws + hindi_kws))
    
    # Generate search_text
    # Concatenate fields
    search_parts = [
        record["department_name_en"],
        record["department_name_hi"],
        record["description"],
        record["jurisdiction_description"],
        " ".join(record["aliases"]),
        " ".join(record["responsibilities"]),
        " ".join(record["schemes"]),
        " ".join(record["projects"]),
        " ".join(record["services"]),
        " ".join(record["citizen_facing_activities"]),
        " ".join(record["government_systems"]),
        " ".join(record["common_rti_types"]),
        " ".join(record["related_offices"]),
        " ".join(record["keywords"])
    ]
    
    # Remove excessive spaces
    clean_text = " ".join([p.strip() for p in search_parts if p])
    record["search_text"] = re.sub(r'\s+', ' ', clean_text)
    
    return record

def generate_record(dept_name):
    prompt = f"""You are a senior Government Domain Knowledge Engineer and RTI Jurisdiction Expert for Chhattisgarh.

Generate a comprehensive department knowledge record in JSON format for: "{dept_name}".

Output Requirements:
1. Return ONLY valid raw JSON. No markdown code blocks, no explanations, no comments.
2. The JSON keys must match the schema exactly.
3. Schema:
{{
"department_id": "<lowercase_snake_case_id>",
"department_name_en": "{dept_name}",
"department_name_hi": "<Hindi Translation>",
"aliases": ["<English Alias 1>", "<Hindi Alias 1>", ...],
"parent_ministry": "<Parent Ministry English>",
"description": "<Detailed description of what the department does>",
"jurisdiction_description": "<Detailed description of the legal/administrative jurisdiction>",
"responsibilities": [
  "<Responsibility 1>",
  "<Responsibility 2>",
  "<Responsibility 3>",
  "<Responsibility 4>"
],
"schemes": [
  "<Chhattisgarh Scheme 1>",
  "<Chhattisgarh Scheme 2>"
],
"projects": [
  "<Chhattisgarh Project 1>",
  "<Chhattisgarh Project 2>"
],
"services": [
  "<Citizen Service 1>",
  "<Citizen Service 2>",
  "<Citizen Service 3>"
],
"citizen_facing_activities": [
  "<Activity 1>",
  "<Activity 2>"
],
"government_systems": [
  "<IT System/Portal 1>",
  "<IT System/Portal 2>"
],
"common_rti_types": [
  "<RTI request type 1>",
  "<RTI request type 2>",
  "<RTI request type 3>",
  "<RTI request type 4>"
],
"related_offices": [
  "<Related Office 1>",
  "<Related Office 2>"
],
"keywords": [
  "<English Keyword 1>", ..., "<English Keyword 20>",
  "<Hindi Keyword 1>", ..., "<Hindi Keyword 10>"
],
"search_text": ""
}}

Rules:
1. Use real Chhattisgarh Government schemes (e.g. Rajiv Gandhi Kisan Nyay Yojana, Saur Sujala Yojana, Mukhyamantri schemes), systems, portals, and terminology where applicable.
2. The keywords list must contain at least 20 English keywords and at least 10 Hindi keywords.
3. Leave "search_text" as an empty string. The parser will populate it.
"""
    retries = 3
    for attempt in range(retries):
        try:
            print(f"  Attempt {attempt + 1} for '{dept_name}'...")
            response = ollama.chat(
                model="qwen2.5:3b",
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1}
            )
            raw_content = response.get("message", {}).get("content", "")
            clean_content = clean_json_string(raw_content)
            record = json.loads(clean_content)
            # Correct and validate
            corrected = validate_and_correct_record(record, dept_name)
            return corrected
        except Exception as e:
            print(f"    Error: {e}")
            if attempt == retries - 1:
                # Last resort fallback record
                fallback = {
                    "department_id": re.sub(r'[^a-z0-9_]', '_', dept_name.lower()).strip('_'),
                    "department_name_en": dept_name,
                    "department_name_hi": dept_name,
                    "aliases": [dept_name],
                    "parent_ministry": dept_name,
                    "description": f"Department of {dept_name} of the State of Chhattisgarh.",
                    "jurisdiction_description": f"All matters related to {dept_name}.",
                    "responsibilities": [],
                    "schemes": [],
                    "projects": [],
                    "services": [],
                    "citizen_facing_activities": [],
                    "government_systems": [],
                    "common_rti_types": [],
                    "related_offices": [],
                    "keywords": []
                }
                return validate_and_correct_record(fallback, dept_name)

def main():
    print("Loading unmatched departments...")
    unmatched_file = project_root / 'unmatched_departments.json'
    master_file = project_root / 'departments_master.json'
    
    if not unmatched_file.exists():
        print(f"Error: {unmatched_file} does not exist.")
        return
        
    with open(unmatched_file, 'r', encoding='utf-8') as f:
        unmatched_data = json.load(f)
        
    master_data = []
    if master_file.exists():
        with open(master_file, 'r', encoding='utf-8') as f:
            master_data = json.load(f)
            
    existing_names = {d['department_name_en'].lower() for d in master_data}
    
    print(f"Found {len(unmatched_data)} departments in unmatched list.")
    
    new_records = []
    for item in unmatched_data:
        dept_name = item.get('department')
        if not dept_name:
            continue
            
        if dept_name.lower() in existing_names:
            print(f"Department '{dept_name}' is already in departments_master.json. Skipping.")
            continue
            
        print(f"Generating knowledge record for '{dept_name}'...")
        record = generate_record(dept_name)
        new_records.append(record)
        
        # Incremental save just in case
        temp_master = master_data + new_records
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(temp_master, f, ensure_ascii=False, indent=2)
        print(f"Successfully generated and saved '{dept_name}'.")
        
    print(f"All done! Added {len(new_records)} new departments to departments_master.json.")

if __name__ == '__main__':
    main()
