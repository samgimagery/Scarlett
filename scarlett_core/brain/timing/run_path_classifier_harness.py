#!/usr/bin/env python3
"""Run paraphrase/noisy utterance -> path_id classifier harness."""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scarlett_core.brain.timing.path_classifier import classify_utterance_to_path, generate_variants, load_cases
from scarlett_core.brain.timing.path_encoding import encode_path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "path_classifier"

SAFETY_INTENTS = {"internal_sources", "prompt_injection"}
HANDOFF_INTENTS = {"julie", "human"}


def classify_error(gold: dict, predicted_intent: str | None) -> str:
    if predicted_intent is None:
        return "miss"
    gold_intent = gold["intent"]
    if predicted_intent == gold_intent:
        return "ok"
    if predicted_intent in SAFETY_INTENTS and gold_intent not in SAFETY_INTENTS:
        return "safety_false_positive"
    if predicted_intent in HANDOFF_INTENTS and gold_intent not in HANDOFF_INTENTS:
        return "handoff_false_positive"
    gold_path = encode_path(gold)
    pred_case = next(c for c in load_cases() if c["intent"] == predicted_intent)
    pred_path = encode_path(pred_case)
    if gold_path.flow != pred_path.flow:
        return "wrong_flow"
    if gold_path.slot != pred_path.slot:
        return "wrong_slot"
    if gold_path.value != pred_path.value:
        return "wrong_value"
    return "wrong_intent_same_semantics"


def main() -> int:
    cases = list(load_cases())
    rows = []
    latencies_us = []
    for case in cases:
        gold_path = encode_path(case)
        for variant in generate_variants(case["intent"], case["question"], target_count=10):
            start = time.perf_counter_ns()
            candidates = classify_utterance_to_path(variant, top_k=3)
            latency_us = (time.perf_counter_ns() - start) / 1000
            latencies_us.append(latency_us)
            top1 = candidates[0] if candidates else None
            top_ids = [c.path_id for c in candidates]
            top_intents = [c.intent for c in candidates]
            top1_ok = bool(top1 and top1.path_id == gold_path.path_id)
            top3_ok = gold_path.path_id in top_ids
            rows.append({
                "case_id": case["case_id"],
                "gold_intent": case["intent"],
                "utterance": variant,
                "gold_path_id": gold_path.path_id,
                "gold_path_debug": gold_path.path_debug,
                "top1_intent": top1.intent if top1 else None,
                "top1_path_id": top1.path_id if top1 else None,
                "top1_score": top1.score if top1 else 0,
                "top3_intents": top_intents,
                "top1_ok": top1_ok,
                "top3_ok": top3_ok,
                "error_category": classify_error(case, top1.intent if top1 else None),
                "latency_us": round(latency_us, 3),
            })

    total = len(rows)
    top1 = sum(1 for r in rows if r["top1_ok"])
    top3 = sum(1 for r in rows if r["top3_ok"])
    by_error = Counter(r["error_category"] for r in rows)
    by_intent = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0})
    for r in rows:
        b = by_intent[r["gold_intent"]]
        b["total"] += 1
        b["top1"] += int(r["top1_ok"])
        b["top3"] += int(r["top3_ok"])

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(cases),
        "variant_count": total,
        "top1_correct": top1,
        "top1_accuracy": round(top1 / total, 4),
        "top3_correct": top3,
        "top3_accuracy": round(top3 / total, 4),
        "latency_us": {
            "mean": round(statistics.mean(latencies_us), 3),
            "median": round(statistics.median(latencies_us), 3),
            "p95": round(sorted(latencies_us)[int(len(latencies_us) * 0.95) - 1], 3),
            "max": round(max(latencies_us), 3),
        },
        "error_categories": dict(by_error),
        "intent_breakdown": {
            intent: {
                **vals,
                "top1_accuracy": round(vals["top1"] / vals["total"], 4),
                "top3_accuracy": round(vals["top3"] / vals["total"], 4),
            }
            for intent, vals in sorted(by_intent.items())
        },
        "failures": [r for r in rows if not r["top1_ok"]][:80],
        "rows": rows,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"path_classifier_harness_{stamp}.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"rows", "intent_breakdown", "failures"}}, indent=2, ensure_ascii=False))
    print(f"report_json={path}")
    return 0 if top1 == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
