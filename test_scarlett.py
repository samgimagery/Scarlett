#!/usr/bin/env python3
"""
Test fine-tuned Scarlett (Alice audiobook) voice model.
Generates samples from the merged model using mlx_audio.
"""

import os
import mlx.core as mx

MERGED_MODEL = os.path.expanduser("~/Media/voices/scarlett_finetuned/merged")
BASE_MODEL = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/"
    "snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
)
OUTPUT_DIR = os.path.expanduser("~/Media/voices/scarlett_finetuned_samples")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEST_TEXTS = [
    "I answer questions from the vault. What would you like to know?",
    "The most wonderful thing about this place is that nothing is quite what it seems.",
    "I've been thinking about you, and I wanted to let you know that I'm here for you.",
    "Hello! I'm Scarlett. It's so nice to meet you.",
    "Sometimes the best conversations happen when you least expect them.",
]

def main():
    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model

    print("=" * 60)
    print("Testing Scarlett (Alice audiobook) fine-tuned model")
    print("=" * 60)

    # Load the full model from base (includes speaker encoder, codec, etc.)
    # then overlay the merged LoRA-fused backbone weights
    print("\n[1] Loading base model...")
    model = load_model(BASE_MODEL, strict=False)

    print("\n[2] Loading merged weights...")
    merged_weights = mx.load(os.path.join(MERGED_MODEL, "model.safetensors"))
    model.load_weights(list(merged_weights.items()), strict=False)
    mx.eval(model.parameters())
    print(f"  Loaded {len(merged_weights)} weight tensors from merged model")

    for i, text in enumerate(TEST_TEXTS):
        print(f"\n[{i+1}/{len(TEST_TEXTS)}] Generating: \"{text[:60]}...\"")
        
        gen_dir = os.path.join(OUTPUT_DIR, f"gen_{i:02d}")
        os.makedirs(gen_dir, exist_ok=True)
        
        generate_audio(
            text=text,
            output_path=gen_dir,
            model=model,
            lang="en",
        )
        
        # Find the generated wav file
        wav_file = None
        for f in os.listdir(gen_dir):
            if f.endswith('.wav'):
                wav_file = os.path.join(gen_dir, f)
                break
        
        if wav_file:
            final_path = os.path.join(OUTPUT_DIR, f"scarlett_alice_{i:02d}.wav")
            os.rename(wav_file, final_path)
            os.rmdir(gen_dir)
            print(f"  Saved: {final_path}")
        else:
            print(f"  ERROR: No wav generated for sample {i}")

    print(f"\n✅ Done! {len(TEST_TEXTS)} samples saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()