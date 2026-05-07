#!/usr/bin/env python3
"""REQ-156 greeting/orientation polish regressions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "greeting_polish_regression_latest.json"

CASES: list[dict[str, Any]] = [
    {
        "question": "bonjour",
        "expect_intent": "greeting",
        "expect_scope": "concise",
        "contains": ["Bonjour", "Scarlett"],
        "forbidden": ["tu", "te", "ton"],
    },
    {
        "question": "allo",
        "expect_intent": "greeting_allo",
        "expect_scope": "concise",
        "contains": ["Allô", "Scarlett"],
        "forbidden": ["tu", "te", "ton"],
    },
    {
        "question": "comment ça va",
        "expect_intent": "how_are_you",
        "expect_scope": "warm",
        "contains": ["Ça va très bien", "information AMS"],
        "forbidden": ["tu", "te", "ton"],
    },
    {
        "question": "tu peux m aider avec quoi",
        "expect_intent": "what_can_help",
        "expect_scope": "concise",
        "contains": ["formations", "prix", "campus", "inscription"],
        "forbidden": ["t’aider", "tu", "tes"],
    },
    {
        "question": "qu est-ce que tu peux faire",
        "expect_intent": "what_can_help",
        "expect_scope": "concise",
        "contains": ["formations", "prix", "campus", "inscription"],
        "forbidden": ["t’aider", "tu", "tes"],
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
        answer_low = answer.lower()
        voice = data.get("voice") or {}
        polish = voice.get("response_polish") or {}
        row = {
            "question": case["question"],
            "status_code": res.status_code,
            "intent": voice.get("intent"),
            "confidence": voice.get("classification_confidence"),
            "reason": voice.get("classification_reason"),
            "sources": data.get("sources") or [],
            "scope": polish.get("scope"),
            "mode": polish.get("mode"),
            "answer": answer,
            "ok": res.status_code == 200,
        }
        if row["intent"] != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {row['intent']} != {case['expect_intent']}"
        elif row["scope"] != case["expect_scope"]:
            row["ok"] = False
            row["failure"] = f"scope {row['scope']} != {case['expect_scope']}"
        else:
            missing = [s for s in case["contains"] if s.lower() not in answer_low]
            forbidden = [s for s in case["forbidden"] if f" {s.lower()} " in f" {answer_low} "]
            if missing:
                row["ok"] = False
                row["failure"] = f"missing snippets: {missing}"
            elif forbidden:
                row["ok"] = False
                row["failure"] = f"forbidden snippets: {forbidden}"
        rows.append(row)
        if not row["ok"]:
            failures.append(row)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"ok": not failures, "failures": failures, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if failures:
        print(json.dumps({"ok": False, "failures": failures, "report": str(REPORT)}, indent=2, ensure_ascii=False))
        return 1
    print(f"PASS greeting polish regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['scope']} / {row['sources'][:1]} / {row['confidence']} / {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
