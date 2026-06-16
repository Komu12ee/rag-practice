"""RTI backend launcher with AI provider switching.

Examples:
    python run.py --provider sarvam
    python run.py --provider ollama --model qwen2.5:14b
    python run.py --provider mock
"""

from __future__ import annotations

import argparse
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start RTI Intelligence FastAPI backend.")
    parser.add_argument("--provider", choices=["sarvam", "ollama", "mock"], default="sarvam")
    parser.add_argument("--model", default="", help="Model name, e.g. qwen2.5:14b for Ollama.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload during development.")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    os.environ["RTI_AI_PROVIDER"] = args.provider
    if args.model:
        os.environ["RTI_AI_MODEL"] = args.model
    elif args.provider == "ollama":
        os.environ.setdefault("RTI_AI_MODEL", "qwen2.5:14b")
    elif args.provider == "sarvam":
        os.environ.setdefault("RTI_AI_MODEL", os.environ.get("SARVAM_MODEL", "sarvam-105b"))
    else:
        os.environ.setdefault("RTI_AI_MODEL", "mock")

    os.environ["OLLAMA_BASE_URL"] = args.ollama_url
    os.environ["AI_TIMEOUT_SECONDS"] = str(args.timeout)
    os.environ["AI_RETRIES"] = str(args.retries)

    print(
        "[RTI Backend] Starting | "
        f"provider={os.environ['RTI_AI_PROVIDER']} "
        f"model={os.environ.get('RTI_AI_MODEL')} "
        f"host={args.host} port={args.port}"
    )

    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
