#!/usr/bin/env python3
"""Generic Qwen3-TTS LoRA fine-tuner for local voice experiments."""

import argparse
import json
import os
from pathlib import Path

import soundfile as sf

BASE_MODEL = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
    "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
)


def load_dataset(jsonl_path: Path):
    rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    data = []
    missing = 0
    for row in rows:
        audio_path = row.get("audio_path") or row.get("audio")
        if not audio_path or not os.path.exists(audio_path):
            missing += 1
            continue
        audio_array, sr = sf.read(audio_path)
        text = (row.get("text") or "").strip()
        if not text:
            continue
        data.append({
            "audio": {"array": audio_array, "sampling_rate": sr},
            "text": text,
        })
    total = sum(len(d["audio"]["array"]) / d["audio"]["sampling_rate"] for d in data)
    print(f"Loaded {len(data)} samples ({total/60:.1f} min), missing={missing}")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-jsonl", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-steps", type=int, default=1000)
    ap.add_argument("--learning-rate", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--warmup-steps", type=int, default=75)
    args = ap.parse_args()

    from mlx_tune import FastTTSModel, TTSSFTTrainer, TTSSFTConfig, TTSDataCollator

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Qwen3-TTS LoRA fine-tune")
    print("=" * 70)
    print(f"Dataset: {args.dataset_jsonl}")
    print(f"Output:  {output_dir}")
    print(f"Steps:   {args.max_steps}")

    print("\n[1] Loading bf16 base model...")
    model, tokenizer = FastTTSModel.from_pretrained(model_name=BASE_MODEL, max_seq_length=4096)

    print("\n[2] Adding LoRA adapters r=32 alpha=32...")
    model = FastTTSModel.get_peft_model(
        model,
        r=32,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    print("\n[3] Loading dataset...")
    train_data = load_dataset(Path(args.dataset_jsonl).expanduser())
    if not train_data:
        raise SystemExit("No training data loaded")

    print("\n[4] Creating collator...")
    collator = TTSDataCollator(model=model, tokenizer=tokenizer, text_column="text", audio_column="audio")

    print("\n[5] Training...")
    trainer = TTSSFTTrainer(
        model=model,
        tokenizer=tokenizer,
        data_collator=collator,
        train_dataset=train_data,
        args=TTSSFTConfig(
            output_dir=str(output_dir),
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.learning_rate,
            max_steps=args.max_steps,
            warmup_steps=args.warmup_steps,
            logging_steps=25,
            weight_decay=0.005,
            train_on_completions=True,
        ),
    )
    result = trainer.train()
    print(f"Final loss: {result.metrics.get('train_loss')}")

    adapter_path = output_dir / "final_adapter"
    print("\n[6] Saving adapter...")
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"Adapter saved: {adapter_path}")


if __name__ == "__main__":
    main()
