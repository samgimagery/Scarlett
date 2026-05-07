#!/usr/bin/env python3
"""Scarlett Telegram trust regression harness.

Exercises the same stateful expansion logic used by telegram_bot.py, then calls
live /ask for non-local replies. This catches pending_offer and active_goal drift
without sending real Telegram messages.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import telegram_bot as bot  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8000/ask"


def post_ask(url: str, question: str, user_data: dict[str, Any], lang: str = "fr") -> dict[str, Any]:
    conv_ctx = bot._conversation_context(user_data)
    question_for_rag = bot._expand_followup_question(user_data, question)
    payload: dict[str, Any] = {"question": question_for_rag, "language": lang}
    if conv_ctx:
        payload["conversation_context"] = conv_ctx
    req = request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    answer = bot._smooth_guided_offer(bot._chat_safe(data.get("answer", ""), strip_intro=True))
    answer = bot._de_repeat_answer(user_data, answer)
    bot._update_conversation_state(user_data, question, answer)
    data["telegram_question_for_rag"] = question_for_rag
    data["telegram_answer"] = answer
    return data


def local_reply(question: str, user_data: dict[str, Any]) -> str | None:
    if bot._is_greeting(question):
        user_data["welcomed"] = True
        user_data.pop("pending_offer", None)
        if user_data.get("welcomed_once"):
            return "Ça va très bien, merci. Quelle information AMS souhaitez-vous vérifier ?"
        user_data["welcomed_once"] = True
        return "Bonjour, je suis Scarlett. Je peux vous aider à trouver le bon parcours à l’AMS."
    checks = [
        (bot._is_repeat_complaint, bot._repeat_complaint_reply),
        (bot._is_capability_query, bot._capability_reply),
        (bot._is_how_it_works_query, bot._how_it_works_reply),
        (bot._is_old_bot_query, lambda ud: bot._old_bot_reply(ud, question)),
        (bot._is_assumption_challenge, bot._assumption_challenge_reply),
        (bot._is_lost_query, bot._lost_reply),
    ]
    for pred, fn in checks:
        if pred(question):
            answer = fn(user_data)
            bot._update_conversation_state(user_data, question, answer)
            return bot._chat_safe(answer)
    if bot._is_new_student_intro(question):
        answer = bot._new_student_intro_reply(user_data, question)
        return bot._chat_safe(answer)
    if bot._is_trained_student_intro(question):
        answer = bot._trained_student_intro_reply(user_data, question)
        return bot._chat_safe(answer)
    direct = bot._direct_flow_reply(user_data, question)
    if direct:
        answer, _, _ = direct
        bot._update_conversation_state(user_data, question, answer)
        return bot._chat_safe(answer)
    return None


def run_turn(url: str, user_data: dict[str, Any], question: str) -> dict[str, Any]:
    answer = local_reply(question, user_data)
    if answer is not None:
        return {"question": question, "local": True, "answer": answer, "question_for_rag": None, "sources": ["telegram_local"]}
    data = post_ask(url, question, user_data)
    return {
        "question": question,
        "local": False,
        "question_for_rag": data.get("telegram_question_for_rag"),
        "answer": data.get("telegram_answer") or data.get("answer", ""),
        "sources": data.get("sources", []),
        "model": data.get("model"),
        "latency_ms": data.get("latency_ms"),
        "voice": data.get("voice"),
    }


def assert_not_contains(name: str, text: str, needles: list[str]):
    low = html.unescape(text or "").lower()
    for needle in needles:
        assert needle.lower() not in low, f"{name}: unexpected {needle!r} in {text[:400]!r}"


def assert_contains(name: str, text: str, needles: list[str]):
    low = html.unescape(text or "").lower()
    for needle in needles:
        assert needle.lower() in low, f"{name}: missing {needle!r} in {text[:400]!r}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    user_data: dict[str, Any] = {
        "lang": "fr",
        "welcomed": True,
        "welcomed_once": True,
        "pending_offer": "Expliquer calmement comment Scarlett fonctionne et comment elle oriente une personne vers le bon parcours AMS; si la personne dit oui ou demande comment ça marche, donner le fonctionnement en mode service client, puis commencer par le parcours débutant Niveau 1.",
    }
    conversation = [
        "wow salut comment vas tu",
        "j'aimerais étudier mais je sais pas où",
        "combien ça coûte?",
        "c'est trop cher",
        "ouch est-ce que je peux suivre d'autres cours pour moins cher?",
        "je veux juste essayer",
        "formation courte ou atelier",
        "laromatherapie",
        "avez vous de linfo sur le contenu ?",
        "de laromatherapy pas practicien",
        "contenu du cours, aromatherapie",
        "je veux parler à une personne",
        "est ce qu on peut me rappeler",
        "pouvez vous m envoyer de l information par courriel",
        "contact pour le campus de laval",
    ]
    results = [run_turn(args.url, user_data, q) for q in conversation]

    # Guard 1: social small-talk must not confirm pending offer or route to pricing.
    assert results[0]["local"] is True
    assert_not_contains("small_talk", results[0]["answer"], ["4 995", "niveau 1", "prix"])

    # Guard 2: price objections should acknowledge payment options and offer lighter à-la-carte paths.
    objection = results[3]["answer"]
    assert_contains("price_objection", objection, ["paiement", "carte"])
    assert_not_contains("price_objection", objection, ["revenu potentiel", "garantir un revenu"])

    # Guard 3: cheaper / lighter commitment flow should stay grounded in à-la-carte options.
    cheaper = results[4]["answer"]
    assert_contains("cheaper_courses", cheaper, ["carte"])
    assert_not_contains("cheaper_courses", cheaper, ["revenu potentiel", "garantir un revenu"])
    trial = results[5]["answer"]
    assert_contains("trial_courses", trial, ["essayer", "99"])
    workshop = results[6]["answer"]
    assert_contains("workshop_courses", workshop, ["carte", "cours"])

    # Guard 4: aromatherapy follow-ups and explicit corrections should remain aromatherapy content.
    aroma = results[7]["answer"]
    assert_contains("aromatherapy_intro", aroma, ["aromath"])
    for idx in [8, 9, 10]:
        content = results[idx]["answer"]
        assert_contains(f"aromatherapy_content_turn_{idx+1}", content, ["aromathérapie : les bases", "huiles essentielles"])
        assert_not_contains(f"aromatherapy_content_turn_{idx+1}", content, ["revenu potentiel", "niveau 2 sert", "orthothérapie avancée", "niveau 1 | praticien", "praticien en massothérapie"])

    # Guard 5: handoff family should give official contact path without pretending action happened.
    handoff_cases = {
        11: ["1 800 475-1964", "contact"],
        12: ["rappel", "1 800 475-1964"],
        13: ["information", "contact"],
        14: ["campus", "contact"],
    }
    for idx, needles in handoff_cases.items():
        answer = results[idx]["answer"]
        assert_contains(f"handoff_turn_{idx+1}", answer, needles)
        assert_not_contains(f"handoff_turn_{idx+1}", answer, ["j'ai réservé", "j’ai réservé", "c'est envoyé", "c’est envoyé", "je vous transfère maintenant"])

    report = {
        "ok": True,
        "url": args.url,
        "turns": results,
        "final_facts": user_data.get("facts", {}),
        "pending_offer": user_data.get("pending_offer"),
    }
    out_dir = ROOT / "scarlett_core" / "brain" / "testing" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "trust_regression_latest.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"PASS trust regressions: {len(results)} turns")
        print(out_path)
        for idx, r in enumerate(results, 1):
            print(f"{idx}. {r['question']} -> {'local' if r['local'] else r.get('model')} | {str(r['sources'])[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
