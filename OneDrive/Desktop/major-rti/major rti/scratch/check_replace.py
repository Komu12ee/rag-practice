with open("frontend/app.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if ".replace(" in line:
            print(f"Line {i+1}: {line.strip()}")
