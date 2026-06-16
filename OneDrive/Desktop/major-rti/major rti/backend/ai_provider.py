"""Configurable AI provider layer for development and production.

Provider selection is controlled by environment variables set by run.py:
    RTI_AI_PROVIDER=sarvam | ollama | mock
    RTI_AI_MODEL=<provider model name>

The rest of the backend should keep using sarvam_client.call_sarvam_chat for
backward compatibility. That wrapper delegates to this module.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str
    model: str
    sarvam_api_key: str
    sarvam_api_url: str
    ollama_base_url: str
    timeout_seconds: int
    retries: int


class AIProvider(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        *,
        timeout: int | None = None,
        retries: int | None = None,
        mode: str = "chat",
        max_tokens: int = 4096,
    ) -> str:
        ...


def load_config() -> AIProviderConfig:
    provider = os.getenv("RTI_AI_PROVIDER", os.getenv("AI_PROVIDER", "sarvam")).strip().lower()
    model_default = "sarvam-105b" if provider == "sarvam" else "qwen2.5:14b"
    return AIProviderConfig(
        provider=provider,
        model=os.getenv("RTI_AI_MODEL", os.getenv("SARVAM_MODEL", model_default)).strip(),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", "").strip(),
        sarvam_api_url=os.getenv("SARVAM_API_URL", "https://api.sarvam.ai/v1/chat/completions").strip(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", os.getenv("SARVAM_TIMEOUT_SECONDS", "90"))),
        retries=int(os.getenv("AI_RETRIES", os.getenv("SARVAM_RETRIES", "2"))),
    )


def get_provider(config: AIProviderConfig | None = None) -> AIProvider:
    cfg = config or load_config()
    if cfg.provider == "mock":
        return MockProvider(cfg)
    if cfg.provider == "ollama":
        return OllamaProvider(cfg)
    if cfg.provider == "sarvam":
        return SarvamProvider(cfg)
    raise ValueError(f"Unsupported RTI_AI_PROVIDER: {cfg.provider}. Use sarvam, ollama, or mock.")


class SarvamProvider:
    def __init__(self, config: AIProviderConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        *,
        timeout: int | None = None,
        retries: int | None = None,
        mode: str = "chat",
        max_tokens: int = 4096,
    ) -> str:
        if not self.config.sarvam_api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured. Use --provider mock/ollama for no-cost development.")
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.sarvam_api_key}",
            "api-subscription-key": self.config.sarvam_api_key,
        }
        return _post_chat_json(
            url=self.config.sarvam_api_url,
            payload=payload,
            headers=headers,
            timeout=timeout or self.config.timeout_seconds,
            retries=retries or self.config.retries,
            mode=mode,
            extractor=_extract_openai_content,
        )


class OllamaProvider:
    def __init__(self, config: AIProviderConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        *,
        timeout: int | None = None,
        retries: int | None = None,
        mode: str = "chat",
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        return _post_chat_json(
            url=f"{self.config.ollama_base_url}/api/chat",
            payload=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout or self.config.timeout_seconds,
            retries=retries or self.config.retries,
            mode=mode,
            extractor=_extract_ollama_content,
        )


class MockProvider:
    """Deterministic no-cost provider for UI and workflow development."""

    def __init__(self, config: AIProviderConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        *,
        timeout: int | None = None,
        retries: int | None = None,
        mode: str = "chat",
        max_tokens: int = 4096,
    ) -> str:
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        logger.info("Mock AI response | mode=%s chars=%s", mode, len(prompt))
        return mock_response_for_prompt(prompt, mode=mode)


def mock_response_for_prompt(prompt: str, mode: str = "chat") -> str:
    lower = prompt.lower()
    if "extracted_entities" in lower and "information_type" in lower:
        return json.dumps(
            {
                "extracted_entities": ["Mock Applicant", "CHiPS"],
                "information_type": "other",
                "systems": ["Mock System"],
                "procurement_status": "none",
                "personal_data": False,
                "public_interest_override": False,
                "explanation": "Mock extraction generated for development mode.",
            }
        )
    if "primary_department" in lower and "alternative_departments" in lower:
        return json.dumps(
            {
                "primary_department": "chips",
                "department_name": "CHiPS (Chhattisgarh Infotech Promotion Society)",
                "confidence_score": 0.9,
                "reasoning": ["Mock routing selected CHiPS for workflow testing."],
                "alternative_departments": [
                    {
                        "department_id": "wcd",
                        "department_name": "Women & Child Development Department",
                        "score": 0.55,
                    }
                ],
            }
        )
    if "exemptions_analysis" in lower:
        return json.dumps(
            {
                "exemptions_analysis": [],
                "overall_explanation": "Mock statutory analysis generated for testing.",
            }
        )
    if "pro_disclosure_argument" in lower and "pro_exemption_argument" in lower:
        return json.dumps(
            {
                "pro_disclosure_argument": "Mock disclosure argument for UI testing.",
                "pro_exemption_argument": "Mock exemption argument for UI testing.",
                "balancing_factors": "Mock balancing factors for workflow testing.",
            }
        )
    if "recommended_action" in lower or "requires_third_party_notice" in lower:
        return json.dumps(
            {
                "recommended_action": "APPROVE",
                "confidence_band": "MEDIUM",
                "reasoning": "Mock synthesis generated for testing only.",
                "sections_applied": [],
                "applicable_exemptions": [],
                "inapplicable_exemptions": [],
                "disclosure_risk": "Mock disclosure risk.",
                "rejection_risk": "Mock rejection risk.",
                "suggested_pio_action": "Review the mock output; no statutory decision is made.",
                "requires_third_party_notice": False,
                "requires_legal_consultation": False,
            }
        )
    if "letter_body" in lower and "rti_summary" in lower:
        return json.dumps(
            {
                "applicant_name": "The Applicant",
                "applicant_address": "Address not specified",
                "rti_summary": "Mock RTI request summary",
                "letter_body": "Mock RTI response generated for testing. This is not a statutory decision.",
            }
        )
    if "return only valid json" in lower or mode == "structured_extraction":
        return json.dumps({"decision": "TEST", "draft": "Mock JSON response generated for testing."})
    return (
        "Mock RTI response generated for testing.\n\n"
        "This system is running in mock mode. No Sarvam or Ollama call was made. "
        "The final decision under the RTI Act, 2005 remains with the concerned PIO."
    )


def _post_chat_json(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    retries: int,
    mode: str,
    extractor,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            logger.info("Calling AI provider | mode=%s url=%s attempt=%s", mode, url, attempt)
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = extractor(data)
            if not content:
                raise RuntimeError("AI provider returned empty content.")
            return content
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            last_error = RuntimeError(f"HTTP {exc.code}: {body}")
            if exc.code < 500 and exc.code not in {408, 429}:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
        if attempt < max(1, retries):
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"AI provider call failed after {max(1, retries)} attempt(s): {last_error}")


def _extract_openai_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Provider returned no choices: {data}")
    message = choices[0].get("message") or {}
    return str(message.get("content") or message.get("reasoning_content") or "").strip()


def _extract_ollama_content(data: dict[str, Any]) -> str:
    message = data.get("message") or {}
    content = message.get("content")
    if content is None:
        content = data.get("response", "")
    return str(content or "").strip()
