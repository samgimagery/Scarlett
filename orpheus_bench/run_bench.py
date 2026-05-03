#!/usr/bin/env python3
"""Light Orpheus benchmark harness for REQ-108.

This starts with readiness and prompt bookkeeping only. Backends are added as they
are installed so we don't create a heavy system before proving the path.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS = ROOT / "prompts.jsonl"


def load_prompts() -> list[dict]:
    return [json.loads(line) for line in PROMPTS.read_text().splitlines() if line.strip()]


def ollama_models() -> list[str]:
    if not shutil.which("ollama"):
        return []
    try:
        out = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        return []
    lines = out.splitlines()[1:]
    return [line.split()[0] for line in lines if line.strip()]


def readiness() -> dict:
    models = ollama_models()
    return {
        "ollama_available": bool(shutil.which("ollama")),
        "orpheus_ollama_models": [m for m in models if "orpheus" in m.lower()],
        "prompt_count": len(load_prompts()),
        "approved_default_model": "legraphista/Orpheus:latest",
        "quality_reference_model": "legraphista/Orpheus:3b-ft-q8",
        "next_step": "Use Q4 by default: run chunking_poc.py --scenario q4_turn_taking --voice leah, then build cached filler + playback queue."
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", action="store_true", help="Check local bench readiness")
    parser.add_argument("--list-prompts", action="store_true", help="Print benchmark prompts")
    args = parser.parse_args()

    if args.list_prompts:
        for prompt in load_prompts():
            print(json.dumps(prompt, ensure_ascii=False))
        return

    print(json.dumps(readiness(), indent=2))


if __name__ == "__main__":
    main()
