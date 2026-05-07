#!/usr/bin/env python3
"""Benchmark Scarlett integer path encoding and service-tile lookup."""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from scarlett_core.brain.timing.path_encoding import decode_path, encode_path
from scarlett_core.brain.timing.service_tiles import DEFAULT_CASES, select_service_tile, select_service_tile_by_path

ITERATIONS = 1000


def load_cases() -> list[dict]:
    return [json.loads(line) for line in Path(DEFAULT_CASES).read_text(encoding="utf-8").splitlines() if line.strip()]


def bench(label: str, fn, iterations: int = ITERATIONS) -> dict:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - start)
    us = [s / 1000 for s in samples]
    return {
        "label": label,
        "iterations": iterations,
        "total_ops": iterations * 50,
        "mean_us_per_50_cases": round(statistics.mean(us), 3),
        "median_us_per_50_cases": round(statistics.median(us), 3),
        "p95_us_per_50_cases": round(sorted(us)[int(len(us) * 0.95) - 1], 3),
        "mean_us_per_case": round(statistics.mean(us) / 50, 4),
        "median_us_per_case": round(statistics.median(us) / 50, 4),
    }


def main() -> int:
    cases = load_cases()
    encoded = [encode_path(case) for case in cases]
    questions = [case["question"] for case in cases]
    path_ids = [path.path_id for path in encoded]

    # Warm caches.
    for q in questions:
        select_service_tile(q)
    for path_id in path_ids:
        select_service_tile_by_path(path_id)

    results = [
        bench("encode_path for 50 cases", lambda: [encode_path(case) for case in cases]),
        bench("decode_path for 50 path ids", lambda: [decode_path(path_id) for path_id in path_ids]),
        bench("text select_service_tile for 50 questions", lambda: [select_service_tile(q) for q in questions]),
        bench("path select_service_tile_by_path for 50 ids", lambda: [select_service_tile_by_path(path_id) for path_id in path_ids]),
        bench("full path round trip for 50 cases", lambda: [select_service_tile_by_path(encode_path(case).path_id) for case in cases]),
    ]

    report = {
        "case_count": len(cases),
        "iterations": ITERATIONS,
        "results": results,
        "samples": [
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "path_id": path.path_id,
                "path_debug": path.path_debug,
                "tile_id": select_service_tile_by_path(path.path_id).tile_id,
            }
            for case, path in zip(cases[:12], encoded[:12])
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
