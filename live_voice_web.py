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
from pathlib import Path
from faster_whisper import WhisperModel

# Add receptionist dir to path for tts module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts as tts_engine

# --- Config ---
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "glm-5.1:cloud"

# Scarlett fine-tuned voice (default)
DEFAULT_VOICE = None  # None = use VOICE_MODE from tts.py (fine-tuned Scarlett)

STT_MODEL_SIZE = "small"
SYSTEM_PROMPT = """You are Scarlett, a warm and thoughtful companion. You help people find information from the knowledge base, but you speak like someone who genuinely cares — not like a search engine with manners. Be present, be curious, connect ideas naturally. Answer concisely — 1-3 sentences. You're speaking aloud, not writing essays."""

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
    segments, _ = model.transcribe(data, language="en", condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()

def generate(text):
    import urllib.request
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
        lang="en",
        voice=DEFAULT_VOICE,
    )
    if not audio_path or not os.path.exists(audio_path):
        return None, 24000
    # Get sample rate from the generated file
    data, sr = sf.read(audio_path)
    duration = len(data) / sr
    return audio_path, sr

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

                # CSM Filler — send instant filler audio while LLM + TTS work
                # This runs CSM in a subprocess, so we can start it before LLM
                filler_path = None
                if tts_engine.CSM_MODEL_AVAILABLE:
                    import asyncio as _a
                    filler_path = await _a.to_thread(
                        tts_engine.generate_csm_filler, lang="en"
                    )
                    if filler_path and os.path.exists(filler_path):
                        with open(filler_path, 'rb') as f:
                            filler_data = f.read()
                        os.unlink(filler_path)
                        await websocket.send(json.dumps({
                            "type": "audio_info",
                            "time": "0.3s",
                            "sampleRate": 24000,
                            "streaming": True,
                            "filler": True
                        }))
                        await websocket.send(filler_data)
                        await websocket.send(json.dumps({"type": "audio_chunk", "chunk": 0, "filler": True}))

                # LLM
                t1 = time.time()
                reply = generate(text)
                llm_time = time.time() - t1
                await websocket.send(json.dumps({"type": "reply", "text": reply, "time": f"{llm_time:.2f}s"}))

                # TTS — streaming: send first chunk immediately, then rest
                t2 = time.time()
                sentences = tts_engine._split_sentences(reply)
                
                if len(sentences) <= 1:
                    # Single sentence — generate and send whole thing
                    audio_path, sr = synthesize(reply)
                    tts_time = time.time() - t2
                    if audio_path:
                        with open(audio_path, 'rb') as f:
                            audio_data = f.read()
                        os.unlink(audio_path)
                        await websocket.send(json.dumps({"type": "audio_info", "time": f"{tts_time:.2f}s", "sampleRate": sr, "streaming": False}))
                        await websocket.send(audio_data)
                else:
                    # Multiple sentences — stream chunks
                    chunk_count = len(sentences)
                    first_sent = True
                    tts_total_start = time.time()
                    
                    for i, sentence in enumerate(sentences):
                        chunk_path = tts_engine.generate_voice(sentence, "en", voice=DEFAULT_VOICE)
                        if not chunk_path or not os.path.exists(chunk_path):
                            continue
                        
                        # Simple silence trim — fade in/out for clean transitions
                        chunk_path = tts_engine._trim_silence(chunk_path)
                        
                        with open(chunk_path, 'rb') as f:
                            chunk_data = f.read()
                        os.unlink(chunk_path)
                        
                        if first_sent:
                            # Send header on first chunk
                            tts_first = time.time() - tts_total_start
                            await websocket.send(json.dumps({
                                "type": "audio_info", 
                                "time": f"{tts_first:.2f}s",
                                "sampleRate": sr, 
                                "streaming": True,
                                "chunk": i + 1,
                                "total": chunk_count
                            }))
                            first_sent = False
                        else:
                            # Send chunk marker
                            await websocket.send(json.dumps({
                                "type": "audio_chunk",
                                "chunk": i + 1,
                                "total": chunk_count
                            }))
                        
                        await websocket.send(chunk_data)
                        
                        # Brief pause between chunks for natural rhythm
                        await asyncio.sleep(0.05)
                    
                    tts_time = time.time() - tts_total_start
                    await websocket.send(json.dumps({
                        "type": "audio_done", 
                        "time": f"{tts_time:.2f}s",
                        "chunks": chunk_count
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
    print(f"  🎙️ Voice: Fine-tuned Scarlett (Qwen3-TTS + Alice LoRA)")
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