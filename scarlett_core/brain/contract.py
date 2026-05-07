"""Scarlett Brain v1 contract and trace objects.

This is intentionally small: it gives the current AMS receptionist a real
product boundary without forcing a risky rewrite of the working RAG service.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


SCARLETT_BRAIN_CONTRACT = {
    "version": "1.0",
    "pipeline": [
        "sources",
        "vault",
        "facts",
        "retrieval",
        "answer",
        "review",
    ],
    "principles": [
        "Answer from deterministic facts when exactness matters.",
        "Retrieve vault context before generating flexible answers.",
        "Never expose internal vault/source implementation details to customers.",
        "Escalate only after orienting the customer when useful information exists.",
        "Log weak answers as review items so corrections become durable tuning inputs.",
    ],
}


@dataclass
class BrainStage:
    name: str
    status: str
    source: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BrainTrace:
    question: str
    language: str
    customer_id: str = "ams"
    conversation_context_present: bool = False
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stages: list[BrainStage] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        question: str,
        language: str,
        *,
        customer_id: str = "ams",
        conversation_context: str | None = None,
    ) -> "BrainTrace":
        return cls(
            question=question,
            language=language,
            customer_id=customer_id,
            conversation_context_present=bool(conversation_context),
        )

    def add(
        self,
        name: str,
        status: str,
        *,
        source: str | None = None,
        score: float | None = None,
        **metadata: Any,
    ) -> None:
        self.stages.append(
            BrainStage(name=name, status=status, source=source, score=score, metadata=metadata)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": SCARLETT_BRAIN_CONTRACT["version"],
            "customer_id": self.customer_id,
            "question": self.question,
            "language": self.language,
            "conversation_context_present": self.conversation_context_present,
            "started_at": self.started_at,
            "stages": [stage.to_dict() for stage in self.stages],
        }
