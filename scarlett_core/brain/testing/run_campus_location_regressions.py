#!/usr/bin/env python3
"""REQ-153 campus/location richness regressions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main

REPORT = Path(__file__).resolve().parent / "reports" / "campus_location_regression_latest.json"

FORBIDDEN = [
    "tous les campus offrent les mêmes programmes",
    "chaque campus offre les mêmes programmes",
    "disponibilité confirmée",
    "place confirmée",
    "horaire confirmé",
    "date confirmée",
    "rendez-vous confirmé",
    "je vous réserve",
    "j'ai réservé",
    "j’ai réservé",
]

CASES: list[dict[str, Any]] = [
    {
        "question": "quels campus avez-vous",
        "expect_intent": "campus_list",
        "expect_source": "local_location_layer",
        "contains": ["8 campus", "Brossard", "Laval", "Montréal", "Trois-Rivières"],
    },
    {
        "question": "avez vous des campus en région",
        "expect_intent": "campus_list",
        "expect_source": "local_location_layer",
        "contains": ["8 campus", "Sherbrooke", "Drummondville", "Québec"],
    },
    {
        "question": "je suis à Laval, le campus le plus proche?",
        "expect_intent": "nearest_campus",
        "expect_source": "local_location_layer",
        "contains": ["Depuis", "Laval", "Repères à vol d’oiseau", "estimation locale"],
    },
    {
        "question": "adresse du campus de Montréal",
        "expect_intent": "campus_address",
        "expect_source": "local_location_layer",
        "contains": ["Montréal", "910 rue Bélanger Est", "horaires", "disponibilités"],
    },
    {
        "question": "horaires du campus de laval",
        "expect_intent": "nearest_campus",
        "expect_source": "local_location_layer",
        "contains": ["Laval", "1 800 475-1964", "Je préfère ne pas inventer"],
    },
    {
        "question": "le campus de brossard offre quoi",
        "expect_intent": "campus_address",
        "expect_source": "local_location_layer",
        "contains": ["Brossard", "1 800 475-1964", "places disponibles", "Je préfère ne pas inventer"],
    },
    {
        "question": "je suis à Rouyn, quel campus?",
        "expect_intent": "city_unknown",
        "expect_source": "local_location_layer",
        "contains": ["Rouyn-Noranda", "probablement", "Repères à vol d’oiseau"],
    },
    {
        "question": "contact pour le campus de laval",
        "expect_intent": "human",
        "expect_source": "local_handoff_layer",
        "contains": ["campus", "contact officiel", "1 800 475-1964"],
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
        sources = data.get("sources") or []
        row = {
            "question": case["question"],
            "status_code": res.status_code,
            "intent": voice.get("intent"),
            "confidence": voice.get("classification_confidence"),
            "reason": voice.get("classification_reason"),
            "source": sources[0] if sources else None,
            "answer": answer,
            "ok": res.status_code == 200,
        }
        if row["intent"] != case["expect_intent"]:
            row["ok"] = False
            row["failure"] = f"intent {row['intent']} != {case['expect_intent']}"
        elif row["source"] != case["expect_source"]:
            row["ok"] = False
            row["failure"] = f"source {row['source']} != {case['expect_source']}"
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
    print(f"PASS campus/location regressions: {len(rows)} turns")
    print(REPORT)
    for row in rows:
        print(f"- {row['question']} -> {row['intent']} / {row['source']} / {row['confidence']} / {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
