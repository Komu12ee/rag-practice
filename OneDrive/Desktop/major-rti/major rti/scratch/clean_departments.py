import json
import re
from pathlib import Path

def main():
    master_file = Path('departments_master.json')
    if not master_file.exists():
        print("Master file not found.")
        return
        
    with open(master_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    cleaned = []
    seen = set()
    
    for d in data:
        name = d.get('department_name_en')
        desc = d.get('description', '')
        
        # 1. Correct the name and ID for the Higher Education Department (wrongly labeled as School Education Department)
        if name == 'School Education Department' and 'state colleges' in desc:
            d['department_id'] = 'higher_education'
            d['department_name_en'] = 'Higher Education Department'
            d['department_name_hi'] = 'उच्च शिक्षा विभाग'
            
        # 2. Correct the name and ID for the Medical Education Department (wrongly labeled as School Education Department)
        elif name == 'School Education Department' and 'medical colleges' in desc:
            d['department_id'] = 'medical_education'
            d['department_name_en'] = 'Medical Education Department'
            d['department_name_hi'] = 'चिकित्सा शिक्षा विभाग'
            
        name = d.get('department_name_en')
        ident = (d.get('department_id'), name)
        
        if ident not in seen:
            seen.add(ident)
            cleaned.append(d)
            
    with open(master_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
        
    print(f"Original elements: {len(data)}")
    print(f"Cleaned unique elements: {len(cleaned)}")

if __name__ == '__main__':
    main()
