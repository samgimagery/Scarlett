# Scarlett AMS Locked Baseline

Locked by Sam on 2026-04-30.

This is the current correct receptionist baseline for AMS.

## Preserve This Behaviour

- French-first Telegram chat receptionist.
- Chat-only for now; voice is parked.
- AMS vault is the active customer truth.
- The bot is Scarlett, AMS reception — never a vault, note browser, source reader, or generic chatbot.
- Direct questions are answered first.
- Qualification is natural and remembered.
- One useful next step at a time.
- Generic “oui / ok / d’accord” continues the active offer; it does not automatically trigger signup.
- Signup/form button appears only on clear registration/form/link/reserve-place intent.

## Course Ordering

New student:

1. Niveau 1 | Praticien en massothérapie — 400h — 4 995 $
2. Then guide by price, content, campus, date, or inscription depending on what they ask.

Already trained/practitioner:

1. Niveau 2 — 600h — 7 345 $
   - Masso-kinésithérapie spécialisation en sportif
   - Massothérapie avancée spécialisation anti-stress
2. Niveau 3 | Orthothérapie avancée — 300h — 3 595 $
3. À-la-carte / formation continue as complements.

Do not lead trained practitioners with small à-la-carte courses unless they explicitly ask for them.

## Deterministic Layers

- `location_layer.py` — fixed campus/location answers.
- `pricing_layer.py` — prices, totals, financing/payment answers.
- `continuing_ed_layer.py` — à-la-carte course list.

These run before general RAG/LLM generation.

## Fixed Pricing

- Niveau 1: 4 995 $
- Niveau 2: 7 345 $
- Niveau 3: 3 595 $
- Niveau 1 + 2: 12 340 $
- Niveau 1 + 2 + 3: 15 935 $

Weekly references:

- Niveau 1: from 104 $ / week
- Niveau 2: from 111 $ / week
- Niveau 3: from 97 $ / week

## Operational Commands

Restart:

```bash
uid=$(id -u)
launchctl kickstart -k gui/$uid/com.scarlett.receptionist-rag
launchctl kickstart -k gui/$uid/com.scarlett.receptionist-telegram
```

Health:

```bash
curl -s http://127.0.0.1:8000/health
```

## GitHub Record

Night wrap confirmation, 2026-04-30:

- GitHub repo: `https://github.com/samgimagery/Scarlett`
- Branch: `main`
- Locked commit: `63e23b8 Lock AMS receptionist baseline`
- Branch status at wrap: aligned with `origin/main`

Experimental Gemini Live / voice files may exist locally from earlier exploration. They are not part of the locked AMS receptionist baseline unless explicitly reintroduced later.
