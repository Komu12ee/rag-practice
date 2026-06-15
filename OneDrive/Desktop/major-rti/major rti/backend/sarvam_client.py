"""Small production-safe Sarvam client used by the FastAPI backend.

Configuration is environment-only. Do not put API keys in source code.
Required:
    SARVAM_API_KEY
Optional:
    SARVAM_MODEL, SARVAM_API_URL, SARVAM_TIMEOUT_SECONDS, SARVAM_RETRIES
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any


logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_MODEL = os.getenv("SARVAM_MODEL", "sarvam-105b").strip()
SARVAM_API_URL = os.getenv("SARVAM_API_URL", "https://api.sarvam.ai/v1/chat/completions").strip()
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("SARVAM_TIMEOUT_SECONDS", "90"))
DEFAULT_RETRIES = int(os.getenv("SARVAM_RETRIES", "2"))


class SarvamConfigurationError(RuntimeError):
    """Raised when Sarvam cannot be called because configuration is missing."""


def call_sarvam_chat(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    mode: str = "draft_generation",
    max_tokens: int = 4096,
) -> str:
    """Call Sarvam chat completions with timeout, retry, and structured errors."""
    if not SARVAM_API_KEY:
        raise SarvamConfigurationError("SARVAM_API_KEY is not configured. Set it in the environment before calling Sarvam.")
    if not messages:
        raise ValueError("messages cannot be empty")

    payload = {
        "model": SARVAM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "api-subscription-key": SARVAM_API_KEY,
    }

    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            logger.info("Calling Sarvam | mode=%s model=%s attempt=%s", mode, SARVAM_MODEL, attempt)
            request = urllib.request.Request(
                SARVAM_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = _extract_content(data)
            logger.info("Sarvam response received | mode=%s chars=%s", mode, len(content))
            return content
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            last_error = RuntimeError(f"Sarvam HTTP {exc.code}: {body}")
            if exc.code < 500 and exc.code not in {408, 429}:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc

        if attempt < max(1, retries):
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError(f"Sarvam call failed after {max(1, retries)} attempt(s): {last_error}")


def call_sarvam_structured_extraction(prompt: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Wrapper for future parser fallback calls that need strict JSON output."""
    return call_sarvam_chat(
        messages=[
            {"role": "system", "content": "Return only valid JSON. Do not include markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        timeout=timeout,
        mode="structured_extraction",
        max_tokens=3072,
    )


def call_sarvam_draft_generation(prompt: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Wrapper for formal RTI draft generation."""
    return call_sarvam_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an RTI legal research and drafting assistant. "
                    "Do not make the final PIO decision."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        timeout=timeout,
        mode="draft_generation",
    )


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not choices:
        raise RuntimeError(f"Sarvam returned no choices: {data}")
    message = choices[0].get("message") or {}
    raw_content = message.get("content") or message.get("reasoning_content") or ""
    content = str(raw_content).strip()
    if not content:
        raise RuntimeError("Sarvam returned an empty response.")
    return content
