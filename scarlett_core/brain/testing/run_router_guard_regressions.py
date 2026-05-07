#!/usr/bin/env python3
"""End-to-end /ask regressions for REQ-149 router guards.

These cases verify that the guard rules do not merely win in the classifier;
they also reach the expected local/source layer through the FastAPI app.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "router_guard_regression_latest.json"

CASES: list[dict[str, Any]] = [
    {
        "question": "quels cours moins chers avez vous",
        "expect_intent": "continuing_ed_list",
        "expect_source": "local_continuing_ed_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "ok alors quels programmes offrez vous",
        "expect_intent": "continuing_ed_list",
        "expect_source": "local_continuing_ed_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "je veux parler à quelqu un",
        "expect_intent": "human",
        "expect_source": "local_handoff_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "je veux parler à Julie",
        "expect_intent": "julie",
        "expect_source": "local_handoff_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "envoie moi le lien inscription",
        "expect_intent": "signup_link",
        "expect_source": "local_service_tile_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "je n ai pas entendu la fin",
        "expect_intent": "didnt_hear",
        "expect_source": "local_service_tile_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "j ai pas compris",
        "expect_intent": "didnt_hear",
        "expect_source": "local_service_tile_layer",
        "min_confidence": 0.96,
    },
    {
        "question": "quels campus avez vous",
        "expect_intent": "campus_list",
        "expect_source": "local_location_layer",
        "min_confidence": 0.96,
    },
]


def main_cli() -> int:
    client = TestClient(main.app)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in CASES:
        res = client.post("/ask", json={"question": case["question"], "language": "fr"})
        data = res.json() if res.status_code == 200 else {"error": res.text}
        voice = data.get("voice") or {}
        sources = data.get("sources") or []
        top_source = sources[0] if sources else None
        row = {
            "question": case["question"],
            "status_code": res.status_code,
            "intent": voice.get("intent"),
            "confidence": voice.get("classification_confidence"),
            "reason": voice.get("classification_reason"),
            "source": top_source,
            "path_debug": voice.get("path_debug"),
            "ok": res.status_code == 200,
        }
        if row["intent"] != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {row['intent']} != {case['expect_intent']}"
        elif top_source != case["expect_source"]:
            row["ok"] = False
            row["failure"] = f"source {top_source} != {case['expect_source']}"
        elif (row["confidence"] or 0) < case["min_confidence"]:
            row["ok"] = False
            row["failure"] = f"confidence {row['confidence']} < {case['min_confidence']}"
        rows.append(row)
        if not row["ok"]:
            failures.append(row)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"ok": not failures, "failures": failures, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if failures:
        print(json.dumps({"ok": False, "failures": failures, "report": str(REPORT)}, indent=2, ensure_ascii=False))
        return 1
    print(f"PASS router guard regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['source']} / {row['confidence']} / {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
