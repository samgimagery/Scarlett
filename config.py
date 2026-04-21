"""
Receptionist Bot — Configuration
"""
import os

# Vault
VAULT_PATH = os.environ.get(
    "RECEPTIONIST_VAULT_PATH",
    "/Users/samg/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mission Control"
)

# MCP Server
MCP_SERVER_PATH = os.path.expanduser("~/smart-connections-mcp/dist/index.js")

# Ollama
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("RECEPTIONIST_MODEL", "qwen3-coder:30b")

# RAG settings
SIMILARITY_THRESHOLD = float(os.environ.get("RECEPTIONIST_THRESHOLD", "0.25"))
MAX_CONTEXT_NOTES = int(os.environ.get("RECEPTIONIST_MAX_NOTES", "3"))
MAX_CONTEXT_CHARS = int(os.environ.get("RECEPTIONIST_MAX_CHARS", "6000"))

# Language
RESPONSE_LANGUAGE = os.environ.get("RECEPTIONIST_LANGUAGE", "en")  # en, fr, etc.

# Server
HOST = os.environ.get("RECEPTIONIST_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECEPTIONIST_PORT", "8000"))

# Telegram Bot
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", f"http://{HOST}:{PORT}")

# Logging
LOG_DB = os.path.expanduser("~/AI/OpenClaw/dev/receptionist/logs.db")