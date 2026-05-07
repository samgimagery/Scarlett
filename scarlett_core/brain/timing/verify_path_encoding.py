#!/usr/bin/env python3
"""Verify Scarlett integer path encoding invariants."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scarlett_core.brain.timing.path_encoding import decode_path, encode_path, infer_path
from scarlett_core.brain.timing.service_tiles import (
    DEFAULT_CASES,
    normalize_question,
    select_service_tile,
    select_service_tile_by_path,
)


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    cases = load_cases()
    first = [encode_path(case) for case in cases]
    second = [encode_path(case) for case in cases]

    errors: list[str] = []
    if [p.path_id for p in first] != [p.path_id for p in second]:
        errors.append("path ids are not deterministic across repeated generation")

    for case, path in zip(cases, first):
        decoded = decode_path(path.path_id)
        if decoded.path_debug != path.path_debug:
            errors.append(
                f"decode mismatch for {case['case_id']}: {path.path_debug} -> {decoded.path_debug}"
            )
        tile_by_text = select_service_tile(case.get("question", ""))
        tile_by_path = select_service_tile_by_path(path.path_id)
        if not tile_by_text:
            errors.append(f"text selector missed {case['case_id']}")
        if not tile_by_path:
            errors.append(f"path selector missed {case['case_id']} path_id={path.path_id}")
        if tile_by_text and tile_by_path and tile_by_text.tile_id != tile_by_path.tile_id:
            errors.append(
                f"tile round trip mismatch for {case['case_id']}: "
                f"text={tile_by_text.tile_id}, path={tile_by_path.tile_id}"
            )

    id_counts = Counter(p.path_id for p in first)
    collisions = [path_id for path_id, count in id_counts.items() if count > 1]
    if collisions:
        errors.append(f"path_id collisions: {collisions}")

    tuple_counts = Counter(tuple(infer_path(case).items()) for case in cases)
    tuple_collisions = [items for items, count in tuple_counts.items() if count > 1]
    if tuple_collisions:
        errors.append(f"semantic tuple collisions: {tuple_collisions}")

    trigger_counts = Counter(normalize_question(case.get("question", "")) for case in cases)
    duplicate_triggers = [trigger for trigger, count in trigger_counts.items() if count > 1]
    if duplicate_triggers:
        errors.append(f"normalized trigger duplicates: {duplicate_triggers}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print(f"PASS: {len(cases)} cases, {len(id_counts)} path ids, zero collisions, all round trips verified")
    for case, path in zip(cases, first):
        print(f"{case['case_id']} {path.path_id} {path.path_debug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
