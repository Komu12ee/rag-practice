with open("frontend/app.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "generate_pio_draft" in line or "pio_draft" in line:
            print(f"{i+1}: {line.strip()}")
