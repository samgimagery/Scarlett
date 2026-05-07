#!/usr/bin/env python3
"""Merge a Qwen3-TTS LoRA adapter into the bf16 base model."""

import argparse
import os
import shutil
from pathlib import Path

BASE_MODEL = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
    "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    from mlx_tune import FastTTSModel

    adapter = Path(args.adapter).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    merged = output_dir / "merged"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Merging Qwen3-TTS LoRA")
    print("=" * 60)
    print(f"Adapter: {adapter}")
    print(f"Merged:  {merged}")

    model, tokenizer = FastTTSModel.from_pretrained(model_name=BASE_MODEL, max_seq_length=4096)
    model = FastTTSModel.get_peft_model(
        model,
        r=32,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model.load_adapter(str(adapter))
    model.save_pretrained_merged(str(merged), tokenizer)

    src_st = Path(BASE_MODEL) / "speech_tokenizer"
    dst_st = merged / "speech_tokenizer"
    if src_st.is_dir() and not dst_st.is_dir():
        shutil.copytree(src_st, dst_st)

    print(f"Merged model saved: {merged}")


if __name__ == "__main__":
    main()
