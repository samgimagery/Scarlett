# Scarlett Timing Policy v1

Purpose: make Scarlett feel fast without pretending generation is instant.

The voice layer should decide what to do during the gap between user speech ending and the real answer being ready.

## Timing bands

- `0–300ms` — **silence**
  - Natural pause. Do not fill.
  - Best for likely continuation or very fast deterministic answer.

- `300–800ms` — **tiny receipt**
  - Examples: “Oui.”, “OK.”, “Je vois.”, “Parfait.”
  - Use only when it confirms the user was heard.
  - Must be interruptible.

- `800–1800ms` — **lookup line**
  - Examples: “Je vérifie ça.”, “Je regarde.”, “Deux petites secondes.”
  - Use only when real lookup/generation is happening.
  - Must be interruptible and cancellable when the answer is ready.

- `1800–3500ms` — **prebuilt service chunk**
  - A short polished line that advances the interaction while generation completes.
  - Example: for “comment ça fonctionne?”: “Oui — je vais d’abord situer ton point de départ, puis je te donne le bon parcours.”
  - Must not contain volatile facts unless sourced from deterministic bank.

- `3500ms+` — **progress or fallback**
  - Use a second progress line only if still genuinely working.
  - If confidence is low, ask a clarifying question rather than padding.

## Voice strategy types

- `silent_wait` — no audio; user is likely still thinking or answer is near-instant.
- `receipt` — tiny acknowledgement.
- `lookup_line` — honest latency cover.
- `prebuilt_tile` — full or partial prerecorded service response.
- `hybrid_tile_then_generate` — prerecorded opening + generated specifics.
- `live_generate` — no prerecorded answer; generate full answer.
- `clarify` — ask targeted clarification before answering.
- `handoff_or_escalate` — human follow-up path.

## Interruptibility

Every non-final audio line must be interruptible.

Rules:

- If user speaks, stop playback immediately.
- Do not resume old filler after interruption.
- If final answer becomes ready while filler plays, stop filler at next safe boundary.
- Never stack more than two filler/service lines before an actual answer or clarification.

## Prebuilt tile rules

A prebuilt tile is allowed when:

- the intent is common and stable
- facts are deterministic or absent
- wording can be polished once and reused
- the line remains true across campuses/schedules
- interruption does not break meaning

A prebuilt tile is not allowed when:

- exact dates/availability are required
- personal file/student status is needed
- uncertain eligibility is involved
- the answer depends on retrieved content not yet known

## Latency budgets

- deterministic local fact answer: target `<300ms`, max `800ms`
- common service tile: target `<500ms`, max `1000ms`
- RAG answer: target first audio `<900ms`, max first audio `1800ms`
- live generated full answer: target first audio `<1800ms`, max `3500ms`
- clarification: target `<800ms`

## Scarlett-specific principle

Fast is not the same as rushed. The goal is composed responsiveness: short, useful, cancellable speech at the right moment.
