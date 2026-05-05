# Scarlett Core

Shared engine for every Scarlett customer instance.

Scarlett Core is the reusable system layer:

- ingestion and source capture
- vault/wiki preparation
- RAG and retrieval
- service-flow engine
- deterministic business facts
- channel adapters
- voice pipeline
- admin/review/tuning tools

Customer-specific data does not live here. It lives under `customers/<customer_id>/`.


## Voice architecture

Scarlett Core owns the reusable live-voice layer. The locked direction is cached-first: a large prefiller bank gives immediate response while Scarlett retrieves, reasons, and generates short answer chunks behind it.

See `voice/README.md` for the canonical FR-CA voice direction, speed split, mega prefiller bank, payment-objection voice rule, and production rights rule.

## Service posture

Scarlett should not sound like a bot with infinite branches. When the customer has already heard the known payment paths, the correct service move is patience and closure: acknowledge the cost, stop implying more hidden options, and ask whether they want a specific option detailed or need anything else.

This behaviour belongs in Core because it applies across customer instances: finite facts should produce finite answers.
