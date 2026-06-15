with open("frontend/app.py", "r", encoding="utf-8") as f:
    results = []
    for i, line in enumerate(f):
        if "Confirmed Parameters" in line or "Extracted Entities" in line or "JURISDICTION REASONING" in line or "Jurisdiction Reasoning" in line or "jurisdiction_reasoning" in line or "extracted_entities" in line or "Confirmed info" in line or "Confirmed Info" in line:
            results.append(f"Line {i+1}: {line.strip()}")

with open("scratch/find_messy_output.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(results))
