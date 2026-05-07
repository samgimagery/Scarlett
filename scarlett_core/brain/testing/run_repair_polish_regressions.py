#!/usr/bin/env python3
"""REQ-150 conversation-repair polish regressions.

Verifies that common voice/ASR repair moments stay local and receive controlled
short polish metadata instead of falling into RAG/generation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "repair_polish_regression_latest.json"

CASES: list[dict[str, Any]] = [
    {
        "question": "je n ai pas entendu la fin",
        "expect_intent": "didnt_hear",
        "expect_scope": "concise",
        "contains": ["reformule"],
    },
    {
        "question": "j ai pas compris",
        "expect_intent": "didnt_hear",
        "expect_scope": "concise",
        "contains": ["reformule"],
    },
    {
        "question": "peux-tu répéter",
        "expect_intent": "repeat",
        "expect_scope": "concise",
        "contains": ["redis"],
    },
    {
        "question": "répète svp",
        "expect_intent": "repeat",
        "expect_scope": "concise",
        "contains": ["redis"],
    },
    {
        "question": "hein quoi",
        "expect_intent": "unclear",
        "expect_scope": "guiding",
        "contains": ["prix", "programme", "campus", "inscription"],
    },
    {
        "question": "je comprends pas",
        "expect_intent": "unclear",
        "expect_scope": "guiding",
        "contains": ["prix", "programme", "campus", "inscription"],
    },
]


def main_cli() -> int:
    client = TestClient(main.app)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in CASES:
        res = client.post("/ask", json={"question": case["question"], "language": "fr"})
        data = res.json() if res.status_code == 200 else {"error": res.text}
        answer = data.get("answer", "")
        voice = data.get("voice") or {}
        polish = voice.get("response_polish") or {}
        sources = data.get("sources") or []
        row = {
            "question": case["question"],
            "status_code": res.status_code,
            "answer": answer,
            "intent": voice.get("intent"),
            "confidence": voice.get("classification_confidence"),
            "reason": voice.get("classification_reason"),
            "source": sources[0] if sources else None,
            "scope": polish.get("scope"),
            "mode": polish.get("mode"),
            "ok": res.status_code == 200,
        }
        if row["intent"] != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {row['intent']} != {case['expect_intent']}"
        elif row["source"] != "local_service_tile_layer":
            row["ok"] = False
            row["failure"] = f"source {row['source']} != local_service_tile_layer"
        elif row["scope"] != case["expect_scope"]:
            row["ok"] = False
            row["failure"] = f"scope {row['scope']} != {case['expect_scope']}"
        else:
            missing = [snippet for snippet in case["contains"] if snippet.lower() not in answer.lower()]
            if missing:
                row["ok"] = False
                row["failure"] = f"missing snippets: {missing}"
        rows.append(row)
        if not row["ok"]:
            failures.append(row)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"ok": not failures, "failures": failures, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if failures:
        print(json.dumps({"ok": False, "failures": failures, "report": str(REPORT)}, indent=2, ensure_ascii=False))
        return 1
    print(f"PASS repair polish regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['scope']} / {row['source']} / {row['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
