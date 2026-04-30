"""
Ollama client — sends prompts to local Ollama for generation.
Uses /api/chat endpoint which handles thinking models correctly.
"""
import sys
import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL


def generate(prompt, system=None, temperature=0.1, max_tokens=1024):
    """Send a prompt to Ollama using the chat endpoint."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        # Qwen thinking models otherwise spend the whole budget in hidden reasoning
        # and return empty content for short API calls.
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }
    
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        if content:
            return content
        # Empty response — thinking model used all tokens for reasoning
        print(f"Ollama returned empty content, eval_count={data.get('eval_count')}", file=sys.stderr)
        return None
    except requests.exceptions.Timeout:
        print("Ollama timeout", file=sys.stderr)
        return None
    except requests.exceptions.ConnectionError:
        print("Ollama connection error", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Ollama error: {e}", file=sys.stderr)
        return None


def check_ollama():
    """Check if Ollama is running and the model is available."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        data = response.json()
        models = [m["name"] for m in data.get("models", [])]
        return OLLAMA_MODEL in models or any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False