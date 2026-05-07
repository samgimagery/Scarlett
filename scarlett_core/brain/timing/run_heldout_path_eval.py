#!/usr/bin/env python3
"""Evaluate held-out utterance variants against the prototype path classifier."""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scarlett_core.brain.timing.path_classifier import classify_utterance_to_path, load_cases
from scarlett_core.brain.timing.path_encoding import encode_path

ROOT = Path(__file__).resolve().parent
DEFAULT_PACK = ROOT / "heldout_utterance_pack_ams.jsonl"
REPORT_DIR = ROOT / "reports" / "path_classifier"
SAFETY_INTENTS = {"internal_sources", "prompt_injection"}
HANDOFF_INTENTS = {"julie", "human"}


def load_pack(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def classify_error(gold_case: dict, predicted_case: dict | None) -> str:
    if predicted_case is None:
        return "miss"
    if predicted_case["intent"] == gold_case["intent"]:
        return "ok"
    if predicted_case["intent"] in SAFETY_INTENTS and gold_case["intent"] not in SAFETY_INTENTS:
        return "safety_false_positive"
    if predicted_case["intent"] in HANDOFF_INTENTS and gold_case["intent"] not in HANDOFF_INTENTS:
        return "handoff_false_positive"
    gold = encode_path(gold_case)
    pred = encode_path(predicted_case)
    if gold.flow != pred.flow:
        return "wrong_flow"
    if gold.slot != pred.slot:
        return "wrong_slot"
    if gold.value != pred.value:
        return "wrong_value"
    return "wrong_intent_same_semantics"


def main() -> int:
    cases = {case["intent"]: case for case in load_cases()}
    pack = load_pack(DEFAULT_PACK)
    rows = []
    latencies = []
    for item in pack:
        gold_case = cases[item["intent"]]
        gold_path = encode_path(gold_case)
        start = time.perf_counter_ns()
        candidates = classify_utterance_to_path(item["utterance"], top_k=3)
        latency_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(latency_us)
        top1 = candidates[0] if candidates else None
        predicted_case = cases.get(top1.intent) if top1 else None
        top_ids = [c.path_id for c in candidates]
        rows.append({
            **item,
            "gold_path_id": gold_path.path_id,
            "gold_path_debug": gold_path.path_debug,
            "top1_intent": top1.intent if top1 else None,
            "top1_path_id": top1.path_id if top1 else None,
            "top1_score": top1.score if top1 else 0,
            "top3_intents": [c.intent for c in candidates],
            "top1_ok": bool(top1 and top1.path_id == gold_path.path_id),
            "top3_ok": gold_path.path_id in top_ids,
            "error_category": classify_error(gold_case, predicted_case),
            "latency_us": round(latency_us, 3),
        })
    total = len(rows)
    top1 = sum(r["top1_ok"] for r in rows)
    top3 = sum(r["top3_ok"] for r in rows)
    errors = Counter(r["error_category"] for r in rows)
    by_intent = defaultdict(lambda: {"total":0,"top1":0,"top3":0})
    for r in rows:
        b=by_intent[r["intent"]]
        b["total"] += 1
        b["top1"] += int(r["top1_ok"])
        b["top3"] += int(r["top3_ok"])
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pack": str(DEFAULT_PACK),
        "variant_count": total,
        "case_count": len(set(r["intent"] for r in rows)),
        "top1_correct": top1,
        "top1_accuracy": round(top1/total,4),
        "top3_correct": top3,
        "top3_accuracy": round(top3/total,4),
        "latency_us": {
            "mean": round(statistics.mean(latencies),3),
            "median": round(statistics.median(latencies),3),
            "p95": round(sorted(latencies)[int(len(latencies)*0.95)-1],3),
            "max": round(max(latencies),3),
        },
        "error_categories": dict(errors),
        "intent_breakdown": {
            intent:{**vals,"top1_accuracy":round(vals["top1"]/vals["total"],4),"top3_accuracy":round(vals["top3"]/vals["total"],4)}
            for intent, vals in sorted(by_intent.items())
        },
        "failures": [r for r in rows if not r["top1_ok"]],
        "rows": rows,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = REPORT_DIR / f"heldout_path_eval_{stamp}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in {"rows","intent_breakdown","failures"}}, indent=2, ensure_ascii=False))
    print(f"report_json={out}")
    return 0 if top1 == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
