# Orpheus Bench — REQ-108

Purpose: prove whether Orpheus can become Scarlett's local live voice layer on Mac Studio.

Current bench order after Sam's Q4 decision:
1. Ollama/GGUF Q4 + Orpheus-FastAPI for SNAC decode/audio output. Approved default: `legraphista/Orpheus:latest` (`Q4_K_M`).
2. Q8 (`legraphista/Orpheus:3b-ft-q8`) only as quality reference or fallback for specific failures.
3. MLX Orpheus if streaming/RTF is competitive after the Q4 playback architecture is proven.
4. orpheus-cpp / llama.cpp Metal if it gives cleaner streaming control.

Do not pull large models automatically. First run is a readiness check; model install stays explicit.

Metrics to capture:
- TTFB
- total generation time
- audio duration
- RTF
- backend/model/quantization, with Q4 as the default English path
- cold vs warm
- quality notes
- seam/crossfade notes

Prompt set lives in `prompts.jsonl`.
Outputs go in `outputs/` and should not be committed blindly.


## Current decision — 2026-05-03

Sam approved Q4 quality for the English live-feel path: speed wins over the small clarity difference. Bench work should default to `legraphista/Orpheus:latest` and focus on perceived latency: cached filler first, Q4 generated answer chunks next, phrase/sentence playback queue, seam trimming, and sparse intentional emotion tags.
