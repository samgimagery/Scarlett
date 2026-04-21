#!/usr/bin/env python3
"""
Merge Scarlett (Alice audiobook) LoRA adapters into the bf16 base model.

This creates a standalone model that doesn't need separate adapter loading.
"""

import os
import shutil

BASE_MODEL = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
    "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
)
ADAPTER_PATH = os.path.expanduser("~/Media/voices/scarlett_finetuned/final_adapter")
OUTPUT_DIR = os.path.expanduser("~/Media/voices/scarlett_finetuned")

def main():
    from mlx_tune import FastTTSModel

    print("=" * 60)
    print("Merging Scarlett LoRA into bf16 base model")
    print("=" * 60)

    # Load base + LoRA
    print("\n[1] Loading base model...")
    model, tokenizer = FastTTSModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=4096,
    )

    print("\n[2] Adding LoRA adapters...")
    model = FastTTSModel.get_peft_model(
        model,
        r=32,
        lora_alpha=32,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    print("\n[3] Loading trained adapter weights...")
    model.load_adapter(ADAPTER_PATH)

    print("\n[4] Merging and saving...")
    merged_path = os.path.join(OUTPUT_DIR, "merged")
    model.save_pretrained_merged(merged_path, tokenizer)

    # Copy speech_tokenizer from base
    src_st = os.path.join(BASE_MODEL, "speech_tokenizer")
    dst_st = os.path.join(merged_path, "speech_tokenizer")
    if os.path.isdir(src_st) and not os.path.isdir(dst_st):
        shutil.copytree(src_st, dst_st)
        print(f"  Copied speech_tokenizer")

    print(f"\n✅ Merged model saved to {merged_path}")
    print(f"  Use this path for inference: {merged_path}")

if __name__ == "__main__":
    main()