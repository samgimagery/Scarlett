#!/usr/bin/env python3
"""REQ-154 continuing-ed polish regressions.

Verifies high-frequency course browsing moments get a short controlled opener
while preserving grounded deterministic course lists from local_continuing_ed_layer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "continuing_ed_polish_regression_latest.json"

FORBIDDEN = [
    "inscription confirmée",
    "place réservée",
    "j'ai réservé",
    "j’ai réservé",
    "date confirmée",
    "horaire confirmé",
    "tous les campus offrent",
    "chaque campus offre",
]

CASES: list[dict[str, Any]] = [
    {
        "question": "quels cours moins chers avez vous",
        "expect_intent": "continuing_ed_list",
        "expect_scope": "reassuring",
        "contains": ["options plus courtes", "Aromathérapie : les bases", "99 $", "cours à la carte"],
    },
    {
        "question": "je veux juste essayer",
        "expect_intent": "continuing_ed_list",
        "expect_scope": "reassuring",
        "contains": ["options plus courtes", "Bons points d’entrée", "Massage neurosensoriel"],
    },
    {
        "question": "formation courte ou atelier",
        "expect_intent": "continuing_ed_list",
        "expect_scope": "reassuring",
        "contains": ["options plus courtes", "Aromathérapie clinique", "Massage bébé/enfant"],
    },
    {
        "question": "cours détente spa",
        "expect_intent": "continuing_ed_list",
        "expect_scope": "guiding",
        "contains": ["guider par objectif", "spa / relaxation", "Massage aux coquillages chauds"],
    },
    {
        "question": "avez vous massage sportif",
        "expect_intent": "sport_course",
        "expect_scope": "concise",
        "contains": ["récupération", "Massage sportif niveau 1", "MyoFlossing"],
    },
    {
        "question": "drainage lymphatique",
        "expect_intent": "specific_course",
        "expect_scope": "concise",
        "contains": ["repère précis", "Drainage lymphatique", "699 $", "24 h"],
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
            "intent": voice.get("intent"),
            "confidence": voice.get("classification_confidence"),
            "reason": voice.get("classification_reason"),
            "source": sources[0] if sources else None,
            "scope": polish.get("scope"),
            "mode": polish.get("mode"),
            "answer": answer,
            "ok": res.status_code == 200,
        }
        if row["intent"] != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {row['intent']} != {case['expect_intent']}"
        elif row["source"] != "local_continuing_ed_layer":
            row["ok"] = False
            row["failure"] = f"source {row['source']} != local_continuing_ed_layer"
        elif row["scope"] != case["expect_scope"]:
            row["ok"] = False
            row["failure"] = f"scope {row['scope']} != {case['expect_scope']}"
        elif row["mode"] != "prefix":
            row["ok"] = False
            row["failure"] = f"mode {row['mode']} != prefix"
        else:
            missing = [snippet for snippet in case["contains"] if snippet.lower() not in answer_low]
            forbidden = [snippet for snippet in FORBIDDEN if snippet in answer_low]
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
    print(f"PASS continuing-ed polish regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['scope']} / {row['source']} / {row['confidence']} / {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
