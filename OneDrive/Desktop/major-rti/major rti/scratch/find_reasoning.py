with open("frontend/app.py", "r", encoding="utf-8") as f:
    results = []
    for i, line in enumerate(f):
        if ".reasoning" in line:
            results.append(f"Line {i+1}: {line.strip()}")

with open("scratch/find_reasoning_output.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(results))
