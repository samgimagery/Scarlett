#!/usr/bin/env python3
"""Build raw and cleaned review reels for Orpheus language-bank clips.

The cleaned reel is deliberately conservative:
- trim leading/trailing low-level silence while keeping breath room
- short cosine fade-in/out per clip
- peak normalize per clip
- fixed inter-clip gaps instead of crossfading unrelated utterances

This is for listening review, not production runtime.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import wave
from pathlib import Path


def read_wav(path: Path):
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        if params.sampwidth != 2 or params.nchannels != 1:
            raise ValueError(f"{path} must be 16-bit mono PCM; got {params}")
        raw = wf.readframes(params.nframes)
    samples = list(struct.unpack(f"<{len(raw)//2}h", raw))
    return params, samples


def write_wav(path: Path, params, samples: list[int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = [max(-32768, min(32767, int(round(s)))) for s in samples]
    raw = struct.pack(f"<{len(clipped)}h", *clipped)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(params.framerate)
        wf.writeframes(raw)


def trim(samples: list[int], threshold: int, keep: int):
    if not samples:
        return samples, 0, 0
    start = 0
    while start < len(samples) and abs(samples[start]) < threshold:
        start += 1
    end = len(samples) - 1
    while end > start and abs(samples[end]) < threshold:
        end -= 1
    a = max(0, start - keep)
    b = min(len(samples), end + 1 + keep)
    return samples[a:b], a, len(samples) - b


def fade(samples: list[int], rate: int, in_ms: float, out_ms: float):
    out = samples[:]
    n_in = min(len(out), int(rate * in_ms / 1000))
    n_out = min(len(out), int(rate * out_ms / 1000))
    for i in range(n_in):
        g = 0.5 - 0.5 * math.cos(math.pi * i / max(1, n_in - 1))
        out[i] *= g
    for i in range(n_out):
        g = 0.5 + 0.5 * math.cos(math.pi * i / max(1, n_out - 1))
        out[-n_out + i] *= g
    return out


def normalize_peak(samples: list[int], target: float):
    peak = max((abs(s) for s in samples), default=0)
    if peak <= 0:
        return samples, 1.0, peak
    gain = min(4.0, (32767 * target) / peak)
    return [s * gain for s in samples], gain, peak


def rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s*s for s in samples) / len(samples))


def make_reel(clips: list[Path], output: Path, cleaned: bool, gap_ms: float, threshold: int, keep_ms: float, fade_in_ms: float, fade_out_ms: float, target_peak: float):
    params = None
    reel: list[int] = []
    notes = []
    for clip in clips:
        p, samples = read_wav(clip)
        if params is None:
            params = p
        elif p.framerate != params.framerate:
            raise ValueError(f"Sample rate mismatch: {clip}")
        original_len = len(samples)
        trim_start = trim_end = 0
        gain = 1.0
        peak = max((abs(s) for s in samples), default=0)
        if cleaned:
            keep = int(p.framerate * keep_ms / 1000)
            samples, trim_start, trim_end = trim(samples, threshold, keep)
            samples, gain, peak = normalize_peak(samples, target_peak)
            samples = fade(samples, p.framerate, fade_in_ms, fade_out_ms)
        reel.extend(samples)
        reel.extend([0] * int(p.framerate * gap_ms / 1000))
        notes.append({
            "file": str(clip),
            "original_s": round(original_len / p.framerate, 3),
            "output_s": round(len(samples) / p.framerate, 3),
            "trim_start_s": round(trim_start / p.framerate, 3),
            "trim_end_s": round(trim_end / p.framerate, 3),
            "peak": peak,
            "gain": round(gain, 3),
            "rms": round(rms([int(s) for s in samples]), 1),
        })
    write_wav(output, params, reel)
    meta = {
        "output": str(output),
        "cleaned": cleaned,
        "clip_count": len(clips),
        "duration_s": round(len(reel) / params.framerate, 3),
        "gap_ms": gap_ms,
        "threshold": threshold,
        "keep_ms": keep_ms,
        "fade_in_ms": fade_in_ms,
        "fade_out_ms": fade_out_ms,
        "target_peak": target_peak,
        "clips": notes,
    }
    output.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def to_m4a(wav: Path):
    m4a = wav.with_suffix(".m4a")
    subprocess.check_call(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "128k", str(m4a)])
    return m4a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips_dir", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--gap-ms", type=float, default=550)
    ap.add_argument("--threshold", type=int, default=120)
    ap.add_argument("--keep-ms", type=float, default=65)
    ap.add_argument("--fade-in-ms", type=float, default=8)
    ap.add_argument("--fade-out-ms", type=float, default=35)
    ap.add_argument("--target-peak", type=float, default=0.82)
    args = ap.parse_args()

    clips = sorted(args.clips_dir.glob("*.wav"))
    if not clips:
        raise SystemExit(f"No wav clips in {args.clips_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = args.output_dir / f"{args.prefix}_raw_fixed_gap.wav"
    clean = args.output_dir / f"{args.prefix}_cleaned_trim_fade_norm.wav"
    raw_meta = make_reel(clips, raw, False, args.gap_ms, args.threshold, args.keep_ms, args.fade_in_ms, args.fade_out_ms, args.target_peak)
    clean_meta = make_reel(clips, clean, True, args.gap_ms, args.threshold, args.keep_ms, args.fade_in_ms, args.fade_out_ms, args.target_peak)
    print(json.dumps({"raw": raw_meta, "clean": clean_meta, "m4a": [str(to_m4a(raw)), str(to_m4a(clean))]}, indent=2))


if __name__ == "__main__":
    main()
