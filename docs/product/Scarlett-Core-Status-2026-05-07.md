# Scarlett Core Status — 2026-05-07

Scarlett Core is now in a hardened live AMS state.

This checkpoint covers the production spine now running behind the AMS Telegram receptionist: deterministic routing, local facts, service-flow discipline, regression harnesses, and safe handoff behaviour.

## Live production pieces

- Telegram receptionist channel
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

## Verification gates

Latest live gates passed:

- path classifier harness: `500/500`
- held-out utterance eval: `250/250`
- realistic conversation batch: `56` turns, `0` low-confidence rows
- live Telegram/RAG trust regression: `15` turns
- Python compile checks for touched runtime and harness files
- RAG and Telegram LaunchAgents restarted cleanly

## Current next priority

Next work should be **multi-turn harness v2**.

Reason: single-turn facts and routing are now strong. The highest-risk failures are now long, messy real conversations where the caller changes topic, says “yes”, corrects Scarlett, gets frustrated, loops on price, or asks several follow-ups across multiple domains.

Planned v2 harness features:

- 10–20 turn scripted conversations
- assertions for no loops and no fake external actions
- context carryover checks
- same-user / changed-goal checks
- price objection → alternative path checks
- human handoff safety checks
- report showing weak turns automatically

After multi-turn v2, the next product layer is voice/service-tile recording.
