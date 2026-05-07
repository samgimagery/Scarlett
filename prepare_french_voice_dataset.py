#!/usr/bin/env python3
"""
Prepare a French voice dataset for Qwen3-TTS LoRA fine-tuning.

Prototype-only: source rights must be cleared before commercial use.

Input: long 24k mono WAV slices.
Output: fixed-length 3-12s WAV clips + faster-whisper transcripts + train_raw.jsonl.
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

TARGET_SR = 24000
LENGTH_PATTERN = [8, 10, 12, 9, 11, 8, 10, 12, 9, 10]


def run(cmd):
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float:
    p = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)
    ], capture_output=True, text=True, check=True)
    return float(json.loads(p.stdout)["format"]["duration"])


def segment_sources(sources, clips_dir: Path, max_minutes: float | None):
    clips_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    used = 0.0
    idx = 0
    for source in sources:
        source = Path(source).expanduser()
        dur = probe_duration(source)
        t = 0.0
        while t + 4.0 <= dur:
            if max_minutes and used >= max_minutes * 60:
                return clips
            clip_len = LENGTH_PATTERN[idx % len(LENGTH_PATTERN)]
            remaining_source = dur - t
            remaining_budget = (max_minutes * 60 - used) if max_minutes else clip_len
            actual_len = min(clip_len, remaining_source, remaining_budget)
            if actual_len < 4.0:
                break
            out = clips_dir / f"fr_voice_{idx:04d}.wav"
            run([
                "ffmpeg", "-y", "-v", "quiet",
                "-ss", f"{t:.3f}", "-t", f"{actual_len:.3f}",
                "-i", str(source),
                "-ar", str(TARGET_SR), "-ac", "1",
                "-af", "loudnorm=I=-20:LRA=11:TP=-1.5",
                str(out),
            ])
            clips.append({
                "path": str(out),
                "source": str(source),
                "source_start": t,
                "duration": actual_len,
                "index": idx,
            })
            idx += 1
            t += actual_len
            used += actual_len
    return clips


def transcribe(clips, model_size: str):
    from faster_whisper import WhisperModel
    whisper = WhisperModel(model_size, device="cpu", compute_type="int8")
    transcripts = []
    for i, clip in enumerate(clips):
        segments, info = whisper.transcribe(clip["path"], language="fr", beam_size=5, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        # Remove common subtitle/video hallucination if it appears.
        bad = ["sous-titres réalisés", "amara.org", "merci d'avoir regardé"]
        if not text or any(b in text.lower() for b in bad):
            try:
                os.remove(clip["path"])
            except OSError:
                pass
            continue
        item = {**clip, "text": text}
        transcripts.append(item)
        if i < 5 or (i + 1) % 25 == 0 or i == len(clips) - 1:
            print(f"[{i+1}/{len(clips)}] {Path(clip['path']).name}: {text[:100]}")
    return transcripts


def write_outputs(transcripts, out_dir: Path):
    jsonl = out_dir / "train_raw.jsonl"
    manifest = out_dir / "manifest.json"
    with jsonl.open("w", encoding="utf-8") as f:
        for t in transcripts:
            f.write(json.dumps({
                "audio_path": t["path"],
                "text": t["text"],
                "speaker": "french_reference_voice",
            }, ensure_ascii=False) + "\n")
    manifest.write_text(json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(t["duration"] for t in transcripts)
    print(f"\nDataset ready: {out_dir}")
    print(f"Clips: {len(transcripts)}")
    print(f"Duration: {total:.1f}s / {total/60:.1f} min")
    print(f"JSONL: {jsonl}")
    return jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-minutes", type=float, default=15.0)
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    source_dir = Path(args.source_dir).expanduser()
    out_dir = Path(args.output_dir).expanduser()
    clips_dir = out_dir / "clips"

    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(source_dir.glob("*.wav"))
    if not sources:
        raise SystemExit(f"No WAV files found in {source_dir}")

    print(f"Sources: {len(sources)}")
    print(f"Output: {out_dir}")
    print(f"Budget: {args.max_minutes} min")

    clips = segment_sources(sources, clips_dir, args.max_minutes)
    print(f"Segmented clips: {len(clips)}")
    transcripts = transcribe(clips, args.whisper_model)
    write_outputs(transcripts, out_dir)


if __name__ == "__main__":
    main()
