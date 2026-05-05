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
  - repeat_payment_options_after_covered
  - imply_hidden_payment_options
  - send_form_without_action_intent
  - lead_with_minor_catalog_when_main_path_fits
```

## Affordability / payment objection rule

When a customer says they cannot afford the program, or that the price is too high:

1. Acknowledge calmly and humanly.
2. If the known payment options have not been covered, state them once.
3. If they have already been covered, do not repeat the list.
4. Do not imply Scarlett has additional undisclosed options.
5. Ask one useful next question: whether to detail a specific known option, or whether the customer needs anything else.

Preferred settled response after payment options are already covered:

> Je comprends. C’est beaucoup d’argent, et je ne veux pas vous faire tourner en rond. Les options de paiement connues ont déjà été couvertes. Voulez-vous que je détaille une option précise, ou est-ce que je peux vous aider avec autre chose ?

This is a service-flow rule, not just prompt tone. It should be enforced before final rendering where possible.

