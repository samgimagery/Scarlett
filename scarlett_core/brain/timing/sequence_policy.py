"""Scarlett sequence policy v0.

Turns speech tiles and micro-performance assets into a simple performance
sequence: speech, pause/room tone, optional receipts, and guardrails.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

MICRO_BANK_ROOT = Path("/Users/samg/Media/voices/scarlett_micro_bank/v0")

SequenceKind = Literal["speech", "pause", "room_tone", "vocal_micro"]


@dataclass(frozen=True)
class SequencePiece:
    kind: SequenceKind
    role: str
    asset_id: str | None = None
    path: str | None = None
    text: str | None = None
    duration_ms: int | None = None
    guardrail: str | None = None

    def metadata(self) -> dict:
        return asdict(self)


PAUSE_ASSETS = {
    180: MICRO_BANK_ROOT / "pause" / "room_tone_250ms.wav",  # nearest safe bed
    250: MICRO_BANK_ROOT / "pause" / "room_tone_250ms.wav",
    400: MICRO_BANK_ROOT / "pause" / "room_tone_400ms.wav",
    600: MICRO_BANK_ROOT / "pause" / "room_tone_600ms.wav",
}

VOCAL_MICROS = {
    "receipt_mhm": MICRO_BANK_ROOT / "generated" / "receipt_mhm_fr.wav",
    "thinking_hm": MICRO_BANK_ROOT / "generated" / "thinking_hm_fr.wav",
    "soft_ok": MICRO_BANK_ROOT / "generated" / "soft_ok_fr.wav",
    "oui_parfait": MICRO_BANK_ROOT / "generated" / "oui_parfait_fr.wav",
    "je_regarde": MICRO_BANK_ROOT / "generated" / "je_regarde_fr.wav",
}


def speech_piece(asset_id: str, path: str, text: str | None = None) -> SequencePiece:
    return SequencePiece(kind="speech", role="content_tile", asset_id=asset_id, path=path, text=text)


def pause_piece(duration_ms: int, role: str) -> SequencePiece:
    nearest = min(PAUSE_ASSETS, key=lambda ms: abs(ms - duration_ms))
    return SequencePiece(
        kind="room_tone",
        role=role,
        asset_id=f"room_tone_{nearest}ms",
        path=str(PAUSE_ASSETS[nearest]),
        duration_ms=nearest,
    )


def vocal_piece(asset_id: str, role: str, guardrail: str) -> SequencePiece:
    return SequencePiece(
        kind="vocal_micro",
        role=role,
        asset_id=asset_id,
        path=str(VOCAL_MICROS[asset_id]),
        guardrail=guardrail,
    )


def should_use_receipt(
    *,
    previous_act: str | None,
    next_act: str,
    same_turn: bool,
    caller_waiting: bool = True,
    repeated_recently: bool = False,
) -> bool:
    """Return whether a tiny receipt like Mm-hm belongs in the sequence.

    Use sparingly. A bad or repeated hum is worse than silence.
    """
    if repeated_recently:
        return False
    if not caller_waiting:
        return False
    if same_turn and previous_act in {"greeting", "identity"}:
        return False
    if next_act in {"answer", "orientation", "recommendation"}:
        return previous_act in {"caller_disclosure", "question", "uncertainty", "objection"}
    return False


def pause_after_act(act: str, *, word_count: int = 0, topic_shift: bool = False) -> int:
    if topic_shift:
        return 600
    if act in {"greeting", "handoff", "safety_boundary"}:
        return 600
    if act in {"receipt", "caller_disclosure", "objection"}:
        return 400
    if word_count >= 14:
        return 400
    if word_count >= 8:
        return 250
    return 180


def build_sequence(
    speech_assets: list[dict],
    *,
    previous_act: str | None = None,
    next_act: str = "answer",
    same_turn: bool = False,
    caller_waiting: bool = True,
    repeated_receipt_recently: bool = False,
) -> list[SequencePiece]:
    """Build a v0 performance sequence from content speech assets.

    speech_assets items: {asset_id, path, text?, act?, word_count?}
    """
    pieces: list[SequencePiece] = []
    if not speech_assets:
        return pieces

    if should_use_receipt(
        previous_act=previous_act,
        next_act=next_act,
        same_turn=same_turn,
        caller_waiting=caller_waiting,
        repeated_recently=repeated_receipt_recently,
    ):
        pieces.append(vocal_piece(
            "receipt_mhm",
            role="receipt_before_answer",
            guardrail="Use at most once per local exchange; never after greeting-only turns.",
        ))
        pieces.append(pause_piece(250, "post_receipt_breath"))

    for idx, item in enumerate(speech_assets):
        pieces.append(speech_piece(item["asset_id"], item["path"], item.get("text")))
        if idx == len(speech_assets) - 1:
            continue
        act = item.get("act") or "content"
        pause_ms = pause_after_act(act, word_count=int(item.get("word_count") or 0))
        pieces.append(pause_piece(pause_ms, f"between_{act}_and_next"))

    return pieces


def sequence_manifest(sequence: list[SequencePiece]) -> list[dict]:
    return [piece.metadata() for piece in sequence]
