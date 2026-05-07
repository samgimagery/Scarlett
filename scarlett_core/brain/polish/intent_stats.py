"""Scarlett intent/path usage statistics.

Small, local, inspectable analytics for the polish loop. It records the route
Scarlett thought she was on, then summarizes the most-used intents/paths so we
can decide which response families deserve human polish and voice work.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LOG_DB
from scarlett_core.brain.timing.path_classifier import classify_utterance_to_path, normalize_for_classification


@dataclass(frozen=True)
class IntentTrace:
    intent: str | None
    path_id: int | None
    path_debug: str | None
    confidence: float
    reason: str | None
    top3: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_intent_trace(question: str) -> IntentTrace:
    candidates = classify_utterance_to_path(question, top_k=3)
    top = candidates[0] if candidates else None
    return IntentTrace(
        intent=top.intent if top else None,
        path_id=top.path_id if top else None,
        path_debug=top.path_debug if top else None,
        confidence=top.score if top else 0.0,
        reason=top.reason if top else None,
        top3=tuple({
            "intent": c.intent,
            "path_id": c.path_id,
            "score": c.score,
            "reason": c.reason,
        } for c in candidates),
    )


def init_intent_stats_db(db_path: str = LOG_DB) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS intent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            question TEXT NOT NULL,
            question_norm TEXT NOT NULL,
            language TEXT DEFAULT 'fr',
            intent TEXT,
            path_id INTEGER,
            path_debug TEXT,
            confidence REAL,
            reason TEXT,
            top3_json TEXT,
            source_layer TEXT,
            model TEXT,
            latency_ms INTEGER
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intent_events_intent ON intent_events(intent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intent_events_path_id ON intent_events(path_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intent_events_timestamp ON intent_events(timestamp)")
    conn.commit()
    conn.close()


def log_intent_event(
    *,
    question: str,
    language: str,
    source_layer: str | None,
    model: str | None,
    latency_ms: int | None,
    trace: IntentTrace | None = None,
    db_path: str = LOG_DB,
) -> IntentTrace:
    init_intent_stats_db(db_path)
    trace = trace or classify_intent_trace(question)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO intent_events
        (timestamp, question, question_norm, language, intent, path_id, path_debug,
         confidence, reason, top3_json, source_layer, model, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            question,
            normalize_for_classification(question),
            language,
            trace.intent,
            trace.path_id,
            trace.path_debug,
            trace.confidence,
            trace.reason,
            json.dumps(trace.top3, ensure_ascii=False),
            source_layer,
            model,
            latency_ms,
        ),
    )
    conn.commit()
    conn.close()
    return trace


def _rows(db_path: str, limit: int | None = None) -> list[sqlite3.Row]:
    init_intent_stats_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM intent_events ORDER BY id DESC"
    params: tuple[Any, ...] = ()
    if limit:
        sql += " LIMIT ?"
        params = (limit,)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def summarize_intent_stats(db_path: str = LOG_DB, limit: int | None = 500) -> dict[str, Any]:
    rows = _rows(db_path, limit)
    by_intent: Counter[str] = Counter()
    by_path: Counter[int] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    low_confidence: list[dict[str, Any]] = []

    for row in rows:
        intent = row["intent"] or "unclassified"
        by_intent[intent] += 1
        if row["path_id"] is not None:
            by_path[int(row["path_id"])] += 1
        if len(examples[intent]) < 5:
            examples[intent].append(row["question"])
        if (row["confidence"] or 0) < 0.75:
            low_confidence.append({
                "question": row["question"],
                "intent": row["intent"],
                "path_id": row["path_id"],
                "confidence": row["confidence"],
                "reason": row["reason"],
            })

    return {
        "event_count": len(rows),
        "top_intents": [{"intent": k, "count": v, "examples": examples[k]} for k, v in by_intent.most_common(20)],
        "top_paths": [{"path_id": k, "count": v} for k, v in by_path.most_common(20)],
        "low_confidence": low_confidence[:25],
    }


if __name__ == "__main__":
    print(json.dumps(summarize_intent_stats(), indent=2, ensure_ascii=False))
