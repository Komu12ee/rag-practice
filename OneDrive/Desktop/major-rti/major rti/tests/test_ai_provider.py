from backend.ai_provider import AIProviderConfig, MockProvider, get_provider, mock_response_for_prompt


def _config(provider: str = "mock") -> AIProviderConfig:
    return AIProviderConfig(
        provider=provider,
        model="mock",
        sarvam_api_key="",
        sarvam_api_url="https://example.invalid",
        ollama_base_url="http://127.0.0.1:11434",
        timeout_seconds=1,
        retries=1,
    )


def test_mock_provider_returns_deterministic_draft_without_api():
    provider = get_provider(_config("mock"))
    assert isinstance(provider, MockProvider)
    content = provider.chat([{"role": "user", "content": "Draft a reply"}])
    assert "Mock RTI response generated for testing" in content


def test_mock_provider_returns_extraction_json_shape():
    content = mock_response_for_prompt(
        'Return JSON with "extracted_entities", "information_type", "systems"'
    )
    assert "extracted_entities" in content
    assert "information_type" in content
