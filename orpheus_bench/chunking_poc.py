#!/usr/bin/env python3
"""REQ-108 English chunking proof-of-concept for Orpheus-FastAPI.

Compares single-shot TTS against phrase chunks and records generation timing,
audio duration, RTF, and first-audio latency proxy. Requires Orpheus-FastAPI
running at --base-url.

Default model path is the approved English Q4 Ollama tag:
legraphista/Orpheus:latest (Q4_K_M). Q8 remains a quality reference only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "chunking_poc"
DEFAULT_MODEL = "legraphista/Orpheus:latest"
DEFAULT_MODEL_NOTE = "approved English Q4_K_M path; speed wins over Q8 clarity delta"

SCENARIOS = {
    "ams_intro": [
        "One moment.",
        "I found the program details.",
        "Level one is four hundred hours.",
        "The price is four thousand nine hundred ninety-five dollars.",
    ],
    "receptionist_flow": [
        "Absolutely.",
        "Let me check that for you.",
        "If you are already studying with AMS, I can help with your course, schedule, supplies, or next step.",
        "What would you like to sort out first?",
    ],
    "live_rag_feel": [
        "Of course.",
        "Let me just get that for you.",
        "I know where to look.",
        "Here we go.",
        "Level one is four hundred hours, and the price is four thousand nine hundred ninety-five dollars.",
    ],
    "warm_emotion": [
        "Of course <chuckle> let me check that for you.",
        "I found it.",
        "This is actually a nice place to start.",
        "Level one gives you the foundation before moving into the advanced courses.",
    ],
    "q4_receptionist_primitives": [
        "Yes.",
        "Absolutely.",
        "One moment.",
        "Let me check that for you.",
        "I know where to look.",
        "Here we go.",
        "I found it.",
        "Could I have your name, please?",
        "Thanks, Sam.",
        "That makes sense <chuckle> let me narrow it down.",
    ],
    "q4_turn_taking": [
        "Of course.",
        "Let me just get that for you.",
        "I know where to look.",
        "Here we go.",
        "The next cohort starts in September, and the full level one program is four hundred hours.",
        "If you like, I can also check schedule options for the Montreal campus.",
    ],
    "q4_filler_bank": [
        "Of course.",
        "One moment.",
        "Let me check that for you.",
        "Let me just get that for you.",
        "I know where to look.",
        "Here we go.",
        "I found it.",
        "Just a second.",
        "I can help with that.",
        "Let me narrow that down.",
        "That's the right place to start.",
        "That makes sense <chuckle> let me narrow it down.",
    ],
    "q4_interrupt_names": [
        "Sorry, go ahead.",
        "No problem, I can adjust that.",
        "Let me stop there.",
        "Could I have your name, please?",
        "Thanks, Sam.",
        "Thanks, Julie.",
        "For Montreal, I would check the campus schedule first.",
        "For Laval, I would check the next available cohort.",
    ],
}


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


def post_tts(base_url: str, text: str, voice: str, output: Path, model: str) -> dict:
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
        return {"ok": False, "error": str(e), "text": text}
    elapsed = time.perf_counter() - start
    output.write_bytes(body)
    dur = audio_duration(output)
    return {
        "ok": True,
        "model": model,
        "text": text,
        "file": str(output),
        "bytes": len(body),
        "content_type": content_type,
        "generation_s": round(elapsed, 3),
        "audio_s": round(dur, 3) if dur else None,
        "rtf": round(elapsed / dur, 3) if dur else None,
    }


def run_scenario(base_url: str, voice: str, model: str, name: str, chunks: list[str]) -> dict:
    safe_voice = voice.replace("/", "_")
    scenario_dir = OUT / f"{name}_{safe_voice}_{int(time.time())}"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    full_text = " ".join(chunks)

    single = post_tts(base_url, full_text, voice, scenario_dir / "single.wav", model)
    chunk_results = []
    chunk_start = time.perf_counter()
    first_chunk_done = None
    for i, chunk in enumerate(chunks, 1):
        res = post_tts(base_url, chunk, voice, scenario_dir / f"chunk_{i:02d}.wav", model)
        if first_chunk_done is None:
            first_chunk_done = time.perf_counter() - chunk_start
        chunk_results.append(res)
    total_chunk_wall = time.perf_counter() - chunk_start

    ok_chunks = [r for r in chunk_results if r.get("ok")]
    total_audio = sum((r.get("audio_s") or 0) for r in ok_chunks)
    total_generation = sum((r.get("generation_s") or 0) for r in ok_chunks)
    summary = {
        "scenario": name,
        "voice": voice,
        "model": model,
        "model_note": DEFAULT_MODEL_NOTE if model == DEFAULT_MODEL else "non-default comparison path",
        "output_dir": str(scenario_dir),
        "single": single,
        "chunks": chunk_results,
        "chunk_summary": {
            "chunk_count": len(chunks),
            "first_audio_proxy_s": round(first_chunk_done, 3) if first_chunk_done else None,
            "total_wall_s": round(total_chunk_wall, 3),
            "sum_generation_s": round(total_generation, 3),
            "sum_audio_s": round(total_audio, 3),
            "wall_rtf": round(total_chunk_wall / total_audio, 3) if total_audio else None,
        },
        "notes": "first_audio_proxy_s is time until first chunk file returns; real streaming playback would start there while later chunks generate.",
    }
    (scenario_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5005")
    parser.add_argument("--voice", default="tara")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI-compatible backend model name; default is approved Q4")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="ams_intro")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    result = run_scenario(args.base_url, args.voice, args.model, args.scenario, SCENARIOS[args.scenario])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
