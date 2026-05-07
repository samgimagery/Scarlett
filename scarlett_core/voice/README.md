# Scarlett Core Voice Layer

Canonical internal voice architecture for Scarlett Core.

## Locked direction — FR-CA live voice

The French Canadian Scarlett voice direction is now:

- Qwen3 French LoRA voice as the preferred FR-CA prototype direction
- `0.65` speed for composed answer chunks and premium delivery
- `0.75` speed for quick bridges, receipts, and fast prefiller clips
- cached-first live flow: play a tasteful cached line immediately while retrieval/planning/generation runs
- short dynamic answer chunks generated behind the first audible response
- intentional silence and calm pacing as a product virtue, not a defect

The target feeling is calm, deliberate, premium, kind, and competent. Latency should feel like care: Scarlett responds immediately, then answers with composed confidence once she has the right information.

## Contextual starter bank — REQ-161

After the first successful real-device cached-first test, Scarlett now has a contextual starter bank for AMS. This is separate from generic prefillers. The goal is to avoid hearing the same bridge lines repeatedly once first-audio latency is good.

Canonical files:

- `manifests/ams_contextual_starter_bank_v1.json` — 120 FR-CA starter lines
- `manifests/ams_contextual_starter_bank_v1.md` — human-readable starter bank
- `manifests/ams_contextual_starter_bank_v1_generation_report.json` — generation report
- `assets/ams/starters/` — generated contextual starter WAVs

Current coverage:

- `120/120` WAV assets generated
- 12 groups × 10 variants: price, financing, campus, signup, reserve_place, continuing_ed, course_content, human, repair, dates, identity, generic
- duration range: `0.90s–7.12s`
- average duration: `2.52s`
- runtime: active `live_conversation.py` loads starters and selects by `/ask` voice intent or local path classifier

Runtime rule: cached service-tile audio wins. Do not put a generic or contextual starter in front of an answer that is already ready quickly. Starters are for genuinely slow lookup/answer-bridge moments, and they must match the service context.

Prototype barge-in rule: barge-in is disabled while Scarlett is speaking, because browser/iPhone mic pickup was cutting off good audio. Re-enable only after echo handling is reliable.

Next validation: live listening/culling pass. Remove or regenerate starters that sound repetitive, wrong-context, awkward, too long, or slower than silence.

## Mega prefiller bank

Scarlett Core should maintain a large reusable bank of cached prefillers for any service situation. This is a core latency shield, not decoration.

Prefillers buy time while Scarlett performs RAG/search, service-flow classification, deterministic fact checks, or LLM generation. They must sound natural and must never imply a capability or action that is not actually happening.

Required coverage categories:

- greeting and receipt
- thinking / looking / checking
- clarification
- empathy and reassurance
- booking / registration
- pricing and financing
- location and campus
- dates / availability
- current student support
- trained practitioner orientation
- uncertainty and missing information
- transfer / human handoff
- error recovery
- graceful deflection
- confirmation and next step
- interruption / cancellation recovery

Each line should support variants by:

- duration: ~1s, ~2s, ~4s, ~6s
- tone: warm, professional, intimate, cheerful, apologetic, concise, premium/composed
- language: FR-CA first for the current prototype, EN later where needed
- speed: `0.75` quick bridge, `0.65` composed/premium

## Runtime rule

The voice runtime should choose the shortest honest cached line that matches the current service state, then queue dynamic answer chunks behind it.

Do not use filler randomly. A prefiller is selected because the system knows what kind of work is happening or what emotional/service state the customer is in.

## Payment objection voice rule

When payment options have already been covered, Scarlett should not keep sounding like more options may exist. The voice should become settled, patient, and honest:

- acknowledge the cost is significant
- avoid re-listing the same options unless asked
- avoid salesy optimism or fake extra doors
- ask whether the customer wants one known option detailed or needs something else

Preferred delivery: slow, calm, empathetic, no bright sales cadence.

Canonical line after options are already covered:

> Je comprends. C’est beaucoup d’argent, et je ne veux pas vous faire tourner en rond. Les options de paiement connues ont déjà été couvertes. Voulez-vous que je détaille une option précise, ou est-ce que je peux vous aider avec autre chose ?

## Production rights rule

Prototype/source voice work is acceptable for internal experimentation only. Any serious commercial deployment must use clean, licensed, or consented voice actor data trained into the same architecture.

## AMS first-audio batch — 2026-05-07

The first AMS cached-first voice batch is now generated, reviewed, and wired into the browser voice prototype.

Canonical files:

- `manifests/ams_first_recording_batch_v1.json` — source manifest for approved first-audio lines
- `manifests/ams_first_recording_batch_v1.md` — human-readable manifest
- `manifests/ams_first_recording_batch_v1_generation_report.json` — generation report
- `manifests/ams_first_recording_batch_v1_asset_validation.json` — asset validation report
- `generate_manifest_audio.py` — manifest-driven audio generation helper
- `reviews/` — Whisper/listening review artifacts and regeneration records
- `assets/ams/` — current approved AMS WAV assets, force-added despite the repo-wide `*.wav` ignore rule

Current validation:

- approved current assets: `28/28`
- duration range: `1.63s–6.18s`
- average duration: `4.08s`
- live runtime: `live_conversation.py` resolves and sends cached service-tile WAVs before generated chunks
- duplicate prevention: cached-only answers skip generated TTS

Manual browser/iPhone validation succeeded for the core cached-first feeling. Next validation is REQ-161: listen through live contextual starter behaviour, then cull or regenerate weak starter clips before the next recording batch.
