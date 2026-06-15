"""Pytest options for MAM-RTI integration tests."""


def pytest_addoption(parser):
    parser.addoption(
        "--no-llm",
        action="store_true",
        default=False,
        help="Skip Qwen/Ollama calls and use deterministic retrieval-only reasoning.",
    )
