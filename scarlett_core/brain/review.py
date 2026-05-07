"""Review queue for Scarlett Brain weak-answer tuning.

The queue is local JSONL by design: easy to inspect, diff, import into an admin
cockpit later, and safe for the current LaunchAgent deployment.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LOG_DB
from .contract import BrainTrace

DEFAULT_REVIEW_QUEUE = Path(os.environ.get(
    "SCARLETT_BRAIN_REVIEW_QUEUE",
    str(Path(LOG_DB).with_name("brain_review_queue.jsonl")),
))

_WEAK_CONTACT_PHRASES = (
    "contacter l'ams",
    "contacter l’ams",
    "communiquer avec l'ams",
    "communiquer avec l’ams",
    "contact the office",
    "contact ams",
)


def _review_reason(answer: str, sources: list[str], top_score: float, refused: bool, model: str) -> str | None:
    text = (answer or "").lower()
    if refused:
        return "refused"
    if model != "local" and not sources:
        return "generated_without_sources"
    if 0 < top_score < 0.18:
        return "low_retrieval_score"
    if "generation error" in text:
        return "generation_error"
    if any(phrase in text for phrase in _WEAK_CONTACT_PHRASES) and len(answer) < 450:
        return "thin_escalation_answer"
    return None


def maybe_log_review(
    trace: BrainTrace,
    *,
    answer: str,
    sources: list[str],
    top_score: float,
    refused: bool,
    model: str,
    latency_ms: int,
    queue_path: Path = DEFAULT_REVIEW_QUEUE,
) -> bool:
    """Append a weak-answer review item when the answer needs human tuning."""
    reason = _review_reason(answer, sources, top_score, refused, model)
    if not reason:
        return False

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    item: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "question": trace.question,
        "answer": answer,
        "sources": sources,
        "top_score": top_score,
        "model": model,
        "latency_ms": latency_ms,
        "trace": trace.to_dict(),
        "status": "pending_review",
    }
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return True


def get_review_queue(limit: int = 50, queue_path: Path = DEFAULT_REVIEW_QUEUE) -> list[dict[str, Any]]:
    if not queue_path.exists():
        return []
    rows = []
    with queue_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]
