---
title: "Scarlett Brain v1"
type: product-architecture
status: draft-canonical
created: 2026-05-06
updated: 2026-05-06
tags:
  - scarlett
  - brain
  - rag
  - customer-instance
  - tuning-loop
---

# Scarlett Brain v1

Scarlett Brain is the product boundary that turns a business knowledge base into a reliable receptionist answer.

```text
sources → vault → facts → retrieval → answer → review
```

## Contract

### 1. Sources

Raw business materials are preserved before they are rewritten:

- website pages
- PDFs, brochures, price sheets, forms, and policies
- images/video transcripts where useful
- owner corrections and operational notes

### 2. Vault

Sources become a structured business vault/wiki:

- service notes
- program/product pages
- pricing and financing notes
- location/contact notes
- policies
- FAQ and objection notes
- contradiction and missing-info reports

The vault is Scarlett’s business memory, not something exposed to customers.

### 3. Facts

High-risk answers bypass fuzzy generation:

- prices
- totals
- locations
- forms and signup links
- course lists
- dates/schedules when exact data exists
- policies and eligibility rules

Facts must be exact, testable, and easy to update per customer instance.

### 4. Retrieval

If no deterministic fact answers the question, Scarlett searches the customer vault and passes only relevant context to the LLM.

Retrieval must prefer specific business notes over broad internal hubs and must exclude operational/boot/archive material.

### 5. Answer

Scarlett answers as a receptionist:

- answer the direct question first
- orient the customer calmly
- guide one useful next step
- never mention vaults, internal notes, sources, files, or implementation details
- escalate only when the specific answer is genuinely unavailable

### 6. Review

Weak answers are not just logs. They become tuning inputs.

Scarlett Brain queues an answer for review when it detects:

- generation without sources
- low retrieval score
- generation error
- refusal
- thin “contact the office” escalation

Current implementation writes local JSONL review items to:

```text
~/AI/OpenClaw/dev/receptionist/brain_review_queue.jsonl
```

The future admin cockpit can turn these items into:

- corrected answers
- new deterministic facts
- service-flow rules
- vault note fixes
- test cases

## Current implementation

Code lives in:

```text
scarlett_core/brain/
```

FastAPI exposes:

```text
GET /brain/contract
GET /brain/review-queue
```

`POST /ask` now emits a Brain trace and sends weak answers into the review queue while preserving the locked AMS receptionist behaviour.

## Why this matters

Scarlett is not prompt glue. The Brain gives the product a durable learning loop:

```text
customer asks → Scarlett answers → weak answer is captured → Sam corrects → correction becomes facts/rules/vault/tests
```

That is how each customer instance becomes sharper over time.
