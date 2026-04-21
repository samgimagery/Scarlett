"""
Interaction logger — SQLite DB for every Q&A exchange.
"""
import sqlite3
import os
import json
from datetime import datetime
from config import LOG_DB


def init_db():
    """Create the logs table if it doesn't exist."""
    os.makedirs(os.path.dirname(LOG_DB), exist_ok=True)
    conn = sqlite3.connect(LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            question TEXT NOT NULL,
            language TEXT DEFAULT 'en',
            top_score REAL,
            sources TEXT,
            answer TEXT,
            refused INTEGER DEFAULT 0,
            model TEXT,
            latency_ms INTEGER
        )
    """)
    conn.commit()
    conn.close()


def log_interaction(question, language, top_score, sources, answer, refused, model, latency_ms):
    """Log a Q&A interaction."""
    conn = sqlite3.connect(LOG_DB)
    conn.execute(
        """INSERT INTO interactions 
           (timestamp, question, language, top_score, sources, answer, refused, model, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().isoformat(),
            question,
            language,
            top_score,
            json.dumps(sources) if isinstance(sources, list) else sources,
            answer,
            1 if refused else 0,
            model,
            latency_ms
        )
    )
    conn.commit()
    conn.close()


def get_recent_interactions(limit=20):
    """Get recent interactions for review."""
    conn = sqlite3.connect(LOG_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM interactions ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unanswered(limit=20):
    """Get questions that were refused (below threshold)."""
    conn = sqlite3.connect(LOG_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM interactions WHERE refused = 1 ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]