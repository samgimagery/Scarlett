#!/usr/bin/env python3
"""Select Scarlett language-bank lines for audio generation/review.

Usage examples:
  python3 language_bank/select_bank.py --cache-priority critical high
  python3 language_bank/select_bank.py --type floor_holder repair --format jsonl
  python3 language_bank/select_bank.py --first-pass > language_bank/first_pass.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "language_bank" / "scarlett_en_live_bank.json"

FIRST_PASS_TYPES = {
    "backchannel",
    "receipt",
    "floor_holder",
    "retrieval_progress",
    "repair",
    "interruption",
}
FIRST_PASS_PRIORITIES = {"critical", "high"}


def load_bank(path: Path = BANK) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def include_line(line: dict, args: argparse.Namespace) -> bool:
    if args.first_pass:
        if line.get("type") not in FIRST_PASS_TYPES:
            return False
        if line.get("cache_priority") not in FIRST_PASS_PRIORITIES:
            return False
        if line.get("requires_manual_review") is True:
            return False
    if args.type and line.get("type") not in args.type:
        return False
    if args.cache_priority and line.get("cache_priority") not in args.cache_priority:
        return False
    if args.exclude_manual_review and line.get("requires_manual_review") is True:
        return False
    if args.text and args.text.lower() not in line.get("text", "").lower():
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, default=BANK)
    parser.add_argument("--type", nargs="*")
    parser.add_argument("--cache-priority", nargs="*")
    parser.add_argument("--exclude-manual-review", action="store_true")
    parser.add_argument("--first-pass", action="store_true")
    parser.add_argument("--text")
    parser.add_argument("--format", choices=["json", "jsonl", "text"], default="jsonl")
    args = parser.parse_args()

    bank = load_bank(args.bank)
    lines = [line for line in bank["lines"] if include_line(line, args) and line.get("text")]

    if args.format == "json":
        print(json.dumps(lines, indent=2, ensure_ascii=False))
    elif args.format == "text":
        for line in lines:
            print(f"{line['id']}\t{line['type']}\t{line.get('cache_priority')}\t{line['text']}")
    else:
        for line in lines:
            print(json.dumps(line, ensure_ascii=False))


if __name__ == "__main__":
    main()
