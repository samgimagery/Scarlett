"""Scarlett Brain v1 public module boundary.

The Brain owns the product contract around a receptionist answer:
sources -> vault -> facts -> retrieval -> answer -> review.
"""
from .contract import BrainStage, BrainTrace, SCARLETT_BRAIN_CONTRACT
from .review import maybe_log_review, get_review_queue

__all__ = [
    "BrainStage",
    "BrainTrace",
    "SCARLETT_BRAIN_CONTRACT",
    "maybe_log_review",
    "get_review_queue",
]
