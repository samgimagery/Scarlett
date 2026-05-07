# Scarlett Brain v1

Scarlett Brain is the product boundary for a customer answer.

Contract:

```text
sources → vault → facts → retrieval → answer → review
```

What lives here:

- the Brain contract
- per-answer trace stages
- weak-answer review logging
- future customer-instance orchestration

What does not live here yet:

- customer-specific AMS facts
- Telegram formatting
- voice playback
- raw source crawling

The current AMS service keeps its working FastAPI route in `main.py`, but that route now emits Brain traces and review items through this module. This gives Scarlett a durable tuning loop without destabilizing production text mode.
