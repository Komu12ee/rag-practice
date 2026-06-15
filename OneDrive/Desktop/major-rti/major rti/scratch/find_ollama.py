import os

results = []
for root, dirs, files in os.walk("backend"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if "ollama" in line.lower():
                        results.append(f"{path}:{i+1}: {line.strip()}")

with open("scratch/find_ollama_output.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(results))
