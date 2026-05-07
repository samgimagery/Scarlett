#!/usr/bin/env python3
"""Generate French AMS review samples from a merged Qwen3-TTS LoRA model."""

import argparse
import json
import os
import shutil
import time
from pathlib import Path

BASE_MODEL = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
    "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
)

DEFAULT_REF_AUDIO = "/Users/samg/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_pilot_15min_dataset/clips/fr_voice_0000.wav"
DEFAULT_REF_TEXT = "ses espérances soient flétries. Il est plus jeune que moi, sinon de fait du moins comme sentiment."


def load_merged_model(merged_dir: Path):
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx

    model = load_model(BASE_MODEL, strict=False)
    weights = mx.load(str(merged_dir / "model.safetensors"))
    model.load_weights(list(weights.items()), strict=False)
    mx.eval(model.parameters())
    return model


def find_wav(output_path: Path):
    for p in output_path.glob("*.wav"):
        return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged-dir", required=True)
    ap.add_argument("--bank", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--ref-audio", default=DEFAULT_REF_AUDIO)
    ap.add_argument("--ref-text", default=DEFAULT_REF_TEXT)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--speed", type=float, default=0.9)
    args = ap.parse_args()

    from mlx_audio.tts.generate import generate_audio

    merged_dir = Path(args.merged_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    bank = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    lines = bank.get("lines", [])[: args.limit]

    print(f"Loading merged model: {merged_dir}")
    model = load_merged_model(merged_dir)
    print(f"Generating {len(lines)} samples...")

    manifest = []
    for i, line in enumerate(lines, 1):
        sample_id = line["id"]
        text = line["text"]
        sample_dir = raw_dir / sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)
        start = time.time()
        print(f"[{i}/{len(lines)}] {sample_id}")
        generate_audio(
            text=text,
            output_path=str(sample_dir),
            model=model,
            lang_code="fr",
            speed=args.speed,
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            stt_model=None,
        )
        wav = find_wav(sample_dir)
        elapsed = time.time() - start
        if not wav:
            manifest.append({**line, "ok": False, "elapsed_sec": elapsed})
            continue
        final_wav = output_dir / f"{sample_id}.wav"
        shutil.copy2(wav, final_wav)
        manifest.append({**line, "ok": True, "elapsed_sec": elapsed, "wav": str(final_wav)})

    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "README.md").write_text(
        "# Qwen3-TTS French LoRA Pilot Review\n\n"
        f"Merged model: `{merged_dir}`\n\n"
        f"Reference audio: `{args.ref_audio}`\n\n"
        f"Bank: `{args.bank}`\n\n"
        f"Speed: `{args.speed}`\n\n"
        "Prototype/reference only until source rights are cleared.\n",
        encoding="utf-8",
    )
    print(f"Done: {output_dir}")


if __name__ == "__main__":
    main()
