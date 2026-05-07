# Scarlett Brain Testing

REQ-116 harness area.

Files:

- `test_pack_ams.jsonl` — representative AMS regression cases.
- `run_harness.py` — calls Scarlett `/ask`, scores deterministic checks, writes reports.
- `run_multiturn_v2.py` — runs long Telegram-like conversations with state, context carryover, no-loop checks, fake-action guards, and route assertions.
- `reports/` — timestamped harness outputs.

Loop:

```text
test pack → /ask runner → deterministic scorer → report → Alfred fix → rerun
```

Pi/tester agents are critics only after the local harness exists.

## First baseline run

Latest clean run: `reports/scarlett_brain_harness_20260505-223143.md`

Result: 10/10 VERIFIED after two safe fixes:

- campus-list questions now route through `local_location_layer` (`location_layer.py`)
- internal-source requests now route through `local_safety_layer` (`main.py`)

Current expansion: multi-turn v2 covers budget-to-trial-to-handoff, aromatherapy correction memory, trained-student path continuity, campus-to-contact, and security recovery back to normal programme questions.
