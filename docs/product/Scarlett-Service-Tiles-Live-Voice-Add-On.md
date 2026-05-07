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

## Open finding

The hard part is not canned audio. The hard part is deciding:

- when to play a tile
- when to interrupt it
- when to continue into generation
- when to stay deterministic
- when to escalate
- when to create a new tile from production behaviour

That is the product moat.

## Next implementation step

Create the audio asset lifecycle:

1. candidate
2. scripted
3. recorded/generated
4. verified
5. production
6. refined

Then wire the live voice shell to play `voice.asset_id` immediately when `/ask` returns tile metadata.
