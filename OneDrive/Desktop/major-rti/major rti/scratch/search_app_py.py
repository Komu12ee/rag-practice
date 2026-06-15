with open(r"c:\Users\hp\projects\rti-project\offline\rti\frontend\app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "tilt" in line.lower():
        clean_line = "".join(c for c in line.strip() if ord(c) < 128)
        print(f"Line {i+1}: {clean_line}")
