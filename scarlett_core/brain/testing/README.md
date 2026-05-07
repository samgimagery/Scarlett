# Scarlett Brain Testing

REQ-116 harness area.

Files:

- `test_pack_ams.jsonl` — representative AMS regression cases.
- `run_harness.py` — calls Scarlett `/ask`, scores deterministic checks, writes reports.
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

Next expansion: add multi-turn follow-up fixtures and structured service-flow expectations before putting Pi beside the harness as a critic.
