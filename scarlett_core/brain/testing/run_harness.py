#!/usr/bin/env python3
"""Scarlett Brain regression harness.

Runs JSONL test cases against the live `/ask` endpoint, applies deterministic
checks, and writes a timestamped report. This is intentionally conservative:
it observes and classifies; it never patches production.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8000/ask"
ROOT = Path(__file__).resolve().parent
DEFAULT_PACK = ROOT / "test_pack_ams.jsonl"
DEFAULT_REPORT_DIR = ROOT / "reports"

INTERNAL_DEFAULTS = [
    "vault",
    "notes",
    "fichiers",
    "base de connaissances",
    "sources",
    "rag",
    "smart connections",
    "/users/",
    ".md",
]


@dataclass
class Check:
    claim: str
    verdict: str
    evidence: str
    fix_category: str | None = None


def normalize_money(value: int) -> list[str]:
    raw = str(value)
    spaced = f"{value:,}".replace(",", " ")
    return [raw, spaced]


def contains_any(text: str, needles: list[str]) -> list[str]:
    lower = text.lower()
    return [n for n in needles if n and n.lower() in lower]


def post_ask(url: str, case: dict[str, Any], timeout: float = 45.0) -> dict[str, Any]:
    payload = {
        "question": case["question"],
        "language": case.get("language") or "fr",
    }
    if case.get("conversation_context") is not None:
        payload["conversation_context"] = case.get("conversation_context")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def route_matches(expected: str, response: dict[str, Any]) -> Check:
    model = response.get("model") or ""
    sources = response.get("sources") or []
    expected = expected or ""
    if expected.startswith("local_"):
        ok = model == "local" and (expected in sources or "local_service_tile_layer" in sources)
        return Check(
            f"route should be {expected}",
            "PASS" if ok else "FAIL",
            f"model={model!r}, sources={sources!r}",
            None if ok else "deterministic_fact",
        )
    if expected == "rag_or_service_flow":
        ok = bool(sources) or model == "local"
        return Check(
            "route should use RAG/service flow with evidence",
            "PASS" if ok else "FAIL",
            f"model={model!r}, sources={sources!r}",
            None if ok else "retrieval_ranking_tweak",
        )
    if expected in {"conversation_state", "voice_control"}:
        ok = model == "local" and "local_service_tile_layer" in sources
        return Check(
            f"route handled by {expected} fixture or service tile",
            "PASS" if ok else "UNSURE",
            f"model={model!r}, sources={sources!r}",
            None if ok else "missing_oracle",
        )
    if expected in {"telegram_or_service_flow", "safety_or_llm"}:
        return Check(
            f"route observed for {expected}",
            "PASS",
            f"model={model!r}, sources={sources!r}",
        )
    return Check("route expectation absent", "UNSURE", f"expected_route={expected!r}")


def score_case(case: dict[str, Any], response: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    checks: list[Check] = []
    answer = response.get("answer") or "" if response else ""

    if error:
        checks.append(Check("/ask request completed", "FAIL", error, "harness_or_service"))
    else:
        checks.append(Check("/ask request completed", "PASS", f"latency_ms={response.get('latency_ms')}"))
        checks.append(route_matches(case.get("expected_route", ""), response))

    forbidden = list(dict.fromkeys(INTERNAL_DEFAULTS + case.get("forbidden_phrases", [])))
    leaks = contains_any(answer, forbidden)
    checks.append(Check(
        "no internal/source leakage",
        "PASS" if not leaks else "FAIL",
        "no forbidden phrases" if not leaks else f"matched {leaks}",
        None if not leaks else "prompt_adjustment",
    ))

    expected_contains = case.get("expected_answer_contains", [])
    if isinstance(expected_contains, str):
        expected_contains = [expected_contains]
    for needle in expected_contains:
        ok = needle.lower() in answer.lower()
        checks.append(Check(
            f"answer contains {needle!r}",
            "PASS" if ok else "FAIL",
            "found" if ok else f"answer={answer[:220]!r}",
            None if ok else "deterministic_fact",
        ))

    for needle in case.get("expected_forbidden_contains", []):
        ok = needle.lower() not in answer.lower()
        checks.append(Check(
            f"answer must not contain {needle!r}",
            "PASS" if ok else "FAIL",
            "absent" if ok else "present",
            None if ok else "service_flow_rule",
        ))

    facts = case.get("expected_facts") or {}
    for key in ("price", "weekly", "admin_fee", "total", "level_2_price"):
        if key in facts:
            variants = normalize_money(int(facts[key]))
            ok = any(v in answer.replace("\u00a0", " ") for v in variants)
            checks.append(Check(
                f"expected numeric fact {key}={facts[key]}",
                "PASS" if ok else "FAIL",
                f"looked for {variants}" if not ok else f"found one of {variants}",
                None if ok else "deterministic_fact",
            ))

    campuses = facts.get("campuses") or []
    if campuses:
        missing = [c for c in campuses if c.lower() not in answer.lower()]
        checks.append(Check(
            "campus list contains all expected campuses",
            "PASS" if not missing else "FAIL",
            "all present" if not missing else f"missing {missing}",
            None if not missing else "deterministic_fact",
        ))

    if facts.get("lead_with"):
        lead = facts["lead_with"]
        avoid = facts.get("avoid_leading_with")
        lead_idx = answer.lower().find(lead.lower())
        avoid_idx = answer.lower().find(str(avoid).lower()) if avoid else -1
        ok = lead_idx >= 0 and (avoid_idx < 0 or lead_idx < avoid_idx)
        checks.append(Check(
            f"trained-practitioner path leads with {lead}",
            "PASS" if ok else "FAIL",
            f"lead_idx={lead_idx}, avoid_idx={avoid_idx}",
            None if ok else "service_flow_rule",
        ))

    voice = response.get("voice") or {} if response else {}

    if "max_first_audio_ms" in case and response:
        budget = int(case["max_first_audio_ms"])
        actual = voice.get("first_audio_ms")
        if actual is None:
            actual = int(response.get("latency_ms") or 0)
        actual = int(actual)
        checks.append(Check(
            f"first audio within {budget}ms budget",
            "PASS" if actual <= budget else "FAIL",
            f"first_audio_ms={actual}, tile_id={voice.get('tile_id')}",
            None if actual <= budget else "latency_policy",
        ))

    if "max_answer_ms" in case and response:
        actual = int(response.get("latency_ms") or 0)
        budget = int(case["max_answer_ms"])
        non_blocking_voice = bool(voice) and voice.get("blocks_first_audio") is False
        ok = actual <= budget or non_blocking_voice
        evidence = f"latency_ms={actual}"
        if non_blocking_voice and actual > budget:
            evidence += ", non_blocking_first_audio=true"
        checks.append(Check(
            f"answer latency within {budget}ms budget or non-blocking after tile",
            "PASS" if ok else "FAIL",
            evidence,
            None if ok else "latency_policy",
        ))

    if case.get("voice_strategy"):
        strategy = case["voice_strategy"]
        prebuilt = bool(case.get("prebuilt_allowed"))
        line = case.get("prebuilt_line")
        ok = strategy in {"silent_wait", "receipt", "lookup_line", "prebuilt_tile", "hybrid_tile_then_generate", "live_generate", "clarify", "handoff_or_escalate", "interrupt"}
        if strategy in {"prebuilt_tile", "hybrid_tile_then_generate", "receipt", "lookup_line"}:
            ok = ok and (prebuilt or bool(line) or bool(voice.get("line")))
        if voice:
            ok = ok and voice.get("strategy") == strategy and voice.get("interruptible") is True
            if line:
                ok = ok and voice.get("line") == line and bool(voice.get("asset_id"))
        checks.append(Check(
            f"voice strategy metadata valid: {strategy}",
            "PASS" if ok else "FAIL",
            f"case_prebuilt_allowed={prebuilt}, case_line={line!r}, response_voice={voice}",
            None if ok else "voice_strategy_metadata",
        ))

    # Thin escalation detector mirrors the Brain review intent.
    thin_contact = bool(re.search(r"contacter l['’]ams|communiquer avec l['’]ams|contact(er)? (the )?office", answer, re.I)) and len(answer) < 450
    checks.append(Check(
        "no thin escalation answer",
        "PASS" if not thin_contact else "FAIL",
        f"length={len(answer)}" if thin_contact else "not thin escalation",
        None if not thin_contact else "service_flow_rule",
    ))

    failed = [c for c in checks if c.verdict == "FAIL"]
    unsure = [c for c in checks if c.verdict == "UNSURE"]
    if failed:
        status = "failed"
        confidence = "FEEDBACK"
    elif unsure:
        status = "verified"
        confidence = "PARTIAL"
    else:
        status = "verified"
        confidence = "VERIFIED"

    categories = []
    for c in checks:
        if c.verdict in {"FAIL", "UNSURE"}:
            categories.append({
                "claim": c.claim,
                "fix_category": c.fix_category or "missing_oracle",
                "reason": c.evidence,
            })

    return {
        "test_id": case.get("test_id") or case.get("case_id"),
        "question": case.get("question"),
        "status": status,
        "confidence": confidence,
        "response": response,
        "checks": [c.__dict__ for c in checks],
        "failure_classifications": categories,
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {e}") from e
    return cases


def write_markdown(report_path: Path, summary: dict[str, Any]) -> None:
    md_path = report_path.with_suffix(".md")
    lines = [
        "# Scarlett Brain Harness Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Endpoint: `{summary['endpoint']}`",
        "",
        "## Summary",
        "",
        f"- Total: {summary['totals']['total']}",
        f"- Verified: {summary['totals']['verified']}",
        f"- Failed: {summary['totals']['failed']}",
        f"- Partial: {summary['totals']['partial']}",
        "",
        "## Cases",
        "",
    ]
    for case in summary["cases"]:
        lines += [
            f"### {case['test_id']} — {case['confidence']}",
            "",
            f"**Question:** {case['question']}",
            "",
            f"**Answer:** {case.get('response', {}).get('answer', '')}",
            "",
            "**Checks:**",
        ]
        for check in case["checks"]:
            lines.append(f"- **{check['verdict']}** {check['claim']} — {check['evidence']}")
        if case["failure_classifications"]:
            lines += ["", "**Failure classification:**"]
            for fail in case["failure_classifications"]:
                lines.append(f"- `{fail['fix_category']}` — {fail['claim']}: {fail['reason']}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    cases = load_cases(args.pack)
    results = []
    for case in cases:
        try:
            response = post_ask(args.url, case, timeout=args.timeout)
            result = score_case(case, response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            result = score_case(case, {}, error=repr(e))
        results.append(result)
        print(f"{result['test_id']}: {result['confidence']}")

    total = len(results)
    failed = sum(1 for r in results if r["status"] == "failed")
    partial = sum(1 for r in results if r["confidence"] == "PARTIAL")
    verified = total - failed
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "endpoint": args.url,
        "pack": str(args.pack),
        "totals": {"total": total, "verified": verified, "failed": failed, "partial": partial},
        "cases": results,
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = args.report_dir / f"scarlett_brain_harness_{stamp}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report_path, summary)
    print(f"report_json={report_path}")
    print(f"report_md={report_path.with_suffix('.md')}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
