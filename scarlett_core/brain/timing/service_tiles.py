"""Scarlett fast-path voice service tiles.

A service tile is the small, polished first response Scarlett can play before
(or instead of) slower retrieval/generation. Tiles are deterministic metadata:
they do not replace the answer layer unless the caller decides to use the
`line` as audio.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from scarlett_core.brain.timing.path_encoding import encode_path

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "interaction_cases_ams.jsonl"

NON_BLOCKING_STRATEGIES = {
    "hybrid_tile_then_generate",
    "live_generate",
    "handoff_or_escalate",
}

TILE_STRATEGIES = {
    "prebuilt_tile",
    "receipt",
    "lookup_line",
    "hybrid_tile_then_generate",
    "clarify",
    "handoff_or_escalate",
}


@dataclass(frozen=True)
class ServiceTile:
    tile_id: str
    case_id: str
    intent: str
    trigger: str
    strategy: str
    line: str | None
    interruptible: bool
    prebuilt_allowed: bool
    fallback_if_slow: str | None
    max_first_audio_ms: int | None
    max_answer_ms: int | None
    asset_id: str | None
    asset_status: str
    blocks_first_audio: bool
    path_id: int
    path_debug: str
    tile_sequence: tuple[str, ...]
    emotion_profile: str | None

    def voice_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["first_audio_ms"] = projected_first_audio_ms(self)
        data["recording_ready"] = self.asset_status == "ready"
        data["needs_recording"] = self.asset_status == "scripted"
        return data


def normalize_question(text: str) -> str:
    q = (text or "").lower().strip().replace("’", "'")
    q = re.sub(r"[!?.,]+$", "", q).strip()
    q = re.sub(r"\s+", " ", q)
    return q


def projected_first_audio_ms(tile: ServiceTile) -> int | None:
    """Conservative target used by the voice shell and harness.

    Scripted/prebuilt tiles can start nearly immediately once selected. Live
    generation remains bounded by the case target because no prerecorded line is
    available yet.
    """
    if tile.strategy in TILE_STRATEGIES and tile.line:
        return min(tile.max_first_audio_ms or 650, 300 if tile.strategy == "prebuilt_tile" else 500)
    if tile.strategy == "live_generate":
        return tile.max_first_audio_ms
    return tile.max_first_audio_ms


def _asset_id(case_id: str, intent: str, line: str | None) -> str | None:
    if not line:
        return None
    safe_intent = re.sub(r"[^a-z0-9_]+", "_", intent.lower()).strip("_")
    return f"ams/{case_id}-{safe_intent}.wav"


@lru_cache(maxsize=1)
def load_service_tiles(path: str | Path = DEFAULT_CASES) -> tuple[ServiceTile, ...]:
    tiles: list[ServiceTile] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        case = json.loads(raw)
        strategy = case.get("voice_strategy") or "live_generate"
        line = case.get("prebuilt_line")
        if not line and strategy == "lookup_line":
            line = "Je vais regarder le meilleur repère avant de te répondre."
        case_id = case["case_id"]
        intent = case["intent"]
        blocks_first_audio = strategy not in NON_BLOCKING_STRATEGIES
        tile_id = f"tile-{case_id}"
        path = encode_path(case)
        tiles.append(ServiceTile(
            tile_id=tile_id,
            case_id=case_id,
            intent=intent,
            trigger=normalize_question(case.get("question", "")),
            strategy=strategy,
            line=line,
            interruptible=bool(case.get("interruptible", True)),
            prebuilt_allowed=bool(case.get("prebuilt_allowed", False)),
            fallback_if_slow=case.get("fallback_if_slow"),
            max_first_audio_ms=case.get("max_first_audio_ms"),
            max_answer_ms=case.get("max_answer_ms"),
            asset_id=_asset_id(case_id, intent, line),
            asset_status="scripted" if line else "not_applicable",
            blocks_first_audio=blocks_first_audio,
            path_id=path.path_id,
            path_debug=path.path_debug,
            tile_sequence=(tile_id,),
            emotion_profile=case.get("emotion_profile"),
        ))
    return tuple(tiles)


@lru_cache(maxsize=1)
def _tile_index() -> dict[str, ServiceTile]:
    return {tile.trigger: tile for tile in load_service_tiles()}


@lru_cache(maxsize=1)
def _path_index() -> dict[int, ServiceTile]:
    return {tile.path_id: tile for tile in load_service_tiles()}


def select_service_tile(question: str) -> ServiceTile | None:
    """Return an exact-match tile for common AMS voice interactions."""
    return _tile_index().get(normalize_question(question))


def select_service_tile_by_path(path_id: int) -> ServiceTile | None:
    """Return a service tile by deterministic conversation path id."""
    return _path_index().get(path_id)


def tile_catalog() -> list[dict[str, Any]]:
    return [tile.voice_metadata() for tile in load_service_tiles()]
