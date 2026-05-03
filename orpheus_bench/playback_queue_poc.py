#!/usr/bin/env python3
"""REQ-108 playback queue proof-of-concept.

Stitches chunk_*.wav files from chunking_poc.py into a single queue output with:
- basic leading/trailing silence trim
- short linear crossfade between chunks

This is not the final runtime queue. It is a fast listen-test artifact for judging
whether phrase/sentence chunking can feel continuous enough for Scarlett.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path


def read_wav(path: Path) -> tuple[wave._wave_params, list[int]]:
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        if params.sampwidth != 2:
            raise ValueError(f"{path} uses sampwidth={params.sampwidth}; expected 16-bit PCM")
        if params.nchannels != 1:
            raise ValueError(f"{path} uses nchannels={params.nchannels}; expected mono")
        raw = wf.readframes(params.nframes)
    samples = list(struct.unpack(f"<{len(raw)//2}h", raw))
    return params, samples


def write_wav(path: Path, params: wave._wave_params, samples: list[int]) -> None:
    raw = struct.pack(f"<{len(samples)}h", *[max(-32768, min(32767, int(s))) for s in samples])
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(params.nchannels)
        wf.setsampwidth(params.sampwidth)
        wf.setframerate(params.framerate)
        wf.writeframes(raw)


def trim_silence(samples: list[int], threshold: int, keep: int) -> tuple[list[int], int, int]:
    if not samples:
        return samples, 0, 0
    start = 0
    while start < len(samples) and abs(samples[start]) < threshold:
        start += 1
    end = len(samples) - 1
    while end > start and abs(samples[end]) < threshold:
        end -= 1
    trim_start = max(0, start - keep)
    trim_end = min(len(samples), end + 1 + keep)
    return samples[trim_start:trim_end], trim_start, len(samples) - trim_end


def crossfade_append(base: list[int], nxt: list[int], fade: int) -> list[int]:
    if not base:
        return nxt[:]
    if not nxt:
        return base
    n = min(fade, len(base), len(nxt))
    if n <= 0:
        return base + nxt
    head = base[:-n]
    tail = []
    for i in range(n):
        a = i / max(1, n - 1)
        tail.append(round(base[-n + i] * (1 - a) + nxt[i] * a))
    return head + tail + nxt[n:]


def rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_dir", type=Path)
    parser.add_argument("--crossfade-ms", type=float, default=45.0)
    parser.add_argument("--silence-threshold", type=int, default=90)
    parser.add_argument("--keep-ms", type=float, default=35.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    chunk_files = sorted(args.scenario_dir.glob("chunk_*.wav"))
    if not chunk_files:
        raise SystemExit(f"No chunk_*.wav files found in {args.scenario_dir}")

    params = None
    queue: list[int] = []
    chunk_notes = []
    for path in chunk_files:
        p, samples = read_wav(path)
        if params is None:
            params = p
        elif (p.nchannels, p.sampwidth, p.framerate) != (params.nchannels, params.sampwidth, params.framerate):
            raise ValueError(f"{path} WAV params do not match first chunk")
        keep = int(params.framerate * args.keep_ms / 1000)
        trimmed, trim_start, trim_end = trim_silence(samples, args.silence_threshold, keep)
        fade = int(params.framerate * args.crossfade_ms / 1000)
        queue = crossfade_append(queue, trimmed, fade)
        chunk_notes.append({
            "file": str(path),
            "original_s": round(len(samples) / params.framerate, 3),
            "trimmed_s": round(len(trimmed) / params.framerate, 3),
            "trim_start_s": round(trim_start / params.framerate, 3),
            "trim_end_s": round(trim_end / params.framerate, 3),
            "rms": round(rms(trimmed), 1),
        })

    out = args.output or (args.scenario_dir / "stitched_queue.wav")
    write_wav(out, params, queue)
    metrics = {
        "source_dir": str(args.scenario_dir),
        "output": str(out),
        "chunk_count": len(chunk_files),
        "crossfade_ms": args.crossfade_ms,
        "silence_threshold": args.silence_threshold,
        "keep_ms": args.keep_ms,
        "duration_s": round(len(queue) / params.framerate, 3),
        "chunks": chunk_notes,
        "notes": "Listen for seam quality and pacing. This simulates queued playback; real runtime should start playback as soon as the first cached/generated chunk exists.",
    }
    (args.scenario_dir / "stitched_queue_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
