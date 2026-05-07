"""Deterministic integer path encoding for Scarlett service tiles.

The path id describes what Scarlett is about to say. Delivery variants such as
emotion/prosody stay outside the id for v0 so the content route remains stable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

VERSION = 1
UNKNOWN = "unknown"

# Fixed registries. Do not derive these from sorted live data; that would make
# ids drift when new values are added. Reserve integer 0 for unknown in every
# semantic field.
BUSINESS = {
    UNKNOWN: 0,
    "AMS": 1,
}

FLOW = {
    UNKNOWN: 0,
    "identity": 1,
    "service_confidence": 2,
    "program_path": 3,
    "pricing": 4,
    "location": 5,
    "signup": 6,
    "continuing_ed": 7,
    "conversation_repair": 8,
    "voice_control": 9,
    "safety": 10,
    "objection": 11,
    "handoff": 12,
}

CALLER_STAGE = {
    UNKNOWN: 0,
    "prospect": 1,
    "beginner": 2,
    "trained_practitioner": 3,
    "current_student": 4,
    "continuing_ed_prospect": 5,
    "frustrated": 6,
}

STRATEGY = {
    UNKNOWN: 0,
    "prebuilt_tile": 1,
    "receipt": 2,
    "lookup_line": 3,
    "hybrid_tile_then_generate": 4,
    "clarify": 5,
    "live_generate": 6,
    "handoff_or_escalate": 7,
}

SLOT = {
    UNKNOWN: 0,
    "none": 1,
    "program": 2,
    "price": 3,
    "campus": 4,
    "course": 5,
    "signup_action": 6,
    "repair_type": 7,
    "safety_type": 8,
    "objection_type": 9,
    "handoff_target": 10,
}

VALUE = {
    UNKNOWN: 0,
    "none": 1,
    "n1": 2,
    "n2": 3,
    "n3": 4,
    "n1_n2": 5,
    "all_levels": 6,
    "financing": 7,
    "weekly": 8,
    "montreal": 9,
    "laval": 10,
    "unknown_city": 11,
    "direct_signup": 12,
    "signup_link": 13,
    "reserve_place": 14,
    "drainage_lymphatique": 15,
    "massage_sportif": 16,
    "aromatherapie": 17,
    "repeat": 18,
    "unclear": 19,
    "didnt_hear": 20,
    "stt_failure": 21,
    "interrupt": 22,
    "internal_sources": 23,
    "prompt_injection": 24,
    "payment": 25,
    "time": 26,
    "duration": 27,
    "frustration": 28,
    "julie": 29,
    "human": 30,
    "old_bot": 31,
    "capability": 32,
    "campus_list": 33,
}

INTENT = {
    UNKNOWN: 0,
    "greeting": 1,
    "greeting_allo": 2,
    "identity": 3,
    "how_are_you": 4,
    "how_it_works": 5,
    "beginner_path": 6,
    "trained_path": 7,
    "current_student": 8,
    "unsure_start": 9,
    "compare_paths": 10,
    "price_n1": 11,
    "price_n2": 12,
    "price_n3": 13,
    "total_n1_n2": 14,
    "total_all": 15,
    "financing": 16,
    "weekly": 17,
    "too_expensive": 18,
    "campus_list": 19,
    "nearest_campus": 20,
    "campus_address": 21,
    "city_unknown": 22,
    "signup_direct": 23,
    "signup_link": 24,
    "reserve_place": 25,
    "oui_after_offer": 26,
    "continuing_ed_list": 27,
    "specific_course": 28,
    "sport_course": 29,
    "aroma_course": 30,
    "start_dates": 31,
    "schedule": 32,
    "recognized": 33,
    "prerequisites": 34,
    "online_hybrid": 35,
    "repeat": 36,
    "unclear": 37,
    "didnt_hear": 38,
    "stt_failure": 39,
    "interrupt": 40,
    "internal_sources": 41,
    "prompt_injection": 42,
    "payment_objection": 43,
    "time_objection": 44,
    "too_long": 45,
    "frustrated": 46,
    "julie": 47,
    "human": 48,
    "old_bot": 49,
    "what_can_help": 50,
}

WIDTHS = {
    "version": 4,
    "business": 4,
    "flow": 5,
    "caller_stage": 4,
    "strategy": 4,
    "slot": 5,
    "value": 6,
    "intent": 8,
}

REGISTRIES = {
    "business": BUSINESS,
    "flow": FLOW,
    "caller_stage": CALLER_STAGE,
    "strategy": STRATEGY,
    "slot": SLOT,
    "value": VALUE,
    "intent": INTENT,
}

REVERSE_REGISTRIES = {
    field: {value: label for label, value in registry.items()}
    for field, registry in REGISTRIES.items()
}

PACK_ORDER = ("version", "business", "flow", "caller_stage", "strategy", "slot", "value", "intent")

ROUTE_TO_FLOW = {
    "local_identity_layer": "identity",
    "local_service_confidence_layer": "service_confidence",
    "rag_or_service_flow": "program_path",
    "local_pricing_layer": "pricing",
    "local_location_layer": "location",
    "telegram_or_service_flow": "signup",
    "local_continuing_ed_layer": "continuing_ed",
    "conversation_state": "conversation_repair",
    "voice_control": "voice_control",
    "local_safety_layer": "safety",
}

INTENT_HINTS = {
    "greeting": ("identity", "prospect", "none", "none"),
    "greeting_allo": ("identity", "prospect", "none", "none"),
    "identity": ("identity", "prospect", "none", "none"),
    "how_are_you": ("identity", "prospect", "none", "none"),
    "how_it_works": ("service_confidence", "prospect", "none", "none"),
    "beginner_path": ("program_path", "beginner", "program", "n1"),
    "trained_path": ("program_path", "trained_practitioner", "program", "n2"),
    "current_student": ("program_path", "current_student", "program", "none"),
    "unsure_start": ("program_path", "prospect", "program", "none"),
    "compare_paths": ("program_path", "prospect", "program", "n1_n2"),
    "price_n1": ("pricing", "prospect", "price", "n1"),
    "price_n2": ("pricing", "prospect", "price", "n2"),
    "price_n3": ("pricing", "prospect", "price", "n3"),
    "total_n1_n2": ("pricing", "prospect", "price", "n1_n2"),
    "total_all": ("pricing", "prospect", "price", "all_levels"),
    "financing": ("pricing", "prospect", "price", "financing"),
    "weekly": ("pricing", "prospect", "price", "weekly"),
    "too_expensive": ("objection", "prospect", "objection_type", "payment"),
    "campus_list": ("location", "prospect", "campus", "campus_list"),
    "nearest_campus": ("location", "prospect", "campus", "laval"),
    "campus_address": ("location", "prospect", "campus", "montreal"),
    "city_unknown": ("location", "prospect", "campus", "unknown_city"),
    "signup_direct": ("signup", "prospect", "signup_action", "direct_signup"),
    "signup_link": ("signup", "prospect", "signup_action", "signup_link"),
    "reserve_place": ("signup", "prospect", "signup_action", "reserve_place"),
    "oui_after_offer": ("conversation_repair", "prospect", "none", "none"),
    "continuing_ed_list": ("continuing_ed", "continuing_ed_prospect", "course", "none"),
    "specific_course": ("continuing_ed", "continuing_ed_prospect", "course", "drainage_lymphatique"),
    "sport_course": ("continuing_ed", "continuing_ed_prospect", "course", "massage_sportif"),
    "aroma_course": ("continuing_ed", "continuing_ed_prospect", "course", "aromatherapie"),
    "repeat": ("conversation_repair", "prospect", "repair_type", "repeat"),
    "unclear": ("conversation_repair", "prospect", "repair_type", "unclear"),
    "didnt_hear": ("conversation_repair", "prospect", "repair_type", "didnt_hear"),
    "stt_failure": ("conversation_repair", "prospect", "repair_type", "stt_failure"),
    "interrupt": ("voice_control", "prospect", "repair_type", "interrupt"),
    "internal_sources": ("safety", "prospect", "safety_type", "internal_sources"),
    "prompt_injection": ("safety", "prospect", "safety_type", "prompt_injection"),
    "payment_objection": ("objection", "prospect", "objection_type", "payment"),
    "time_objection": ("objection", "prospect", "objection_type", "time"),
    "too_long": ("objection", "prospect", "objection_type", "duration"),
    "frustrated": ("objection", "frustrated", "objection_type", "frustration"),
    "julie": ("handoff", "current_student", "handoff_target", "julie"),
    "human": ("handoff", "prospect", "handoff_target", "human"),
    "old_bot": ("objection", "prospect", "objection_type", "old_bot"),
    "what_can_help": ("service_confidence", "prospect", "none", "capability"),
}


@dataclass(frozen=True)
class PathEncoding:
    version: int
    business: str
    flow: str
    caller_stage: str
    strategy: str
    slot: str
    value: str
    intent: str
    path_id: int
    path_debug: str

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


def _registry_value(field: str, label: str) -> int:
    registry = REGISTRIES[field]
    value = registry.get(label, registry[UNKNOWN])
    max_value = (1 << WIDTHS[field]) - 1
    if value > max_value:
        raise ValueError(f"{field}={label!r} overflows {WIDTHS[field]} bits")
    return value


def _pack(values: dict[str, int]) -> int:
    out = 0
    for field in PACK_ORDER:
        width = WIDTHS[field]
        value = values[field]
        if value < 0 or value >= (1 << width):
            raise ValueError(f"{field} value {value} overflows {width} bits")
        out = (out << width) | value
    return out


def _unpack(path_id: int) -> dict[str, int]:
    if path_id < 0:
        raise ValueError("path_id must be non-negative")
    values: dict[str, int] = {}
    remaining = path_id
    for field in reversed(PACK_ORDER):
        width = WIDTHS[field]
        mask = (1 << width) - 1
        values[field] = remaining & mask
        remaining >>= width
    if remaining:
        raise ValueError(f"path_id {path_id} exceeds v{VERSION} packing width")
    return values


def infer_path(case: dict[str, Any]) -> dict[str, str]:
    explicit = case.get("path") or {}
    intent = case.get("intent") or UNKNOWN
    hinted = INTENT_HINTS.get(intent)
    if hinted:
        flow, caller_stage, slot, value = hinted
    else:
        flow = ROUTE_TO_FLOW.get(case.get("expected_route"), UNKNOWN)
        caller_stage, slot, value = UNKNOWN, UNKNOWN, UNKNOWN
    return {
        "business": explicit.get("business") or "AMS",
        "flow": explicit.get("flow") or flow,
        "caller_stage": explicit.get("caller_stage") or caller_stage,
        "strategy": explicit.get("strategy") or case.get("voice_strategy") or UNKNOWN,
        "slot": explicit.get("slot") or slot,
        "value": explicit.get("value") or value,
        "intent": explicit.get("intent") or intent,
    }


def _debug_string(version: int, fields: dict[str, str]) -> str:
    return ".".join([
        f"v{version}",
        fields["business"],
        fields["flow"],
        fields["caller_stage"],
        fields["intent"],
        fields["slot"],
        fields["value"],
        fields["strategy"],
    ])


def encode_path(case: dict[str, Any]) -> PathEncoding:
    fields = infer_path(case)
    values = {"version": VERSION}
    values.update({field: _registry_value(field, fields[field]) for field in REGISTRIES})
    path_id = _pack(values)
    path_debug = _debug_string(VERSION, fields)
    return PathEncoding(version=VERSION, path_id=path_id, path_debug=path_debug, **fields)


def decode_path(path_id: int) -> PathEncoding:
    values = _unpack(path_id)
    version = values["version"]
    if version != VERSION:
        raise ValueError(f"unsupported path version {version}; expected {VERSION}")
    fields = {
        field: REVERSE_REGISTRIES[field].get(values[field], UNKNOWN)
        for field in REGISTRIES
    }
    return PathEncoding(
        version=version,
        path_id=path_id,
        path_debug=_debug_string(version, fields),
        **fields,
    )
