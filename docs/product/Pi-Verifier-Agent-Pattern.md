---
title: "Pi Verifier Agent Pattern"
type: reference
status: captured
created: 2026-05-06
updated: 2026-05-06
source: "https://github.com/disler/the-verifier-agent"
local_source: "/Users/samg/.openclaw/workspace/sources/the-verifier-agent"
license: MIT
tags:
  - agentic-engineering
  - verifier-agent
  - pi-agent
  - scarlett-brain
  - testing-harness
---

# Pi Verifier Agent Pattern

Local copy:

```text
/Users/samg/.openclaw/workspace/sources/the-verifier-agent
```

GitHub:

```text
https://github.com/disler/the-verifier-agent
```

## What it is

A two-agent Pi Coding Agent harness:

- **Builder** — normal interactive Pi agent that does the work.
- **Verifier** — sibling Pi child session with locked input, read-only tools, and a verifier persona.

The builder emits lifecycle events. The verifier independently reads the builder's session JSONL slice, decomposes claims into atomic checks, verifies against actual state, and sends correction feedback back to the builder when it finds a fixable failure.

## Core design

```text
Builder Pi
  ├─ owns Unix socket: /tmp/pi-verifier/<sessionId>.sock
  ├─ writes session JSONL
  ├─ emits lifecycle events: start / stop / error
  └─ receives correction prompts as follow-up messages

Verifier Pi
  ├─ launches as child window/tmux session
  ├─ input is locked
  ├─ reads builder JSONL slice only
  ├─ uses read-only tools
  ├─ emits ## Report
  └─ calls verifier_prompt when correction is needed
```

## Important source files

- `README.md` — overview, architecture, quick start, confidence ladder.
- `.pi/verifier/agents/verifier.md` — generic verifier persona.
- `.pi/verifier/prompts/verify_on_stop.md` — per-turn verification prompt.
- `apps/verifier/verifiable.ts` — builder-side extension, socket server, lifecycle forwarding, builder feedback injection.
- `apps/verifier/verifier.ts` — verifier-side extension, locked input, status bar, prompt/report transport.
- `apps/verifier/_shared/ipc.ts` — JSONL IPC envelope protocol.
- `apps/verifier/_shared/frontmatter.ts` — persona frontmatter parser and simple placeholder templating.
- `justfile` — `just v` launches builder + verifier.

## Persona frontmatter

The verifier persona is a markdown file with frontmatter:

```yaml
---
name: verifier
description: Generic verifier — decomposes the user's request into atomic claims, validates each independently, reports.
tools: read, grep, find, ls, bash, verifier_prompt
model: openai/gpt-5.5
domain: generic
max_loops: 3
---
```

Required fields in source:

- `name`
- `description`
- `tools`
- `model`
- `domain`

Optional:

- `max_loops`
- `verification_focus`

The persona body becomes the verifier's full system prompt. Pi's default prompt is overwritten by design.

## Verifier instructions that matter

The generic verifier persona says:

- Verify, do not build.
- Tool surface is read-only: `read`, `grep`, `find`, `ls`, constrained `bash`, and `verifier_prompt`.
- The builder's final message is a claim, never proof.
- Break claims into smallest atomic units.
- Cite deterministic evidence for every verified claim.
- Mark anything without evidence as unsure.
- If a concrete fix exists, call `verifier_prompt` before the report.
- Stop after the report.

## Confidence ladder

- **PERFECT** — every atomic claim verified, zero gaps, no feedback.
- **VERIFIED** — checked claims passed; minor non-blocking gaps allowed.
- **PARTIAL** — no failures, but significant unverifiable gaps.
- **FEEDBACK** — at least one failed claim and verifier prompted builder.
- **FAILED** — verifier could not verify at all; human escalation.

## Report contract

The verifier must end with exactly one block:

```markdown
## Report

STATUS: verified | failed | unsure
CONFIDENCE: PERFECT | VERIFIED | PARTIAL | FEEDBACK | FAILED

### What did you verify?
- <atomic claim>: <exact tool output + verdict>

### What could you not verify?
- <claim>: <why>

### What feedback did you give?
<message or none>

### What do you need from me to verify this next time?
<nothing or missing oracle/harness/fixture>

### Verification metadata
- turn_index: <TURN_INDEX>
- atomic_claims_total: <N>
- atomic_claims_verified: <N>
- atomic_claims_failed: <N>
- atomic_claims_unverified: <N>
```

## IPC protocol

The transport uses JSONL frames over a Unix socket.

Direction matrix:

```text
verifier → builder: hello, prompt, report
builder → verifier: hello_ack, prompt_ack, event
both directions: ping, pong, bye
```

Events include:

- `start`
- `stop`
- `error`

The stop event carries:

- `userPrompt`
- `turnIndex`
- `sessionFileStartLine`
- `sessionFileEndLine`

That lets the verifier read only the current turn slice, not the whole transcript.

## Why this matters for Scarlett Brain

The pattern maps cleanly to REQ-116:

```text
Scarlett Brain answer
→ harness captures answer/sources/layer/latency/review trigger
→ tester persona decomposes claims
→ deterministic checks score facts, service flow, tone, source leakage, escalation
→ feedback becomes classified fix
→ Alfred applies safe fix
→ harness reruns
```

The key is not a chatting tester. The key is a **locked tester persona** plus deterministic scripts.

## Recommended Scarlett adaptation

Create:

```text
scarlett_core/brain/testing/
  test_pack_ams.jsonl
  run_harness.py
  scorer.py
  Scarlett Brain Tester.md
  reports/
```

The tester should be read-only and should never edit production. It should output a report with:

- atomic claim checks
- correctness score
- service-flow score
- tone/repetition score
- source-leakage check
- fix classification
- whether Alfred should patch facts, service rules, vault notes, retrieval ranking, prompt, or tests

## Safety rule

Do not let the tester self-mutate production. The loop may propose fixes and classify failures. Alfred applies and verifies them.
