#!/usr/bin/env python3
"""REQ-152 handoff polish regressions.

Verifies human/Julie/callback/send-info/campus-contact handoffs stay local,
keep official AMS contact anchors, and never imply Scarlett has transferred,
called, emailed, booked, or reserved anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "handoff_polish_regression_latest.json"

FORBIDDEN = [
    "je vous transfère",
    "je vous transfere",
    "transfert confirmé",
    "j'ai transféré",
    "j’ai transféré",
    "j'ai appelé",
    "j’ai appelé",
    "rappel confirmé",
    "rendez-vous confirmé",
    "j'ai réservé",
    "j’ai réservé",
    "place réservée",
    "j'ai envoyé",
    "j’ai envoyé",
    "courriel envoyé",
    "email envoyé",
]

CASES: list[dict[str, Any]] = [
    {
        "question": "je veux parler à quelqu un",
        "expect_intent": "human",
        "expect_scope": "concise",
        "contains": ["1 800 475-1964", "contact", "officiel"],
    },
    {
        "question": "je veux parler à Julie",
        "expect_intent": "julie",
        "expect_scope": "concise",
        "contains": ["julie", "1 800 475-1964", "contact"],
    },
    {
        "question": "est ce qu on peut me rappeler",
        "expect_intent": "human",
        "expect_scope": "reassuring",
        "contains": ["rappel", "contact officiel", "1 800 475-1964"],
    },
    {
        "question": "prendre rendez-vous avec quelqu un",
        "expect_intent": "human",
        "expect_scope": "reassuring",
        "contains": ["rendez-vous", "contact officiel", "1 800 475-1964"],
    },
    {
        "question": "pouvez vous m envoyer de l information par courriel",
        "expect_intent": "human",
        "expect_scope": "warm",
        "contains": ["information officielle", "contact", "1 800 475-1964"],
    },
    {
        "question": "contact pour le campus de laval",
        "expect_intent": "human",
        "expect_scope": "warm",
        "contains": ["campus", "contact officiel", "1 800 475-1964"],
    },
]


def main_cli() -> int:
    client = TestClient(main.app)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in CASES:
        res = client.post("/ask", json={"question": case["question"], "language": "fr", "conversation_context": "Niveau 1; campus Laval"})
        data = res.json() if res.status_code == 200 else {"error": res.text}
        answer = data.get("answer", "")
        answer_low = answer.lower()
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
        elif row["source"] != "local_handoff_layer":
            row["ok"] = False
            row["failure"] = f"source {row['source']} != local_handoff_layer"
        elif row["scope"] != case["expect_scope"]:
            row["ok"] = False
            row["failure"] = f"scope {row['scope']} != {case['expect_scope']}"
        else:
            missing = [snippet for snippet in case["contains"] if snippet.lower() not in answer_low]
            forbidden = [snippet for snippet in FORBIDDEN if snippet in answer_low]
            if missing:
                row["ok"] = False
                row["failure"] = f"missing snippets: {missing}"
            elif forbidden:
                row["ok"] = False
                row["failure"] = f"forbidden fake-action snippets: {forbidden}"
        rows.append(row)
        if not row["ok"]:
            failures.append(row)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"ok": not failures, "failures": failures, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if failures:
        print(json.dumps({"ok": False, "failures": failures, "report": str(REPORT)}, indent=2, ensure_ascii=False))
        return 1
    print(f"PASS handoff polish regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['scope']} / {row['source']} / {row['confidence']} / {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
