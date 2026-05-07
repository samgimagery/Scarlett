#!/usr/bin/env python3
"""Multi-turn regression for top-intent polish wiring.

This intentionally exercises the controlled polish layer without requiring live
Ollama/RAG. It calls the FastAPI app directly and verifies that high-value
intent families get stable, emotionally-scoped response shapes.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "polish_regression_latest.json"


CASES = [
    {
        "question": "combien pour le niveau 1",
        "expect_intent": "price_n1",
        "expect_scope": "concise",
        "contains": ["4 995", "104"],
    },
    {
        "question": "avez vous aromatherapie",
        "expect_intent": "aroma_course",
        "expect_scope": "concise",
        "contains": ["aromathérapie", "formation à la carte"],
    },
    {
        "question": "de laromatherapy pas practicien",
        "expect_intent": "aroma_course",
        "expect_scope": "repair",
        "contains": ["pas du parcours praticien"],
    },
    {
        "question": "je ne sais pas quel niveau choisir",
        "expect_intent": "unsure_start",
        "expect_scope": "warm",
        "contains": ["point de départ", "parcours logique"],
    },
    {
        "question": "c est au dessus de mes moyens",
        "expect_intent": "too_expensive",
        "expect_scope": "reassuring",
        "contains": ["budget", "paiements"],
    },
    {
        "question": "agent humain s il vous plaît",
        "expect_intent": "human",
        "expect_scope": "reassuring",
        "contains": ["parler à quelqu’un", "orienter"],
    },
]


def main_cli() -> int:
    client = TestClient(main.app)
    rows = []
    failures = []
    for case in CASES:
        res = client.post("/ask", json={"question": case["question"], "language": "fr"})
        ok = res.status_code == 200
        data = res.json() if ok else {"error": res.text}
        answer = data.get("answer", "")
        voice = data.get("voice") or {}
        polish = voice.get("response_polish") or {}
        row = {
            "question": case["question"],
            "status_code": res.status_code,
            "answer": answer,
            "intent": voice.get("intent"),
            "scope": polish.get("scope"),
            "source_layer": polish.get("source_layer"),
            "ok": ok,
        }
        if voice.get("intent") != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {voice.get('intent')} != {case['expect_intent']}"
        elif polish.get("scope") != case["expect_scope"]:
            row["ok"] = False
            row["failure"] = f"scope {polish.get('scope')} != {case['expect_scope']}"
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
    print(f"PASS polish regressions: {len(rows)} turns")
    print(REPORT)
    for i, row in enumerate(rows, 1):
        print(f"{i}. {row['question']} -> {row['intent']} / {row['scope']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
