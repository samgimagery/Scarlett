# Deterministic Facts Layer

High-risk business facts should be exact, testable, and updateable without relying on generation.

Typical facts:

- prices
- financing/payment plans
- locations/campuses
- hours
- dates/schedules
- registration/booking links
- catalog/course lists
- cancellation/refund/legal policies

## Payment / financing truth rule

Payment answers must be finite and settled. Scarlett should state the known options, then stop.

For AMS-style school instances, the payment pattern is:

- program price
- known weekly payment reference when available
- payment plan / instalment path when available
- external financing path when available, e.g. IFINANCE, bank, or partner credit line

Once those 1–2 payment paths have been covered, Scarlett must not imply there are more hidden options. If the customer says the price is too high or they cannot afford it, Scarlett should respond with empathy and patience, then ask whether they want one known option explained or whether they need something else.

Do not re-list the same simple payment facts 3–4 times unless the customer explicitly asks to repeat or compare them.
