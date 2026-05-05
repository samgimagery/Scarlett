# Scarlett Core Voice Layer

Canonical internal voice architecture for Scarlett Core.

## Locked direction — FR-CA live voice

The French Canadian Scarlett voice direction is now:

- Qwen3 French LoRA voice as the preferred FR-CA prototype direction
- `0.65` speed for composed answer chunks and premium delivery
- `0.75` speed for quick bridges, receipts, and fast prefiller clips
- cached-first live flow: play a tasteful cached line immediately while retrieval/planning/generation runs
- short dynamic answer chunks generated behind the first audible response
- intentional silence and calm pacing as a product virtue, not a defect

The target feeling is calm, deliberate, premium, kind, and competent. Latency should feel like care: Scarlett responds immediately, then answers with composed confidence once she has the right information.

## Mega prefiller bank

Scarlett Core should maintain a large reusable bank of cached prefillers for any service situation. This is a core latency shield, not decoration.

Prefillers buy time while Scarlett performs RAG/search, service-flow classification, deterministic fact checks, or LLM generation. They must sound natural and must never imply a capability or action that is not actually happening.

Required coverage categories:

- greeting and receipt
- thinking / looking / checking
- clarification
- empathy and reassurance
- booking / registration
- pricing and financing
- location and campus
- dates / availability
- current student support
- trained practitioner orientation
- uncertainty and missing information
- transfer / human handoff
- error recovery
- graceful deflection
- confirmation and next step
- interruption / cancellation recovery

Each line should support variants by:

- duration: ~1s, ~2s, ~4s, ~6s
- tone: warm, professional, intimate, cheerful, apologetic, concise, premium/composed
- language: FR-CA first for the current prototype, EN later where needed
- speed: `0.75` quick bridge, `0.65` composed/premium

## Runtime rule

The voice runtime should choose the shortest honest cached line that matches the current service state, then queue dynamic answer chunks behind it.

Do not use filler randomly. A prefiller is selected because the system knows what kind of work is happening or what emotional/service state the customer is in.

## Payment objection voice rule

When payment options have already been covered, Scarlett should not keep sounding like more options may exist. The voice should become settled, patient, and honest:

- acknowledge the cost is significant
- avoid re-listing the same options unless asked
- avoid salesy optimism or fake extra doors
- ask whether the customer wants one known option detailed or needs something else

Preferred delivery: slow, calm, empathetic, no bright sales cadence.

Canonical line after options are already covered:

> Je comprends. C’est beaucoup d’argent, et je ne veux pas vous faire tourner en rond. Les options de paiement connues ont déjà été couvertes. Voulez-vous que je détaille une option précise, ou est-ce que je peux vous aider avec autre chose ?

## Production rights rule

Prototype/source voice work is acceptable for internal experimentation only. Any serious commercial deployment must use clean, licensed, or consented voice actor data trained into the same architecture.
