#!/usr/bin/env python3
"""REQ-151 signup/action polish regressions.

Verifies Scarlett handles signup/reservation action requests locally and honestly:
she may guide to the official path, but must not claim she submitted, emailed,
reserved, booked, or transferred anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "action_polish_regression_latest.json"

FORBIDDEN = [
    "je vous ai inscrit",
    "vous êtes inscrit",
    "inscription confirmée",
    "j'ai soumis",
    "j’ai soumis",
    "formulaire soumis",
    "j'ai envoyé",
    "j’ai envoyé",
    "courriel envoyé",
    "email envoyé",
    "place réservée",
    "j'ai réservé",
    "j’ai réservé",
    "réservation confirmée",
    "rendez-vous confirmé",
    "j'ai transféré",
    "j’ai transféré",
]

CASES: list[dict[str, Any]] = [
    {
        "question": "envoie moi le lien inscription",
        "expect_intent": "signup_link",
        "expect_scope": "concise",
        "contains": ["lien", "officiel"],
    },
    {
        "question": "peux tu envoyer la page inscription",
        "expect_intent": "signup_link",
        "expect_scope": "concise",
        "contains": ["lien", "officiel"],
    },
    {
        "question": "je veux m inscrire",
        "expect_intent": "signup_direct",
        "expect_scope": "guiding",
        "contains": ["niveau 1", "cours à la carte"],
    },
    {
        "question": "inscris moi",
        "expect_intent": "signup_direct",
        "expect_scope": "guiding",
        "contains": ["niveau 1", "cours à la carte"],
    },
    {
        "question": "je veux réserver ma place",
        "expect_intent": "reserve_place",
        "expect_scope": "reassuring",
        "contains": ["confirmée", "ams"],
    },
    {
        "question": "garde moi une place",
        "expect_intent": "reserve_place",
        "expect_scope": "reassuring",
        "contains": ["confirmée", "ams"],
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
    print(f"PASS action polish regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['scope']} / {row['source']} / {row['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
