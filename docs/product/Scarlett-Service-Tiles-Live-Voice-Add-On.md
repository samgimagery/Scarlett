# Scarlett Service Tiles — Live Voice Add-On

## Product thesis

Live voice is a premium Scarlett add-on built around a per-business, per-voice **service tile bank**.

The goal is not to make live generation speak every word. The goal is to make Scarlett feel immediate, polished, and interruptible while the Brain handles only the parts that need retrieval or synthesis.

## Service tiles

A service tile is a short, polished, scripted voice moment tied to a common interaction:

- greeting
- identity
- how-it-works
- pricing anchor
- campus/location anchor
- signup pre-check
- objection handling
- repair phrase
- handoff/escalation
- safety refusal

Each tile carries metadata:

- stable tile ID
- business/customer instance
- intent
- trigger phrase or classifier target
- voice strategy
- script line
- future audio asset path
- interruptible flag
- first-audio budget
- full-answer budget
- whether generation continues after the tile

## Why it works

The key split is **first audio** vs **full answer**.

If Scarlett can begin with the right tile in 300–700ms, the customer feels heard immediately. The full answer can arrive after retrieval/generation when needed.

This avoids the main weakness of pure voice AI: dead air.

## Commercial framing

Base Scarlett:

- knowledge ingestion
- vault/wiki
- deterministic fact layers
- chat/text receptionist
- testing and tuning loop

Live Voice Add-On:

- voice/persona selection
- service tile discovery
- tile script writing
- audio generation/recording
- interruption-safe playback
- live generation fallback
- ongoing tile refinement from real interactions

This is service design plus engineering, not just TTS.

## AMS v1 evidence

REQ-119 introduced 50 AMS timing/service cases.
Initial timing result: 21/50 verified; most failures were latency/service-shape issues.

REQ-120 added the v1 tile layer:

- `scarlett_core/brain/timing/service_tiles.py`
- `/ask` voice metadata
- `/brain/service-tiles`
- harness support for first-audio vs full-answer timing
- 50 scripted AMS service tiles

Final harness result:

- Report: `scarlett_core/brain/timing/reports/scarlett_brain_harness_20260506-005347.md`
- 50/50 verified
- 0 failed
- 0 partial

REQ-158 through REQ-160 moved the layer from metadata to live audio:

- `28/28` AMS first-audio WAV assets generated from `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json`
- listening/Whisper review completed and weak lines regenerated
- final asset duration range: `1.63s–6.18s`, average `4.08s`
- active browser voice path now plays cached service-tile WAVs before generated chunks
- cached-only answers skip generated TTS to prevent duplicate playback

## Open finding

The hard part is not canned audio. The hard part is deciding:

- when to play a tile
- when to interrupt it
- when to continue into generation
- when to stay deterministic
- when to escalate
- when to create a new tile from production behaviour

That is the product moat.

## Current implementation step

The audio asset lifecycle now exists in practice:

1. candidate
2. scripted
3. recorded/generated
4. reviewed with listening/Whisper artifacts
5. verified by asset validation and live smoke tests
6. production-ready for browser/iPhone review

Next implementation work is not more scripting. It is the real device pass: first-audio timing, duplicate playback checks, awkward take review, and interruption/barge-in behaviour. After that, either regenerate weak lines or harden timing and barge-in.
