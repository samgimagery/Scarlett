---
title: "Scarlett Customer Instance Model"
type: product-architecture
status: draft-canonical
created: 2026-05-03
updated: 2026-05-03
tags:
  - scarlett
  - customer-instance
  - product
  - deployment
  - business-model
---

# Scarlett Customer Instance Model

Scarlett is best packaged as a managed system, not a self-serve chatbot product.

Sam keeps the cockpit. The customer gets the working receptionist.

## Business model

Scarlett is a done-for-you customer-service system.

Sam can remotely prepare a business before walking in:

1. create a customer instance
2. crawl the business website
3. ingest public files, PDFs, brochures, forms, images, videos, and policy pages
4. classify the knowledge into a clean vault/wiki
5. identify gaps, contradictions, and stale information
6. build a customer-specific service profile
7. connect a chat/voice channel
8. bring the business a working demo

The sales moment is strong: walk in with a laptop and let the business owner chat with their own business knowledge before they have done any technical work.

This sells the outcome, not the software.

## What the customer buys

Not “an AI chatbot”.

They buy:

> A managed AI receptionist built from the business’s actual knowledge, tuned to the way the business wants customers served.

The customer does not need to understand crawling, RAG, embeddings, vaults, service-flow logic, or hosting.

## Two layers

### Scarlett Core

Shared system used across all customers:

- ingestion pipeline
- Crawl4AI/source capture
- vault/wiki generation
- source map and raw archive
- RAG service
- deterministic facts framework
- service-flow engine
- conversation state
- channel adapters
- chat/voice rendering
- logs/review/tuning tools
- admin cockpit

### Customer Instance

Per-business configuration and data:

- `customer_id`
- business name
- domain(s)
- language(s)
- vault path
- source registry
- raw source archive
- structured facts
- service profile
- business rules
- channel tokens/settings
- brand/tone profile
- escalation contacts
- conversation logs
- QA/test set
- deployment config

Example:

```text
scarlett/
  core/
    ingestion/
    rag/
    service_flow/
    voice/
    channels/
    admin/
  customers/
    ams/
      customer.yaml
      vault/
      sources/
      rules/
      service-profile.md
      deterministic-facts.yaml
      channels.yaml
      logs/
      tests/
    clinic-example/
      customer.yaml
      vault/
      sources/
      rules/
      service-profile.md
```

## Customer creation order

### 1. Create instance

Capture:

- business name
- customer ID
- website/domain
- language(s)
- industry
- preferred channel(s)
- owner/admin contact
- escalation contact

### 2. Source capture

Collect:

- website pages
- PDFs
- downloadable documents
- forms
- price sheets
- policies
- FAQs
- photos/images when relevant
- videos/transcripts when relevant
- social/Google profile references only if explicitly needed

Raw sources are preserved. Clean notes are derived from them.

### 3. Vault classification

Build the customer vault:

- raw source index
- category hubs
- product/service notes
- policy notes
- pricing notes
- location/contact notes
- FAQ notes
- missing-info report
- contradiction report
- human-review queue

### 4. Service profile

Define how Scarlett should serve this business’s customers:

- role: receptionist, concierge, intake assistant, advisor, support desk
- customer types
- main paths/offers
- secondary/complementary offers
- objection handling
- preferred next steps
- forbidden claims
- unknown-answer policy
- escalation rules
- tone/formality
- language rules

### 5. Deterministic facts layer

Move high-risk answers out of fuzzy generation:

- prices
- financing/payment terms
- locations
- business hours
- dates/schedules when available
- registration/booking links
- catalog lists
- legal/refund/cancellation policies

These facts should be exact, testable, and easy to update.

### 6. RAG and service-flow connection

Connect:

```text
Customer question
→ service-flow classification
→ deterministic facts if needed
→ vault retrieval if needed
→ answer synthesis
→ next-step selection
→ channel delivery
→ log/review
```

### 7. Channel setup

Initial channels can include:

- Telegram bot
- website chat bubble
- admin demo chat
- later: voice call / web voice / phone line

Each channel uses the same Scarlett Core and Customer Instance.

### 8. QA before launch

Run customer-specific test sets:

- top 50 likely questions
- pricing questions
- location/contact questions
- buyer-path questions
- support questions
- edge cases
- unknown/missing info
- action/registration/booking flows

Review failures and tune before launch.

### 9. Managed tuning

Ongoing service:

- review unanswered questions
- fix bad routes
- update vault when the business changes pages/prices/forms
- add missing docs
- tune service flow
- update deterministic facts
- provide monthly summaries

This is recurring value.

## Deployment model

Recommended business model:

- Sam hosts/runs the system, at least initially.
- Customer gets channels and outcomes, not the cockpit.
- Infrastructure scales as demand grows: one server can host early customers; split customers/workers as load increases.
- Customer data should remain separated by instance.
- Logs and vaults should be per-customer.

This keeps setup quality high and protects the product method.

## Sales demo model

Before walking in:

1. crawl the business website
2. build a rough vault
3. create a temporary customer instance
4. connect demo chat
5. test 20 obvious questions
6. bring laptop/iPad
7. let owner ask questions about their own business

The pitch is simple:

> “I already built the first version from your public information. Ask it anything a customer would ask.”

Then sell cleanup, launch, and managed tuning.

## Why this is hard to copy

Competitors can copy a chatbot interface.

They cannot easily copy:

- Sam’s ingestion process
- the classified vault
- the service-flow engine
- deterministic business-facts layer
- tuning loop
- customer-specific rules
- hands-on deployment quality
- voice rhythm and live conversation timing

Scarlett is the system around the model.

## Rule portability boundary

Updated: 2026-05-07

Every customer instance should separate reusable engine rules from customer-specific rules.

**Reusable in Scarlett Core**

- service loop
- no lazy website deflection
- escalation discipline
- lightweight conversation memory
- anti-repeat behaviour
- goal-based advisor bundle mechanism
- one-next-step guidance
- regression harness structure
- review loop from real conversations

**Specific to each customer instance**

- business catalogue
- exact products/services
- prices and fees
- locations/service areas
- booking or registration links
- exact availability/dates when known
- industry language
- customer-specific bundles
- business-specific escalation policy

For a new company, the process is:

1. ingest sources
2. classify the catalogue
3. identify customer goals and natural clusters
4. create customer-specific bundles under the shared bundle mechanism
5. add deterministic facts for high-risk answers
6. write regression tests for every bundle and escalation rule
7. observe real questions and promote repeated friction into better service paths

The AMS work is a prototype customer instance, not hard-coded product strategy. The lesson is portable; the massage curriculum content is not.

## Customer-instance pause rule

Updated: 2026-05-07

After a customer instance reaches a stable advisor baseline, pause before adding more rules.

A stable baseline means:

- core service rules are working
- high-risk facts are deterministic
- main commercial/advisor paths are regression-tested
- short follow-ups preserve context
- source/vault docs match code behaviour

Next rules should come from real conversation friction, not speculative polishing.
