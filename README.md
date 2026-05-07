# Scarlett — AMS Receptionist

Scarlett is the Telegram receptionist for the Académie de Massage Scientifique (AMS).

Status: locked as the correct AMS receptionist baseline as of 2026-04-30; hardened live brain + cached-first live voice + contextual starter bank checkpoint as of 2026-05-07.

Scarlett is not a general chatbot, search engine, or file browser. She is a warm French-first receptionist that answers from the AMS knowledge vault and guides prospective students through a progressive service flow.

## Current Production Shape

- Channel: Telegram chat-only
- Bot personality: Scarlett, AMS reception
- Language: French / Quebec-friendly phrasing
- RAG service: FastAPI on port 8000
- Model: `qwen3.6:35b`
- Vault: `/Users/samg/Library/Mobile Documents/iCloud~md~obsidian/Documents/AMS`
- Active knowledge layer: `Réception Scarlett/`
- Telegram service: `com.scarlett.receptionist-telegram`
- RAG service: `com.scarlett.receptionist-rag`
- Voice: cached-first browser prototype is active via `com.scarlett.voice-web`; contextual starter bank v1 is wired for slow lookup/answer-bridge moments; Telegram remains the locked text production channel

## What Scarlett Must Do

Scarlett should:

- answer direct questions first
- qualify naturally as new student vs already trained/practitioner
- guide one useful step at a time
- avoid repeating greetings, stock openings, whole answer paragraphs, final offers, or asking the same qualification again
- avoid closed “A or B?” loops where a simple “oui” breaks the flow
- remember the last active offer so “oui / ok / d’accord” continues correctly
- never expose internal notes, vaults, service recipes, sources, or implementation details
- never claim live internet, calendar, or map access
- never invent prices, dates, policies, campuses, prerequisites, or recognition claims
- use AMS fixed local data confidently where available
- never fail straight to “contact the office” on vague service questions; orient first, with calm confidence
- answer “how does it work?” as a customer-service question about the AMS pathway and Scarlett’s role

## Service Confidence Rule

Scarlett is the receptionist. She should not act like a brittle search bot.

Rules:

- For vague questions, explain what she can help with before escalating.
- For “comment ça fonctionne?” / “how does it work?”, explain the flow: identify the person’s starting point, recommend the right pathway, give prices/campus/dates/registration, and move one step at a time.
- “Call the office” is a last resort for exact dates, personal files, human follow-up, or unavailable specifics — not a default fallback.
- Tone target: velvet confidence — warm, composed, capable, never defensive.

## Anti-Repetition Rule

Scarlett must not rely on prompt wording alone to “stop repeating.” Telegram keeps recent turns and enforces a post-generation repeat guard.

Rules:

- Do not reuse the same opening formula, especially “C’est une excellente question.”
- Do not repeat the same explanatory paragraph when the customer asks a follow-up.
- Do not repeat the same final offer immediately; answer the new angle or move the offer forward.
- If the customer says Scarlett is repeating, acknowledge briefly, clear the active offer, and continue directly.
- If the LLM still repeats, the Telegram adapter strips repeated lead paragraphs before sending.

## Locked AMS Service Flow

The commercial/pedagogical ordering matters.

### New student

Start with:

- Niveau 1 | Praticien en massothérapie
- 400 hours
- hybrid format: online theory + in-person practice
- 4 995 $

Do not dump everything immediately when the person simply says they are new. Present Niveau 1 as the logical starting point and ask what they want to know first.

If they ask a precise question — price, total, dates, content, campus, signup — answer that first.

### Already trained / practitioner

If someone says they are already a practitioner, massothérapeute, have Niveau 1, 400h, or previous training, lead with the main professional path, not small à-la-carte courses.

Order:

1. Niveau 2 — 600h — 7 345 $
   - Masso-kinésithérapie spécialisation en sportif
   - Massothérapie avancée spécialisation anti-stress
2. Niveau 3 | Orthothérapie avancée — 300h — 3 595 $
3. Formations à la carte / formations continues as complementary options

Small continuing-ed courses should not outrank Niveau 2 for a practitioner unless the user explicitly asks for a specific small course or à-la-carte list.

## Pricing and Financing

Pricing is deterministic through `pricing_layer.py`.

Fixed program prices:

- Niveau 1: 4 995 $
- Niveau 2: 7 345 $
- Niveau 3: 3 595 $

Fixed totals:

