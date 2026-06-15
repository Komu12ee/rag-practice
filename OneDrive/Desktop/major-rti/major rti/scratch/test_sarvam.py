import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sarvam_client import call_sarvam_chat

print("[test_sarvam.py] Starting connection test to Sarvam AI completions API...")

test_messages = [
    {
        "role": "user",
        "content": "You are a routing helper. Respond with ONLY 'OK' in a JSON object: {\"status\": \"OK\"}"
    }
]

try:
    print("[test_sarvam.py] Triggering API call...")
    response = call_sarvam_chat(test_messages, temperature=0.1)
    print("\n[test_sarvam.py] API CALL SUCCESSFUL!")
    print(f"[test_sarvam.py] Response received:\n{response}")
except Exception as e:
    print("\n[test_sarvam.py] API CALL FAILED!")
    print(f"[test_sarvam.py] Error details: {str(e)}")
