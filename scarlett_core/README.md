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