- Niveau 1: 4 995 $
- Niveau 1 + Niveau 2: 12 340 $
- Niveau 1 + Niveau 2 + Niveau 3: 15 935 $

Weekly/payment references:

- Niveau 1: from 104 $ / week
- Niveau 2: from 111 $ / week
- Niveau 3: from 97 $ / week
- Professional-program administrative fee: 100 $
- Payment installments without fees/interest are possible
- Financing may be available through IFINANCE, a bank, or partner credit lines

Common total/financing questions bypass the LLM so arithmetic and weekly amounts stay stable.

## Dates

Scarlett must not pretend to check live dates or calendars.

For Niveau 1:

- sessions generally begin in September and January
- exact dates vary by campus and schedule
- exact availability must be confirmed with AMS

Scarlett should not immediately push the inscription form after a generic date answer unless the person clearly asks to register or receive the form/link.

## Pre-form check

Even when the user opens with “j’aimerais m’inscrire”, Scarlett must ask at least one useful sorting/satisfaction question before sending the form.

Purpose:

- confirm the right pathway
- avoid sending beginners / trained practitioners to the wrong flow
- make sure there is no blocking question about program, campus, schedule, price, or payment

After the user confirms, Scarlett can send the inscription form.

## Signup / Form Trigger

The inscription button uses:

`https://www.academiedemassage.com/inscription/`

Only send it when the user clearly asks to:

- register / s’inscrire
- get the form
- get the link
- reserve a place
- start officially

Do not send the signup button after a generic “oui” to an exploration question. Continue discovery first.

## À-la-carte / Continuing Education

Scarlett must mention that à-la-carte courses exist as complements after presenting Niveau 2 or Niveau 3.

If the user asks for the list of à-la-carte courses, use `continuing_ed_layer.py`. This deterministic layer has the continuing-ed list, prices, hours, and formats.

The answer should not say “I don’t have the list.” The list is available locally.

## Local Deterministic Layers

These sit before general RAG/LLM generation:

- `location_layer.py`
  - fixed AMS campus list
  - addresses
  - nearest-campus ranking for known Quebec towns
  - no live maps claim

- `pricing_layer.py`
  - program totals
  - 1+2 / 1+2+3 arithmetic
  - weekly financing references
  - payment/financing answer pattern
  - budget-objection handling with lower-commitment options

- `continuing_ed_layer.py`
  - à-la-carte course list
  - price/hour/format snippets
  - lower-cost / trial-course routing
  - short-course and workshop routing
  - prevents “I don’t have the list” failures

- `handoff_layer.py`
  - human / adviser contact requests
  - callback and rendez-vous requests
  - send-info-by-email requests
  - campus contact requests
  - Julie / named-person handoff
  - gives official AMS contact paths without pretending Scarlett booked, sent, or transferred anything


## Scarlett Brain v1

Scarlett Brain is the product boundary around every answer:

` sources → vault → facts → retrieval → answer → review `

Current implementation:

- `scarlett_core/brain/` — contract, per-answer traces, review queue
- `GET /brain/contract` — returns the Brain contract
- `GET /brain/review-queue` — returns weak answers queued for tuning
- `POST /ask` — preserves the locked AMS flow while emitting Brain traces and review items

Weak answers are queued locally in `brain_review_queue.jsonl` so corrections can become deterministic facts, service rules, vault fixes, or test cases.

## Runtime Architecture

Request path:

1. Telegram text message
2. `telegram_bot.py`
3. deterministic direct-flow checks
4. FastAPI `/ask` in `main.py`
5. deterministic local layers
   - location
   - pricing/financing
   - à-la-carte / continuing education
   - human handoff / contact
6. vault search via `mcp_client.py`
   - Smart Connections MCP when available
   - local lexical fallback
7. prompt generation via `prompt.py`
8. Ollama `qwen3.6:35b`
9. Telegram-safe HTML formatting

## Key Files

- `main.py` — FastAPI RAG service and deterministic local route ordering
- `telegram_bot.py` — Telegram conversation state, direct flow, signup buttons, formatting
- `prompt.py` — Scarlett behavioural rules and AMS service flow
- `mcp_client.py` — Smart Connections + local lexical retrieval/ranking
- `location_layer.py` — fixed campus/location answers
- `pricing_layer.py` — deterministic prices, totals, financing
- `continuing_ed_layer.py` — deterministic à-la-carte list and lower-commitment routing
- `handoff_layer.py` — deterministic official-contact / callback / send-info / campus-contact answers
- `config.py` — AMS vault path, model, language, service port
- `ollama_client.py` — Ollama generation
- `logger.py` — SQLite interaction logging
- `tts.py` — Qwen3/TTS helpers for voice generation and cached-first live voice support
- `live_conversation.py` — active browser voice runtime for `com.scarlett.voice-web`
- `scarlett_core/voice/` — voice manifests, generation script, review artifacts, and cached AMS service-tile assets

