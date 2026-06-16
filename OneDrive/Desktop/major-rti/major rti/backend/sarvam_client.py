"""Backward-compatible AI client wrapper.

Historically backend modules imported this file directly. It now delegates to
backend.ai_provider so development can switch between Sarvam, local Ollama, and
mock mode without touching feature code.
"""

from __future__ import annotations

from ai_provider import get_provider, load_config


_CONFIG = load_config()

AI_PROVIDER = _CONFIG.provider
SARVAM_MODEL = _CONFIG.model
SARVAM_API_URL = _CONFIG.sarvam_api_url
DEFAULT_TIMEOUT_SECONDS = _CONFIG.timeout_seconds
DEFAULT_RETRIES = _CONFIG.retries

# Existing modules use `if not SARVAM_API_KEY` to decide whether to skip LLM.
# For ollama/mock this must be truthy so the provider can handle the call.
SARVAM_API_KEY = _CONFIG.sarvam_api_key if _CONFIG.provider == "sarvam" else "__LOCAL_OR_MOCK_PROVIDER__"


class SarvamConfigurationError(RuntimeError):
    """Kept for compatibility with older imports."""


def call_sarvam_chat(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    mode: str = "draft_generation",
    max_tokens: int = 4096,
) -> str:
    provider = get_provider(_CONFIG)
    return provider.chat(
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        retries=retries,
        mode=mode,
        max_tokens=max_tokens,
    )


def call_sarvam_structured_extraction(prompt: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
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
