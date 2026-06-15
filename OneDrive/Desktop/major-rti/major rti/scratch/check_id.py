import os

patterns = ["['id']", '["id"]', "['name_en']", '["name_en"]', "['name_hi']", '["name_hi"]', ".get('id')", '.get("id")', ".get('name_en')", '.get("name_en")', ".get('name_hi')", '.get("name_hi")']

for root, dirs, files in os.walk("."):
    if ".venv" in root or "__pycache__" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py") and file != "check_id.py":
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if any(pat in line for pat in patterns):
                            print(f"{path}:{i+1}: {line.strip()}")
            except Exception as e:
                pass
