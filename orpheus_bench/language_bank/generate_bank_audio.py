#!/usr/bin/env python3
"""Generate Scarlett cached-bank audio clips through Orpheus-FastAPI.

Default: first-pass cache candidates from scarlett_en_live_bank.json using Q4 leah.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
import wave
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "language_bank" / "scarlett_en_live_bank.json"
OUT_ROOT = ROOT / "outputs" / "language_bank"
DEFAULT_MODEL = "legraphista/Orpheus:latest"
DEFAULT_VOICE = "leah"
FIRST_PASS_TYPES = {"backchannel", "receipt", "floor_holder", "retrieval_progress", "repair", "interruption"}
FIRST_PASS_PRIORITIES = {"critical", "high"}


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return None


def ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ], text=True, stderr=subprocess.DEVNULL, timeout=10)
        return float(out.strip())
    except Exception:
        return None


def audio_duration(path: Path) -> float | None:
    return wav_duration(path) or ffprobe_duration(path)


def load_bank(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_first_pass(line: dict) -> bool:
    return (
        line.get("text")
        and line.get("type") in FIRST_PASS_TYPES
        and line.get("cache_priority") in FIRST_PASS_PRIORITIES
        and line.get("requires_manual_review") is not True
    )


def post_tts(base_url: str, model: str, voice: str, text: str, output: Path) -> dict:
    payload = json.dumps({
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "wav",
        "speed": 1.0,
    }).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=180) as resp:
            body = resp.read()
            content_type = resp.headers.get("content-type", "")
    except error.URLError as e:
        return {"ok": False, "error": str(e), "text": text, "file": str(output)}
    elapsed = time.perf_counter() - start
    output.write_bytes(body)
    dur = audio_duration(output)
    return {
        "ok": True,
        "text": text,
        "file": str(output),
        "bytes": len(body),
        "content_type": content_type,
        "generation_s": round(elapsed, 3),
        "audio_s": round(dur, 3) if dur else None,
        "rtf": round(elapsed / dur, 3) if dur else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, default=BANK)
    parser.add_argument("--base-url", default="http://127.0.0.1:5005")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--first-pass", action="store_true", default=True)
    parser.add_argument("--all", action="store_true", help="Generate all non-empty, non-manual lines")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    bank = load_bank(args.bank)
    if args.all:
        lines = [line for line in bank["lines"] if line.get("text") and line.get("requires_manual_review") is not True]
    else:
        lines = [line for line in bank["lines"] if is_first_pass(line)]
    if args.limit:
        lines = lines[: args.limit]

    run_dir = args.output_dir or (OUT_ROOT / f"{bank['version']}_{args.voice}_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = run_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    results = []
    for idx, line in enumerate(lines, 1):
        out = clips_dir / f"{idx:02d}_{line['id']}.wav"
        if args.skip_existing and out.exists():
            dur = audio_duration(out)
            res = {"ok": True, "file": str(out), "generation_s": None, "audio_s": round(dur, 3) if dur else None, "rtf": None, "skipped": True}
        else:
            res = post_tts(args.base_url, args.model, args.voice, line["text"], out)
        row = {
            "index": idx,
            "id": line["id"],
            "type": line.get("type"),
            "cache_priority": line.get("cache_priority"),
            "intent": line.get("intent"),
            "text": line["text"],
            "voice": args.voice,
            "model": args.model,
            **res,
            "review": "",
            "review_notes": "",
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    metrics = {
        "bank": bank["name"],
        "version": bank["version"],
        "voice": args.voice,
        "model": args.model,
        "line_count": len(results),
        "ok_count": sum(1 for r in results if r.get("ok")),
        "output_dir": str(run_dir),
        "clips_dir": str(clips_dir),
        "total_generation_s": round(sum((r.get("generation_s") or 0) for r in results), 3),
        "total_audio_s": round(sum((r.get("audio_s") or 0) for r in results), 3),
        "results": results,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    with (run_dir / "review_sheet.tsv").open("w", newline="", encoding="utf-8") as f:
        fields = ["index", "id", "type", "cache_priority", "text", "audio_s", "generation_s", "rtf", "file", "review", "review_notes"]
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps({k: v for k, v in metrics.items() if k != "results"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
