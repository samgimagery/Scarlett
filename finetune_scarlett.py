#!/usr/bin/env python3
"""
Fine-tune Qwen3-TTS on Scarlett Johansson's voice using Alice audiobook clips.

97 clips, ~13 minutes of diverse reading. LoRA r=32 on bf16 base.
Much better generalization than the 5-clip HER dataset (50s → 13min).
"""

import os
import json
import soundfile as sf

DATASET_DIR = os.path.expanduser("~/Media/voices/scarlett_audiobook")
OUTPUT_DIR = os.path.expanduser("~/Media/voices/scarlett_finetuned")
DATASET_JSONL = os.path.join(DATASET_DIR, "train_raw.jsonl")

def main():
    from mlx_tune import FastTTSModel, TTSSFTTrainer, TTSSFTConfig, TTSDataCollator

    print("=" * 70)
    print("Scarlett Johansson Voice Fine-Tuning (Alice Audiobook)")
    print("=" * 70)

    bf16_path = os.path.expanduser(
        "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
        "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
    )

    # 1. Load base model
    print("\n[Step 1] Loading Qwen3-TTS 1.7B bf16 base model...")
    model, tokenizer = FastTTSModel.from_pretrained(
        model_name=bf16_path,
        max_seq_length=4096,
    )
    print("  Model loaded.")

    # 2. LoRA — same config as HER training
    print("\n[Step 2] Adding LoRA adapters (r=32, alpha=32)...")
    model = FastTTSModel.get_peft_model(
        model,
        r=32,
        lora_alpha=32,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    print("  LoRA adapters attached.")

    # 3. Load dataset
    print("\n[Step 3] Loading dataset...")
    entries = []
    with open(DATASET_JSONL) as f:
        for line in f:
            entries.append(json.loads(line.strip()))

    print(f"  Loaded {len(entries)} training samples")

    # Check audio_path key (Whisper output uses "audio_path", training needs "audio")
    formatted_data = []
    for entry in entries:
        audio_path = entry.get("audio_path") or entry.get("audio", "")
        if not os.path.exists(audio_path):
            continue
        audio_array, sr = sf.read(audio_path)
        formatted_data.append({
            "audio": {"array": audio_array, "sampling_rate": sr},
            "text": entry["text"],
        })

    print(f"  Prepared {len(formatted_data)} samples for training")
    total_duration = sum(len(d["audio"]["array"]) / d["audio"]["sampling_rate"] for d in formatted_data)
    print(f"  Total training audio: {total_duration:.1f}s ({total_duration/60:.1f} min)")

    # 4. Data collator
    print("\n[Step 4] Creating data collator...")
    collator = TTSDataCollator(
        model=model,
        tokenizer=tokenizer,
        text_column="text",
        audio_column="audio",
    )

    # 5. Fine-tune — more steps for larger dataset, lower LR
    # 13 min of data can handle 2000+ steps without overfitting
    print("\n[Step 5] Starting fine-tuning...")
    print("  Larger dataset — more steps, lower learning rate")

    trainer = TTSSFTTrainer(
        model=model,
        tokenizer=tokenizer,
        data_collator=collator,
        train_dataset=formatted_data,
        args=TTSSFTConfig(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=8,
            learning_rate=5e-5,        # Lower than HER (1e-4) — more data needs gentler updates
            max_steps=2000,            # More steps for 13 min vs 800 for 50s
            warmup_steps=100,         # More warmup for stability
            logging_steps=50,
            weight_decay=0.005,
            train_on_completions=True,
        ),
    )

    result = trainer.train()
    print(f"\nFinal loss: {result.metrics['train_loss']:.4f}")

    # 6. Save adapters
    print("\n[Step 6] Saving LoRA adapters...")
    adapter_path = os.path.join(OUTPUT_DIR, "final_adapter")
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"  Adapters saved to {adapter_path}")

    print("\n" + "=" * 70)
    print("Fine-tuning complete!")
    print("=" * 70)
    print(f"  Output: {adapter_path}")
    print(f"  Next: python merge_her.py (update FINETUNED_MODEL path)")


if __name__ == "__main__":
    main()