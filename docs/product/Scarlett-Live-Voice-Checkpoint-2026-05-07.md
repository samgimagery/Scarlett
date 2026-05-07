# Scarlett Live Voice Checkpoint — 2026-05-07

Scarlett live voice is now wired as a cached-first prototype for the AMS receptionist.

This checkpoint covers the path from scripted service tiles to approved `.wav` assets, active browser playback, real-device feedback, and the new contextual starter bank.

## Current state

- Live voice server: `com.scarlett.voice-web`
- Active runtime file: `live_conversation.py`
- Aligned legacy tap-to-talk file: `live_voice_web.py`
- Public entry point: `https://samgs-mac-studio.tail3e92a8.ts.net/`
- Cached asset root: `scarlett_core/voice/assets/`
- AMS asset namespace: `scarlett_core/voice/assets/ams/`
- First-audio manifest: `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json`
- Contextual starter manifest: `scarlett_core/voice/manifests/ams_contextual_starter_bank_v1.json`
- Contextual starter namespace: `scarlett_core/voice/assets/ams/starters/`

## What shipped

REQ-158 generated the first AMS service-tile audio batch.

- `28/28` first-audio `.wav` assets generated
- manifest-driven generation script added: `scarlett_core/voice/generate_manifest_audio.py`
- service tiles now report `recording_ready: true` when an asset exists

REQ-159 performed the listening/Whisper review pass.

- weak or overlong lines were regenerated only where needed
- final batch duration range: `1.63s–6.18s`
- average duration: `4.08s`
- longest approved line: `ams-int-048-human.wav`, about `6.18s`
- final asset validation: `28/28` current files present

REQ-160 wired playback into the live voice path.

- cached service-tile WAV is sent to the browser when `/ask` returns ready voice metadata
- cached-only answers skip generated TTS to prevent duplicate playback
- hybrid answers play cached first audio, then generated answer chunks
- WebSocket audio metadata includes service tile identity and asset IDs


REQ-161 started the contextual starter hardening pass after Sam’s real-device test.

- generic receipt filler was removed before fast service-tile answers
- RAG slow-path threshold tightened from `0.70s` to `0.45s`
- contextual starter selection added to `live_conversation.py`
- starter category is inferred from `/ask` voice metadata or local path classifier
- 120 contextual FR-CA starter WAVs generated: 12 intent groups × 10 variants
- starter duration range: `0.90s–7.12s`, average `2.52s`
- groups: price, financing, campus, signup, reserve_place, continuing_ed, course_content, human, repair, dates, identity, generic
- prototype barge-in disabled while Scarlett is speaking so browser/iPhone mic pickup does not cut her off
- Sam confirmed the improved live feel in testing: “WOW fucking amazing already ! WTF”

## Key files

- `live_conversation.py` — active browser voice runtime
- `live_voice_web.py` — older tap-to-talk runtime kept aligned
- `tts.py` — Qwen3/TTS helpers and voice generation support
- `scarlett_core/brain/timing/service_tiles.py` — service-tile metadata and asset readiness
- `scarlett_core/brain/timing/interaction_cases_ams.jsonl` — AMS timing/service cases
- `scarlett_core/voice/generate_manifest_audio.py` — manifest-driven batch generation
- `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json` — canonical recording manifest
- `scarlett_core/voice/manifests/ams_contextual_starter_bank_v1.json` — 120-line contextual starter bank
- `scarlett_core/voice/manifests/ams_contextual_starter_bank_v1.md` — human-readable starter bank
- `scarlett_core/voice/assets/ams/starters/` — contextual starter WAV assets
- `scarlett_core/voice/reviews/` — Whisper/listening review artifacts

## Verified cases

Smoke cases verified locally:

- `bonjour` → cached `ams/ams-int-001-greeting.wav`, no duplicate generated TTS
- `je veux réserver ma place` → cached `ams/ams-int-025-reserve_place.wav`, no duplicate generated TTS
- `combien coûte le niveau 1` → fast cached price audio, no generic filler first
- `quels campus avez-vous` → cached `ams/ams-int-019-campus_list.wav`, then generated longer answer chunks
- `je veux m’inscrire` → contextual signup starter available if answer preparation is slow
- `garde-moi une place` → cached reserve-place service tile, no fake reservation
- `peux-tu répéter` → repair starter/service tile path available

## Latest gates

Green as of this checkpoint:

- Python compile checks for touched runtime, voice, service-tile, and harness files
- path classifier harness: `500/500`
- held-out utterance eval: `250/250`
- router guard regressions: `8/8`
- repair polish regressions: `6/6`
- action polish regressions: `6/6`
- handoff polish regressions: `6/6`
- campus/location regressions: `8/8`
- greeting polish regressions: `5/5`
- realistic conversation batch: passed, `0` low-confidence rows
- trust regression: `15/15`
- asset validation: `28/28` current AMS first-audio WAV files present
- contextual starter generation: `120/120` WAV files generated
- contextual starter runtime load: `120 cached clips` confirmed after voice-web restart

## Known limitation

The core live feel is now validated by Sam, but the contextual starter bank still needs a proper listening/culling pass. The starter bank is generated and wired, not yet fully curated.

## Next step

Run the REQ-161 live starter pass against the public URL.

Recommended script:

- `Combien coûte le Niveau 1?`
- `Quels campus avez-vous?`
- `Je veux m’inscrire`
- `Garde-moi une place`
- `Peux-tu répéter?`
- `Je veux parler à quelqu’un`

Listen for:

- repeated starter lines
- wrong-context starters
- any generic bridge before a fast cached answer
- awkward prosody or overlong starter clips
- delay added by starter selection
- premature cut-off from mic/VAD pickup

Decision after that pass:

- if the starters feel varied and contextual: commit this as the locked v1 behaviour
- if specific starter lines feel weak: regenerate only those WAV assets first
- only then choose the next recording batch
