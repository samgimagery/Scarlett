# Scarlett — AMS Receptionist

Scarlett is the Telegram receptionist for the Académie de Massage Scientifique (AMS).

Status: locked as the correct AMS receptionist baseline as of 2026-04-30.

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
- Voice: intentionally parked; text mode is the correct current product mode

## What Scarlett Must Do

Scarlett should:

- answer direct questions first
- qualify naturally as new student vs already trained/practitioner
- guide one useful step at a time
- avoid repeating greetings or asking the same qualification again
- avoid closed “A or B?” loops where a simple “oui” breaks the flow
- remember the last active offer so “oui / ok / d’accord” continues correctly
- never expose internal notes, vaults, service recipes, sources, or implementation details
- never claim live internet, calendar, or map access
- never invent prices, dates, policies, campuses, prerequisites, or recognition claims
- use AMS fixed local data confidently where available

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

- `continuing_ed_layer.py`
  - à-la-carte course list
  - price/hour/format snippets
  - prevents “I don’t have the list” failures

## Runtime Architecture

Request path:

1. Telegram text message
2. `telegram_bot.py`
3. deterministic direct-flow checks
4. FastAPI `/ask` in `main.py`
5. deterministic local layers
   - location
   - pricing/financing
   - à-la-carte list
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
- `continuing_ed_layer.py` — deterministic à-la-carte list
- `config.py` — AMS vault path, model, language, service port
- `ollama_client.py` — Ollama generation
- `logger.py` — SQLite interaction logging
- `tts.py` and voice files — retained but not current product path

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

- generic receptionist engine
- customer vault ingestion pipeline
- customer-specific service profile/soul
- deterministic business facts layer for prices, locations, dates, forms, and catalog lists
- human approval workflow before website changes update the active truth

AMS is the locked baseline for “correct receptionist behaviour,” especially the service flow: answer, discover, connect course features to benefits, then offer the right next step.
