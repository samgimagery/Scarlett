#!/usr/bin/env bash
set -euo pipefail
cd /Users/samg/AI/OpenClaw/dev/receptionist
TS=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$HOME/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_fr_lora_overnight_$TS"
DATASET="$HOME/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_pilot_15min_dataset/train_raw.jsonl"
BANK="$PWD/orpheus_bench/language_bank/scarlett_fr_ca_live_bank.json"
PY="$PWD/.voice-clone-env/bin/python"
mkdir -p "$RUN_DIR"
{
  echo "REQ-112 overnight FR clone run"
  echo "Started: $(date)"
  echo "Dataset: $DATASET"
  echo "Output: $RUN_DIR"
  echo "Bank: $BANK"
} | tee "$RUN_DIR/RUNNING.md"

"$PY" finetune_qwen3_tts_lora.py \
  --dataset-jsonl "$DATASET" \
  --output-dir "$RUN_DIR/train" \
  --max-steps 2200 \
  --learning-rate 5e-5 \
  --batch-size 2 \
  --grad-accum 8 \
  --warmup-steps 100 2>&1 | tee "$RUN_DIR/train.log"

"$PY" merge_qwen3_tts_lora.py \
  --adapter "$RUN_DIR/train/final_adapter" \
  --output-dir "$RUN_DIR/merged_out" 2>&1 | tee "$RUN_DIR/merge.log"

"$PY" generate_qwen3_french_lora_review.py \
  --merged-dir "$RUN_DIR/merged_out/merged" \
  --bank "$BANK" \
  --output-dir "$RUN_DIR/review_samples" \
  --limit 15 \
  --speed 0.9 2>&1 | tee "$RUN_DIR/review.log"

{
  echo "# REQ-112 Overnight FR Clone Complete"
  echo
  echo "Completed: $(date)"
  echo
  echo "- Dataset: \`$DATASET\`"
  echo "- Adapter: \`$RUN_DIR/train/final_adapter\`"
  echo "- Merged: \`$RUN_DIR/merged_out/merged\`"
  echo "- Review samples: \`$RUN_DIR/review_samples\`"
} > "$RUN_DIR/COMPLETE.md"
echo "$RUN_DIR" > "$HOME/Media/voices/french_sources/xUiKafk2gWM/latest_overnight_fr_clone_path.txt"