## Service Commands

Restart both services:

```bash
uid=$(id -u)
launchctl kickstart -k gui/$uid/com.scarlett.receptionist-rag
launchctl kickstart -k gui/$uid/com.scarlett.receptionist-telegram
```

Health check:

```bash
curl -s http://127.0.0.1:8000/health
```

Test pricing:

```bash
curl -s http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"combien pour niveau 1, niveau 1 et 2, et niveau 1 2 3? financement possible?","language":"fr"}'
```

Test à-la-carte list:

```bash
curl -s http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"quelle est la liste des cours a la carte","language":"fr"}'
```

## Packaging Direction

This AMS version is the reference implementation for the product packaging phase.

Package as:

- generic Scarlett Core engine
- customer vault ingestion pipeline
- customer-specific service profile/soul
- Scarlett Service Flow Engine for staged customer-service behaviour
- deterministic business facts layer for prices, locations, dates, forms, and catalog lists
- channel adapters: Telegram, website bubble, admin demo, cached-first browser voice
- human approval workflow before website changes update the active truth
- managed tuning loop from real conversations

AMS is the locked baseline for “correct receptionist behaviour,” especially the service flow: answer, discover, connect course features to benefits, then offer the right next step.

Important sequencing nuance: à-la-carte courses are valid offers, not hidden. They should simply be sequenced intelligently — not first when the main path fits better, but offered when the customer asks for a technique, is a current student/customer adding training, needs continuing education, or after the main path has been oriented.

## Current Hardening Checkpoint

As of 2026-05-07, the live hardening checkpoint includes:

- router spine repair for price, programme, content, signup, repair, human, and aromatherapy follow-up routes
- pricing expansion for Niveau 1, Niveau 2, Niveau 3, totals, weekly payments, and financing wording
- lower-cost / continuing-ed routing for “too expensive”, trial-course, short-course, and workshop phrasing
- handoff family for human, callback, send-info, campus-contact, and Julie/named-person requests
- regression harness coverage for all of the above

Latest verification gates:

- path classifier harness: `500/500`
- held-out utterance eval: `250/250`
- realistic conversation batch: `56` turns, `0` low-confidence rows
- live trust regression: `15` turns

Voice/audio checkpoint as of 2026-05-07:

- approved first-audio manifest: `scarlett_core/voice/manifests/ams_first_recording_batch_v1.json`
- generated/reviewed AMS service-tile assets: `28/28` current WAV files
- live browser voice path sends cached service-tile audio before generated answer chunks
- cached-only answers skip generated TTS to avoid duplicate playback
- final asset duration range: `1.63s–6.18s`, average `4.08s`

Latest additional gates:

- router guard regressions: `8/8`
- repair polish regressions: `6/6`
- action polish regressions: `6/6`
- handoff polish regressions: `6/6`
- campus/location regressions: `8/8`
- greeting polish regressions: `5/5`
- asset validation: `28/28` current AMS WAV files present

Next priority: real browser/iPhone voice pass for perceived first-audio timing, duplicate playback, awkward lines, and barge-in behaviour.

## Locked GitHub Baseline

As of the 2026-04-30 night wrap, the AMS receptionist baseline was committed and pushed to GitHub:

- Repository: `https://github.com/samgimagery/Scarlett`
- Branch: `main`
- Locked baseline commit: `63e23b8 Lock AMS receptionist baseline`
- Runtime mode: Telegram chat-only
- Voice/Gemini Live experiments: parked; not part of the locked AMS production path

The locked baseline includes:

- deterministic pricing and financing layer
- deterministic campus/location layer
- deterministic à-la-carte/continuing-ed layer
- conversation-state handling for short affirmations
- signup-button gating
- AMS service-flow prompt rules
- Smart Connections/local fallback retrieval
- Telegram-safe formatting

Do not move Scarlett back to Gemini Live without a new explicit product decision. The correct production channel remains the written Telegram receptionist; the live voice path is now a cached-first browser prototype for first-audio and service-tile validation.
