# Orpheus Bench Setup — REQ-108

## Installed

- `external/Orpheus-FastAPI/` cloned from `Lex-au/Orpheus-FastAPI`
- Python 3.11 virtualenv at `external/Orpheus-FastAPI/.venv`
- Installed Orpheus-FastAPI requirements, including:
  - FastAPI / Uvicorn
  - PyTorch macOS arm64
  - `snac==1.2.1`
  - audio/system deps from upstream requirements
- Local `.env` created for Mac-only local testing:
  - `ORPHEUS_API_URL=http://127.0.0.1:11434/v1/completions`
  - `ORPHEUS_HOST=127.0.0.1`
  - `ORPHEUS_PORT=5005`

## Model install

Attempted tag:

```bash
ollama pull legraphista/Orpheus:3b-ft-q4
```

Result: tag did not exist.

Approved/default model:

```bash
ollama pull legraphista/Orpheus
```

This is the ~2.4GB Q4_K_M model exposed as `legraphista/Orpheus:latest`. Sam approved it for the English live-feel path because speed beats the small clarity delta versus Q8.

Quality-reference model only:

```bash
ollama pull legraphista/Orpheus:3b-ft-q8
```

## Important architecture note

Ollama can load/generate Orpheus GGUF tokens, but it does **not** produce playable audio by itself. The missing middle is SNAC decode:

```text
Ollama / llama.cpp GGUF → Orpheus audio tokens → SNAC decoder → WAV/PCM audio
```

That is why Orpheus-FastAPI is installed: it should provide the wrapper/server and SNAC decode path.

## Alice research handoff

Alice should research and confirm:

1. How Orpheus-FastAPI extracts custom audio tokens from OpenAI-compatible backend responses.
2. Whether Ollama `/v1/completions` response shape is compatible without patches.
3. SNAC warmup/window rules: 28-token window, 7-token audio frames.
4. Whether `snac==1.2.1` on macOS CPU is acceptable for realtime decode.
5. Current status of native llama.cpp Orpheus/SNAC support.
6. Whether French GGUF uses the same prompt/token format and voice names.

## Next commands after model pull completes

```bash
cd ~/AI/OpenClaw/dev/receptionist/orpheus_bench
python3 run_bench.py --readiness

cd external/Orpheus-FastAPI
source .venv/bin/activate
python app.py
```

Then test:

```bash
curl -s http://127.0.0.1:5005/docs
python3 chunking_poc.py --scenario q4_turn_taking --voice leah
python3 chunking_poc.py --scenario q4_receptionist_primitives --voice leah
```

## French Q8 wiring — 2026-05-04

Registered downloaded French GGUF with Ollama:

```bash
ollama create orpheus-french-q8 -f models/french/Modelfile
```

Model path:

```text
/Users/samg/Media/models/orpheus-gguf/Orpheus-3b-French-FT-Q8_0.gguf
```

For the French bench, `external/Orpheus-FastAPI/.env` is currently pointed at:

```text
ORPHEUS_MODEL_NAME=orpheus-french-q8:latest
```

Previous English Q4 env is saved at:

```text
external/Orpheus-FastAPI/.env.q4-backup-20260504
```

Generated review package:

```text
outputs/language_bank/scarlett_fr_q8_amelie_marie_review_package_20260504.zip
```
