#!/usr/bin/env python3
"""Scarlett live-voice speed matrix.

Runs repeatable timing attempts across the layers that affect perceived voice
speed: tile selection, /ask + voice metadata, cached audio, live TTS engines,
and optional local fast TTS servers.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics as stats
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
RECEPTIONIST_ROOT = ROOT.parents[2]
if str(RECEPTIONIST_ROOT) not in sys.path:
    sys.path.insert(0, str(RECEPTIONIST_ROOT))

from scarlett_core.brain.timing.service_tiles import load_service_tiles, select_service_tile

DEFAULT_ASK_URL = "http://127.0.0.1:8000/ask"
DEFAULT_TILES_URL = "http://127.0.0.1:8000/brain/service-tiles"
DEFAULT_VOICE_URL = "http://127.0.0.1:8788/api/voice"
DEFAULT_CSM_URL = "http://127.0.0.1:8766/generate"
REPORT_DIR = ROOT / "reports" / "voice_speed"
PREFILLER_MANIFEST = Path("/Users/samg/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_fr_lora_overnight_20260504-215150/prefiller_bank_req112_v2_p0_speed075/manifest.json")


@dataclass
class Attempt:
    approach: str
    label: str
    ok: bool
    elapsed_ms: float
    bytes: int = 0
    error: str | None = None
    meta: dict[str, Any] | None = None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] * (c - k) + values[c] * (k - f)


def summarize(attempts: list[Attempt]) -> dict[str, Any]:
    groups: dict[str, list[Attempt]] = {}
    for a in attempts:
        groups.setdefault(a.approach, []).append(a)
    rows = []
    for approach, items in sorted(groups.items()):
        ok = [a.elapsed_ms for a in items if a.ok]
        rows.append({
            "approach": approach,
            "attempts": len(items),
            "ok": len(ok),
            "fail": len(items) - len(ok),
            "min_ms": round(min(ok), 1) if ok else None,
            "median_ms": round(stats.median(ok), 1) if ok else None,
            "p90_ms": round(percentile(ok, 0.9), 1) if ok else None,
            "max_ms": round(max(ok), 1) if ok else None,
            "avg_bytes": round(stats.mean([a.bytes for a in items if a.ok and a.bytes]), 1) if any(a.ok and a.bytes for a in items) else 0,
        })
    rows.sort(key=lambda r: (r["median_ms"] is None, r["median_ms"] or 10**9))
    return {"groups": rows}


def timed(approach: str, label: str, fn: Callable[[], Any]) -> Attempt:
    start = time.perf_counter()
    try:
        out = fn()
        elapsed = (time.perf_counter() - start) * 1000
        if out is None:
            return Attempt(approach, label, False, elapsed, error="no output")
        size = 0
        meta: dict[str, Any] = {}
        if isinstance(out, bytes):
            size = len(out)
        elif isinstance(out, dict):
            meta = {k: v for k, v in out.items() if k != "audio_base64"}
            if out.get("audio_base64"):
                size = len(base64.b64decode(out["audio_base64"]))
            elif out.get("bytes"):
                size = int(out.get("bytes") or 0)
        elif isinstance(out, str) and os.path.exists(out):
            size = os.path.getsize(out)
            meta = {"path": out}
        return Attempt(approach, label, True, elapsed, size, meta=meta)
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return Attempt(approach, label, False, elapsed, error=repr(e))


def post_json(url: str, payload: dict[str, Any], timeout: float = 90) -> Any:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return json.loads(body.decode("utf-8"))
        return body


def get_json(url: str, timeout: float = 30) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def selected_tiles(limit: int) -> list[Any]:
    tiles = [t for t in load_service_tiles() if t.line]
    priority = [
        "ams-int-001", "ams-int-005", "ams-int-011", "ams-int-019", "ams-int-023",
        "ams-int-027", "ams-int-036", "ams-int-041", "ams-int-046", "ams-int-050",
        "ams-int-006", "ams-int-007", "ams-int-017", "ams-int-043", "ams-int-044",
    ]
    by_id = {t.case_id: t for t in tiles}
    ordered = [by_id[i] for i in priority if i in by_id]
    ordered += [t for t in tiles if t.case_id not in priority]
    return ordered[:limit]


def load_prefiller_files(limit: int = 20) -> list[Path]:
    if not PREFILLER_MANIFEST.exists():
        return []
    items = json.loads(PREFILLER_MANIFEST.read_text(encoding="utf-8"))
    paths = []
    for item in items:
        p = Path(item.get("wav") or "")
        if item.get("ok") and p.exists():
            paths.append(p)
    return paths[:limit]


def run(args: argparse.Namespace) -> dict[str, Any]:
    attempts: list[Attempt] = []
    tiles = selected_tiles(args.tile_limit)

    # 1. In-process route selection: upper bound for how fast tile decision can be.
    triggers = [t.trigger for t in load_service_tiles()]
    for i in range(args.tile_select_attempts):
        q = triggers[i % len(triggers)]
        attempts.append(timed("tile_select_inprocess", q, lambda q=q: select_service_tile(q).voice_metadata()))

    # 2. HTTP catalog call: cheap remote metadata lookup.
    for i in range(args.http_metadata_attempts):
        attempts.append(timed("service_tiles_http_catalog", "GET /brain/service-tiles", lambda: get_json(args.tiles_url)))

    # 3. /ask with real Scarlett answer + voice metadata.
    for r in range(args.ask_attempts):
        for tile in tiles:
            attempts.append(timed("ask_with_voice_metadata", tile.case_id, lambda tile=tile: post_json(args.ask_url, {"question": tile.trigger, "language": "fr"}, timeout=90)))

    # 4. Cached/prebuilt file read: production target once tiles are recorded.
    prefiller_files = load_prefiller_files(args.prefiller_limit)
    for r in range(args.cached_attempts):
        for p in prefiller_files:
            attempts.append(timed("cached_wav_file_read", p.name, lambda p=p: p.read_bytes()))

    # 5. Mind Vault /api/voice current Scarlett path (Qwen FR LoRA for French).
    for r in range(args.voice_attempts):
        for tile in tiles[:args.voice_tile_limit]:
            attempts.append(timed("http_voice_scarlett_qwen_fr", tile.case_id, lambda tile=tile: post_json(args.voice_url, {"text": tile.line, "language": "fr", "mode": "scarlett", "debug": True}, timeout=180)))

    # 6. Direct TTS approaches inside this process, avoiding HTTP overhead.
    if args.direct_tts:
        import tts
        for r in range(args.direct_attempts):
            for tile in tiles[:args.direct_tile_limit]:
                attempts.append(timed("direct_qwen_fr_lora", tile.case_id, lambda tile=tile: tts.generate_voice(tile.line, lang="fr", speed=0.6)))
        for r in range(args.kokoro_attempts):
            for tile in tiles[:args.direct_tile_limit]:
                attempts.append(timed("direct_kokoro_fr_fast", tile.case_id, lambda tile=tile: tts._generate_kokoro(tile.line, "fr", "bf_alice", 1.05)))

    # 7. Optional CSM filler endpoint if running.
    for r in range(args.csm_attempts):
        attempts.append(timed("csm_filler_http", "short filler", lambda: post_json(args.csm_url, {"text": "Oui, je regarde ça.", "max_audio_ms": 1600}, timeout=15)))

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": vars(args),
        "tile_count_available": len(load_service_tiles()),
        "tile_count_tested": len(tiles),
        "prefiller_files_tested": len(prefiller_files),
        "summary": summarize(attempts),
        "attempts": [asdict(a) for a in attempts],
    }
    return out


def write_reports(result: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_DIR / f"voice_speed_matrix_{stamp}.json"
    md_path = json_path.with_suffix(".md")
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Scarlett Voice Speed Matrix",
        "",
        f"Generated: {result['generated_at']}",
        f"Tiles tested: {result['tile_count_tested']} / {result['tile_count_available']}",
        f"Cached prefiller files tested: {result['prefiller_files_tested']}",
        "",
        "## Summary",
        "",
        "| Approach | Attempts | OK | Fail | Min ms | Median ms | P90 ms | Max ms | Avg bytes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["summary"]["groups"]:
        lines.append(
            f"| {row['approach']} | {row['attempts']} | {row['ok']} | {row['fail']} | "
            f"{row['min_ms']} | {row['median_ms']} | {row['p90_ms']} | {row['max_ms']} | {row['avg_bytes']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- `tile_select_inprocess` is the decision cost for choosing a service tile.",
        "- `cached_wav_file_read` approximates production pre-recorded tile playback readiness.",
        "- `ask_with_voice_metadata` measures text answer + tile metadata; this can run while cached audio plays.",
        "- `http_voice_scarlett_qwen_fr` / `direct_qwen_fr_lora` measure current live TTS generation and should not block first audio for common cases.",
        "- `direct_kokoro_fr_fast` is a quality tradeoff baseline: much faster, less on-brand.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask-url", default=DEFAULT_ASK_URL)
    parser.add_argument("--tiles-url", default=DEFAULT_TILES_URL)
    parser.add_argument("--voice-url", default=DEFAULT_VOICE_URL)
    parser.add_argument("--csm-url", default=DEFAULT_CSM_URL)
    parser.add_argument("--tile-limit", type=int, default=20)
    parser.add_argument("--tile-select-attempts", type=int, default=5000)
    parser.add_argument("--http-metadata-attempts", type=int, default=100)
    parser.add_argument("--ask-attempts", type=int, default=3)
    parser.add_argument("--cached-attempts", type=int, default=25)
    parser.add_argument("--prefiller-limit", type=int, default=20)
    parser.add_argument("--voice-attempts", type=int, default=2)
    parser.add_argument("--voice-tile-limit", type=int, default=8)
    parser.add_argument("--direct-tts", action="store_true")
    parser.add_argument("--direct-attempts", type=int, default=1)
    parser.add_argument("--kokoro-attempts", type=int, default=2)
    parser.add_argument("--direct-tile-limit", type=int, default=6)
    parser.add_argument("--csm-attempts", type=int, default=20)
    args = parser.parse_args()
    result = run(args)
    json_path, md_path = write_reports(result)
    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    for row in result["summary"]["groups"]:
        print(f"{row['approach']}: median={row['median_ms']}ms p90={row['p90_ms']}ms ok={row['ok']}/{row['attempts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
