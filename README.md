# Receptionist Bot

Vault-grounded Q&A service. Answers questions using only your Obsidian vault — zero hallucination.

## Architecture

```
Question → FastAPI /ask
    → Smart Connections MCP (search vault)
    → Check similarity threshold
    → Ollama gemma4:e4b (generate grounded answer)
    → Log interaction (SQLite)
    → Return answer + sources
```

## Quick Start

```bash
# Install dependencies
cd ~/AI/OpenClaw/dev/receptionist
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the service
python main.py
```

## API Endpoints

### POST /ask

Ask a question, get a grounded answer.

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the receptionist bot?"}'
```

Optional params:
- `language`: "en" (default) or "fr"
- `threshold`: similarity threshold override (default 0.45)
- `max_notes`: max context notes override (default 5)

### GET /health

Health check — Ollama status, model, vault path.

### GET /logs?limit=20

Recent interaction logs.

### GET /unanswered?limit=20

Questions that were refused (below threshold) — for the learning loop.

### GET /stats

Knowledge base statistics from Smart Connections MCP.

## Configuration

All settings in `config.py`. Key ones:

- `OLLAMA_MODEL`: default `gemma4:e4b`
- `SIMILARITY_THRESHOLD`: default `0.45`
- `MAX_CONTEXT_NOTES`: default `5`
- `RESPONSE_LANGUAGE`: default `en`

## Environment Variables

- `RECEPTIONIST_MODEL` — override the Ollama model
- `RECEPTIONIST_THRESHOLD` — override the similarity threshold
- `RECEPTIONIST_LANGUAGE` — override the response language
- `RECEPTIONIST_PORT` — override the port (default 8000)
- `RECEPTIONIST_VAULT_PATH` — override the vault path