import sys
import os
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "backend"))

# Redirect stdout and stderr to a log file
log_dir = root_dir / "scratch"
log_dir.mkdir(exist_ok=True)
log_file = open(log_dir / "backend_persistent.log", "w", encoding="utf-8", buffering=1)
sys.stdout = log_file
sys.stderr = log_file

import uvicorn

try:
    print("[start_backend.py] Starting backend server...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8002)
except Exception as e:
    print(f"[start_backend.py] Failed to start backend: {e}")
