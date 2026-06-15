import os
import json
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)

# Load configuration from environment variables with defaults
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_hhusezzy_cnfsLw6EbCOox523LJGXm15G")
# SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_0mfxhg3i_JT6kA0PStfJJ7z2mN2OIl5Mc")

SARVAM_MODEL = os.getenv("SARVAM_MODEL", "sarvam-105b")
SARVAM_API_URL = os.getenv("SARVAM_API_URL", "https://api.sarvam.ai/v1/chat/completions")

print(f"[Sarvam AI Initialize] Centralized Client Loaded (Model: {SARVAM_MODEL})")

def call_sarvam_chat(messages: list, temperature: float = 0.1) -> str:
    """
    Call Sarvam AI's OpenAI-compatible completions endpoint.
    Degrades gracefully by raising a RuntimeError if the call fails.
    """
    print(f"\n[Sarvam AI Request] Calling {SARVAM_MODEL}...")
    print(f"[Sarvam AI Request] URL: {SARVAM_API_URL}")
    print(f"[Sarvam AI Request] Payload Messages Count: {len(messages)}")
    
    payload = {
        "model": SARVAM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "api-subscription-key": SARVAM_API_KEY
    }
    
    req = urllib.request.Request(
        SARVAM_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            res_data = response.read().decode("utf-8")
            res_json = json.loads(res_data)
            
            choices = res_json.get('choices')
            if not choices:
                raise RuntimeError(f"API returned response without choices: {res_json}")
                
            msg = choices[0].get('message', {})
            raw_content = msg.get('content')
            if raw_content is None:
                # If content is null, fallback to reasoning_content if available, or empty string
                raw_content = msg.get('reasoning_content') or ""
                
            content = raw_content.strip()
            print(f"[Sarvam AI Response] Received {len(content)} characters successfully.")
            return content
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        err_msg = f"HTTP Error {e.code}: {error_body}"
        print(f"[Sarvam AI Error] {err_msg}")
        raise RuntimeError(err_msg)
    except Exception as e:
        err_msg = f"API call failed: {str(e)}"
        print(f"[Sarvam AI Error] {err_msg}")
        raise RuntimeError(err_msg)
