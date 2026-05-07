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
- Contextual starter WAV assets under `scarlett_core/voice/assets/ams/starters/`

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
- generic receipt filler no longer plays before fast service-tile answers
- contextual starters are used only for genuinely slow lookup/answer-bridge moments
- prototype barge-in is disabled while Scarlett is speaking so browser/iPhone mic pickup does not cut her off

Final asset validation:

- current AMS first-audio WAV assets: `28/28` present
- first-audio duration range: `1.63s–6.18s`
- first-audio average duration: `4.08s`
- contextual starter WAV assets: `120/120` generated
- contextual starter duration range: `0.90s–7.12s`
- contextual starter average duration: `2.52s`

### Contextual starter bank

REQ-161 adds a contextual starter bank so Scarlett does not overuse the same bridges once the first-audio path feels fast.

Coverage:

- 12 groups × 10 variants
- groups: price, financing, campus, signup, reserve_place, continuing_ed, course_content, human, repair, dates, identity, generic
- manifest: `scarlett_core/voice/manifests/ams_contextual_starter_bank_v1.json`
- readable manifest: `scarlett_core/voice/manifests/ams_contextual_starter_bank_v1.md`
- generated assets: `scarlett_core/voice/assets/ams/starters/`

Selection rule: service-tile audio wins when the answer is ready quickly. Contextual starters are not decorative filler; they are selected by intent only when retrieval or answer preparation needs a moment.

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
- asset validation: `28/28` current AMS first-audio WAV files present
- contextual starter generation: `120/120` WAV files generated

## Current next priority

Next work is **REQ-161 contextual starter hardening**.

Reason: Sam’s real-device pass confirmed the core live voice feel is now strong. The remaining risk is repetition or wrong-context starter audio during longer play sessions.

Recommended manual script:

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

Decision after the pass:

- if starters feel varied and contextual, lock v1
- if specific lines sound weak, regenerate only those WAV assets
- choose the next recording batch only after this layer is stable
