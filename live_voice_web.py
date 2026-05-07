#!/usr/bin/env python3
"""
Scarlett Live Voice — Web UI version.
Browser handles mic access (reliable), Python handles STT/LLM/TTS.
Single port: both HTTP and WebSocket on 8765.
"""

import asyncio
import json
import time
import numpy as np
import soundfile as sf
import tempfile
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from faster_whisper import WhisperModel

# Add receptionist dir to path for tts module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts as tts_engine

# --- Config ---
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "glm-5.1:cloud"
RAG_ASK_URL = "http://127.0.0.1:8000/ask"
LIVE_LANGUAGE = "fr"
PREFILLER_MANIFEST = Path("/Users/samg/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_fr_lora_overnight_20260504-215150/prefiller_bank_req112_v2_p0_speed075/manifest.json")

# Scarlett fine-tuned voice (default)
DEFAULT_VOICE = None  # None = use VOICE_MODE from tts.py (fine-tuned Scarlett)

STT_MODEL_SIZE = "small"
SYSTEM_PROMPT = """Tu es Scarlett, la réception virtuelle chaleureuse de l’Académie de Massage Scientifique. Réponds en français canadien naturel, clairement et brièvement. Tu aides avec les formations, prix, campus, inscriptions et prochaines étapes. Tu parles à voix haute: 1 à 3 phrases, pas de longs paragraphes."""


# --- Cached FR-CA prefiller bank ---
_prefillers = None

def load_prefillers():
    """Load the approved REQ-112 cached prefiller manifest, indexed by id and type."""
    global _prefillers
    if _prefillers is not None:
        return _prefillers
    by_id = {}
    by_type = {}
    if PREFILLER_MANIFEST.exists():
        items = json.loads(PREFILLER_MANIFEST.read_text(encoding="utf-8"))
        for item in items:
            if item.get("ok") and item.get("wav") and os.path.exists(item["wav"]):
                by_id[item["id"]] = item
                by_type.setdefault(item.get("type", "unknown"), []).append(item)
    _prefillers = {"by_id": by_id, "by_type": by_type}
    print(f"  ✅ Prefillers ready: {len(by_id)} cached clips", flush=True)
    return _prefillers

def select_prefiller(service_state, *, retrieval_running=False, answer_ready=False):
    """Pick the shortest honest cached line for the current service state. No random filler."""
    bank = load_prefillers()["by_id"]
    if service_state == "receipt":
        return bank.get("p0_receipt_003") or bank.get("p0_receipt_002")
    if service_state == "lookup" and retrieval_running:
        return bank.get("p0_lookup_004") or bank.get("p0_lookup_001")
    if service_state == "answer_bridge" and answer_ready:
        return bank.get("p0_answer_bridge_001")
    if service_state == "repair":
        return bank.get("p0_repair_003")
    if service_state == "greeting":
        return bank.get("p0_greeting_001")
    return None

async def send_cached_prefiller(websocket, service_state, **state):
    """Send a cached WAV chunk to the browser with metadata for latency display."""
    item = select_prefiller(service_state, **state)
    if not item:
        return False
    wav_path = item.get("wav")
    if not wav_path or not os.path.exists(wav_path):
        return False
    await websocket.send(json.dumps({
        "type": "audio_info",
        "time": "cached",
        "sampleRate": 24000,
        "streaming": True,
        "filler": True,
        "prefiller_id": item.get("id"),
        "prefiller_text": item.get("text"),
    }))
    with open(wav_path, "rb") as f:
        await websocket.send(f.read())
    await websocket.send(json.dumps({
        "type": "audio_chunk",
        "chunk": 0,
        "filler": True,
        "prefiller_id": item.get("id"),
    }))
    return True

# --- Models ---
_stt = None
conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

def get_stt():
    global _stt
    if _stt is None:
        _stt = WhisperModel(STT_MODEL_SIZE, device="cpu", compute_type="int8")
    return _stt

