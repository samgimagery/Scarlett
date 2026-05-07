# Scarlett Core Status — 2026-05-07

Scarlett Core is now in a hardened live AMS state.

This checkpoint covers the production spine now running behind the AMS Telegram receptionist: deterministic routing, local facts, service-flow discipline, regression harnesses, and safe handoff behaviour.

## Live production pieces

- Telegram receptionist channel
- Cached-first browser voice prototype via `com.scarlett.voice-web`
- FastAPI RAG service on `:8000`
- Ollama model: `qwen3.6:35b`
- AMS vault: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/AMS`
- Deterministic local layers before RAG/LLM:
  - `location_layer.py`
  - `pricing_layer.py`
  - `continuing_ed_layer.py`
  - `handoff_layer.py`
  - current-student support layer
- Scarlett Brain tracing, review queue, classifier, service tiles, and test harnesses under `scarlett_core/brain/`
- Approved AMS first-audio WAV assets under `scarlett_core/voice/assets/ams/`

## Shipped in this hardening pass

### Router spine repair

The classifier and service route now correctly handle high-frequency AMS receptionist moments:

- generic price questions default to `price_n1`
- programme/price/content questions are no longer swallowed by campus routes
- human requests route to `human`
- signup link and “didn’t hear” phrases route high-confidence
- aromatherapy follow-ups preserve aromatherapy context instead of drifting to the main practitioner path

### Pricing expansion

Pricing is deterministic for the main commercial path:

- Niveau 1: `4 995 $`, from `104 $ / semaine`
- Niveau 2: `7 345 $`, from `111 $ / semaine`
- Niveau 3: `3 595 $`, from `97 $ / semaine`
- Niveau 1 + 2: `12 340 $`
- Niveau 1 + 2 + 3: `15 935 $`
- professional-program admin fee: `100 $`
- financing language: IFINANCE, bank, or partner credit line; no implied approval or hidden option

### Lower-cost / continuing education routing

Scarlett now handles budget hesitation without dead-ending the lead:

- “c’est trop cher” gives payment anchors and lighter options
- “je veux juste essayer” routes to low-commitment courses
- “formation courte”, “atelier”, “cours court” route to à-la-carte / continuing-ed options
- lower-cost flows preserve specific aromatherapy routing

Representative low-entry examples:

- Aromathérapie : les bases — `99 $`
- Massage aux balles de sel himalayen — `99 $ · 8 h`
- Massage aux coquillages chauds — `119 $`
- Massage neurosensoriel — `149 $ · 7 h`
- Aromathérapie clinique et scientifique 1 — `199 $ · 32 h`
- Massage bébé/enfant — `205 $ · 15 h`

### Handoff family

`handoff_layer.py` gives official AMS contact paths without pretending Scarlett performed an external action.

Covered intents:

- speak to a person / human / adviser
- callback / appointment / phone call
- send information by email
- campus contact
- Julie or named-person handoff

Official anchors:

- `1 800 475-1964`
- `https://www.academiedemassage.com/contact/`

Forbidden behaviour:

- no “I booked it”
- no “email sent”
- no fake live transfer
- no false claim that a callback is confirmed


### Multi-turn and polish expansion

The hardening pass now includes a stateful multi-turn torture suite and dedicated polish regression families.

Covered areas:

- multi-turn context carryover and no-loop checks
- repair language: did-not-hear, repeat, unclear
- signup/action safety: link, direct signup, reserve-place
- handoff safety: human, Julie, callback, send-info, campus contact
- greeting/capability polish
- campus/location richness

Scarlett preserves the same safety line throughout: she can guide, prepare, and provide official paths, but she must not pretend to transfer, book, email, submit, confirm, or reserve anything externally.

### First-audio live voice checkpoint

Scarlett now has a cached-first live voice prototype for AMS service tiles.

Shipped pieces:

- `28/28` approved AMS `.wav` first-audio assets
- manifest: `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json`
- generator: `scarlett_core/voice/generate_manifest_audio.py`
- review artifacts under `scarlett_core/voice/reviews/`
- live playback wiring in `live_conversation.py` and `live_voice_web.py`
- service-tile asset readiness detection in `scarlett_core/brain/timing/service_tiles.py`

Runtime behaviour:

- cached tile audio is sent first when `/ask` returns ready voice metadata
- cached-only answers skip generated TTS to avoid duplicate playback
- hybrid answers play cached first audio, then generated answer chunks

Final asset validation:

- current AMS WAV assets: `28/28` present
- duration range: `1.63s–6.18s`
- average duration: `4.08s`

## Verification gates

Latest live gates passed:

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
- live Telegram/RAG trust regression: `15` turns
- asset validation: `28/28` current AMS WAV files present

## Current next priority

Next work should be the **real browser/iPhone voice pass**.

Reason: code and harness gates are now green. The remaining risk is perceived product quality in the actual mic/browser loop: first-audio timing, duplicate playback, awkward takes, and interruption/barge-in behaviour.

Recommended manual script:

- `Bonjour`
- `Combien coûte le Niveau 1?`
- `Quels campus avez-vous?`
- `Je veux m’inscrire`
- `Garde-moi une place`
- `Peux-tu répéter?`
- interrupt once mid-answer if the UI allows it

Decision after the pass:

- if it sounds acceptable, harden timing and barge-in
- if specific lines sound weak, regenerate only those WAV assets before further code work
