# Scarlett Live Voice Checkpoint — 2026-05-07

Scarlett live voice is now wired as a cached-first prototype for the AMS receptionist.

This checkpoint covers the path from scripted service tiles to approved `.wav` assets and active browser playback.

## Current state

- Live voice server: `com.scarlett.voice-web`
- Active runtime file: `live_conversation.py`
- Aligned legacy tap-to-talk file: `live_voice_web.py`
- Public entry point: `https://samgs-mac-studio.tail3e92a8.ts.net/`
- Cached asset root: `scarlett_core/voice/assets/`
- AMS asset namespace: `scarlett_core/voice/assets/ams/`
- Manifest: `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json`

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

## Key files

- `live_conversation.py` — active browser voice runtime
- `live_voice_web.py` — older tap-to-talk runtime kept aligned
- `tts.py` — Qwen3/TTS helpers and voice generation support
- `scarlett_core/brain/timing/service_tiles.py` — service-tile metadata and asset readiness
- `scarlett_core/brain/timing/interaction_cases_ams.jsonl` — AMS timing/service cases
- `scarlett_core/voice/generate_manifest_audio.py` — manifest-driven batch generation
- `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json` — canonical recording manifest
- `scarlett_core/voice/reviews/` — Whisper/listening review artifacts

## Verified cases

Smoke cases verified locally:

- `bonjour` → cached `ams/ams-int-001-greeting.wav`, no duplicate generated TTS
- `je veux réserver ma place` → cached `ams/ams-int-025-reserve_place.wav`, no duplicate generated TTS
- `combien coûte le niveau 1` → cached `ams/ams-int-011-price_n1.wav`, no duplicate generated TTS
- `quels campus avez-vous` → cached `ams/ams-int-019-campus_list.wav`, then generated longer answer chunks

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
- asset validation: `28/28` current AMS WAV files present

## Known limitation

The final missing gate is not a unit test. It is a real browser/iPhone voice pass to judge perceived first-audio timing, duplicate playback, awkward takes, and interruption/barge-in behaviour.

## Next step

Run the iPhone/browser pass against the public URL.

Recommended script:

- `Bonjour`
- `Combien coûte le Niveau 1?`
- `Quels campus avez-vous?`
- `Je veux m’inscrire`
- `Garde-moi une place`
- `Peux-tu répéter?`
- interrupt once mid-answer if the UI allows it

Decision after that pass:

- if the audio feels good: harden timing and barge-in
- if specific lines feel weak: regenerate only those WAV assets first
