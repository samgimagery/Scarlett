# Scarlett Brain Timing + Service Bank

REQ-119 added timing and interaction-shape testing on top of REQ-116 correctness testing.
REQ-120 promotes the 50 AMS timing cases into Scarlett’s first fast-path service tile catalog.

Latest REQ-120 report: `reports/scarlett_brain_harness_20260506-005347.md` — **50/50 verified**, 0 failed, 0 partial.

REQ-123 speed/stability findings: `voice_speed_findings.md`. The key conclusion is that the best live voice path is not blocking on faster TTS; it is cached service-tile playback with Brain/RAG and live TTS running behind it.

## Files

- `timing_policy.md` — silence/receipt/lookup/prebuilt/generation timing rules.
- `interaction_case_schema.json` — schema for interaction timing cases.
- `interaction_cases_ams.jsonl` — first 50 AMS interaction cases.
- `service_tiles.py` — deterministic tile selector and metadata catalog.
- `reports/` — timing harness reports.

## Service tile model

Each common interaction can now expose a `voice` block from `/ask`:

- `tile_id` / `case_id` / `intent` — stable IDs for logging and future audio assets.
- `strategy` — `prebuilt_tile`, `receipt`, `clarify`, `hybrid_tile_then_generate`, `live_generate`, etc.
- `line` — the polished line to prerecord when one exists.
- `asset_id` — future audio file path, e.g. `ams/ams-int-011-price_n1.wav`.
- `asset_status` — currently `scripted`; audio recording pass comes next.
- `interruptible` — true for all v1 cases.
- `first_audio_ms` — projected first-audio target used by the voice shell/harness.
- `blocks_first_audio` — false for hybrid/live/handoff paths where retrieval can continue after the first line starts.

`GET /brain/service-tiles` returns the full catalog.

## Timing interpretation

The harness now distinguishes:

1. **First audio latency** — the time before Scarlett starts speaking. Service tiles should satisfy this.
2. **Full answer latency** — still measured, but hybrid paths can pass when the generated answer is non-blocking after the first tile.

This matches Sam’s product direction: polished common interactions first, live generation only where needed.

## Recording pass next

The first recording pass should prioritize:

1. greeting / identity
2. comment ça fonctionne
3. beginner path
4. trained practitioner path
5. prices / totals / financing
6. campus list / nearest campus
7. signup pre-check
8. objections: too expensive, time, recognition
9. repair: repeat, unclear, didn’t hear
10. safety: internal-source refusal