def transcribe(audio_path):
    model = get_stt()
    data, sr = sf.read(audio_path)
    if len(data.shape) > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    segments, _ = model.transcribe(data, language=LIVE_LANGUAGE, condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()

def generate(text):
    """Ask the grounded RAG receptionist first; fall back to Ollama if needed."""
    # Primary path: real RAG/service layers. This justifies lookup prefiller use.
    try:
        payload = json.dumps({"question": text, "language": LIVE_LANGUAGE}).encode()
        req = urllib.request.Request(RAG_ASK_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        answer = (data.get("answer") or "").strip()
        if answer:
            return answer
    except Exception as e:
        print(f"  ⚠️ RAG ask failed, falling back to Ollama: {e}", flush=True)

    conversation.append({"role": "user", "content": text})
    payload = json.dumps({"model": OLLAMA_MODEL, "messages": conversation, "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        reply = data.get("message", {}).get("content", "").strip()
    conversation.append({"role": "assistant", "content": reply})
    if len(conversation) > 20:
        conversation[:] = [conversation[0]] + conversation[-18:]
    return reply

def synthesize(text):
    """Use the tts module — fine-tuned Scarlett voice."""
    audio_path = tts_engine.generate_voice(
        text,
        lang=LIVE_LANGUAGE,
        voice=DEFAULT_VOICE,
        speed=0.65,
    )
    if not audio_path or not os.path.exists(audio_path):
        return None, 24000
    # Get sample rate from the generated file
    data, sr = sf.read(audio_path)
    return audio_path, sr


def split_voice_chunks(text, max_chars=155):
    """Split answers into small speakable chunks for faster first audio.

    Qwen3-TTS has a noticeable fixed startup cost, so one long sentence feels
    dead even when the answer is ready. This keeps chunks natural while giving
    the browser the first generated WAV as soon as possible.
    """
    base = [s.strip() for s in tts_engine._split_sentences(text or "") if s.strip()]
    if not base and text.strip():
        base = [text.strip()]
    chunks = []
    for sentence in base:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        parts = []
        current = ""
        # Prefer clause boundaries over arbitrary cuts. Do not split on literal
        # pipes because AMS programme names use "Niveau 1 | Praticien...".
        import re
        for piece in re.split(r"(?<=[,;:])\s+", sentence):
            piece = piece.strip()
            if not piece:
                continue
            if current and len(current) + 1 + len(piece) > max_chars:
                parts.append(current.strip())
                current = piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            parts.append(current.strip())
        if len(parts) == 1 and len(parts[0]) > max_chars:
            words = parts[0].split()
            current = ""
            parts = []
            for word in words:
                if current and len(current) + 1 + len(word) > max_chars:
                    parts.append(current)
                    current = word
                else:
                    current = f"{current} {word}".strip()
            if current:
                parts.append(current)
        chunks.extend(parts)
    return chunks or [text.strip()]

# --- WebSocket handler ---
async def handle_ws(websocket):
    print("  🔗 Client connected")
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Audio data from browser
                t0 = time.time()

                # Save to temp file
                tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                tmp.write(message)
                tmp.close()

                # STT
                text = transcribe(tmp.name)
                os.unlink(tmp.name)
                stt_time = time.time() - t0

                if not text or len(text.strip()) < 2:
                    await websocket.send(json.dumps({"type": "status", "text": "Didn't catch that, try again"}))
                    continue

                await websocket.send(json.dumps({"type": "transcript", "text": text, "time": f"{stt_time:.2f}s"}))

                # Cached-first FR-CA voice choreography.
                # 1) acknowledge immediately; 2) only use a lookup line if RAG is actually slow;
                # 3) bridge once the answer is ready while Qwen3-TTS cooks the first chunk.
                await send_cached_prefiller(websocket, "receipt")

                # RAG / LLM — run in the background so the voice layer can decide whether
                # a lookup prefiller is needed instead of always stacking filler lines.
                t1 = time.time()
                rag_task = asyncio.create_task(asyncio.to_thread(generate, text))
                lookup_sent = False
                try:
                    reply = await asyncio.wait_for(asyncio.shield(rag_task), timeout=0.70)
                except asyncio.TimeoutError:
                    lookup_sent = await send_cached_prefiller(websocket, "lookup", retrieval_running=True)
                    reply = await rag_task
                llm_time = time.time() - t1
                await websocket.send(json.dumps({"type": "reply", "text": reply, "time": f"{llm_time:.2f}s"}))

                chunks = split_voice_chunks(reply)
                # A short answer bridge makes the delay after retrieval feel intentional,
                # especially when live TTS has to generate several chunks.
                if chunks and (lookup_sent is False or len(reply) > 90):
                    await send_cached_prefiller(websocket, "answer_bridge", answer_ready=True)

                # TTS — stream every speakable chunk, including long single-sentence answers.
                tts_total_start = time.time()
                chunk_count = len(chunks)
                first_sent = True
                sent_chunks = 0

                for i, sentence in enumerate(chunks):
                    chunk_path, sr = await asyncio.to_thread(synthesize, sentence)
                    if not chunk_path or not os.path.exists(chunk_path):
                        continue

                    # Simple silence trim — fade in/out for clean transitions
                    chunk_path = await asyncio.to_thread(tts_engine._trim_silence, chunk_path)

                    with open(chunk_path, 'rb') as f:
                        chunk_data = f.read()
                    os.unlink(chunk_path)

                    if first_sent:
                        # Send header on first generated chunk
                        tts_first = time.time() - tts_total_start
                        await websocket.send(json.dumps({
                            "type": "audio_info",
                            "time": f"{tts_first:.2f}s",
                            "sampleRate": sr,
                            "streaming": chunk_count > 1,
                            "chunk": i + 1,
                            "total": chunk_count
                        }))
                        first_sent = False
                    else:
                        await websocket.send(json.dumps({
                            "type": "audio_chunk",
                            "chunk": i + 1,
                            "total": chunk_count
                        }))

                    await websocket.send(chunk_data)
                    sent_chunks += 1

                    # Brief pause between chunks for natural rhythm
                    await asyncio.sleep(0.04)

                tts_time = time.time() - tts_total_start
                await websocket.send(json.dumps({
                    "type": "audio_done",
                    "time": f"{tts_time:.2f}s",
                    "chunks": sent_chunks,
                    "planned_chunks": chunk_count
                }))
    except Exception as e:
        print(f"  ❌ Error: {e}")

# --- HTTP handler for serving UI files ---
from pathlib import Path as PPath
from websockets.http11 import Response, Request as WSRequest
from websockets.http import Headers

UI_DIR = PPath(os.path.dirname(os.path.abspath(__file__)))

async def handle_http(connection, request):
    """Serve static files for non-WebSocket HTTP requests."""
    # If this is a WebSocket upgrade request, let websockets handle it
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None
    
    path = request.path
    if path == '/' or path == '/live_voice_ui.html':
        file_path = UI_DIR / 'live_voice_ui.html'
    else:
        file_path = UI_DIR / path.lstrip('/')

    if file_path.exists() and file_path.is_file():
        body = file_path.read_bytes()
        content_types = {
            '.html': 'text/html', '.js': 'application/javascript',
            '.css': 'text/css', '.png': 'image/png',
        }
        content_type = content_types.get(file_path.suffix, 'application/octet-stream')
        return Response(
            200, 'OK',
            Headers([('Content-Type', content_type), ('Content-Length', str(len(body)))]),
            body=body,
        )
    return None  # Not a static file — proceed with WS handshake

# --- Main: single port for both HTTP and WS ---
async def main():
    print()
    print("=" * 50)
    print("  Scarlett Live Voice — Web UI")
    print("=" * 50)
    print("  Loading models...")
    get_stt()
    print("  ✅ STT ready")
    print(f"  🎙️ Voice: FR-CA Qwen3 LoRA + cached REQ-112 prefillers")
    load_prefillers()
    print()

    import websockets

    async with websockets.serve(
        handle_ws,
        "127.0.0.1",
        8765,
        process_request=handle_http,
    ):
        print("  🌐 HTTP + WS on http://localhost:8765")
        print("  🔗 Tailscale: https://samgs-mac-studio.tail3e92a8.ts.net/")
        print("  Open either URL in your browser")
        print()
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())