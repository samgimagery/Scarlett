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

See `voice/README.md` for the canonical FR-CA voice direction, speed split, mega prefiller bank, and production rights rule.
