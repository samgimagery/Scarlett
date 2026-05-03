# Scarlett Service Flow Engine

Internal scaffolding for elite customer-service behaviour.

Core loop:

1. Receive
2. Understand
3. Orient
4. Answer
5. Guide
6. Remember
7. Recover

This layer decides the shape of service before the final response is rendered. It should produce an internal plan, not customer-facing explanation.

Example internal plan:

```yaml
customer_status: new | trained | current | unknown
intent: price | location | dates | registration | support | comparison | exploration | objection | other
answer_priority: deterministic | rag | clarify | escalate
next_step: ask_open_question | offer_campus | offer_payment | offer_form | offer_human | close_warmly
forbidden_moves:
  - repeat_greeting
  - repeat_qualification
  - send_form_without_action_intent
  - lead_with_minor_catalog_when_main_path_fits
```
