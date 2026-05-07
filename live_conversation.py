#!/usr/bin/env python3
"""
Scarlett Live Conversation — continuous voice flow.

Architecture:
- Browser streams mic audio continuously via WebSocket
- Silero VAD detects speech start/end in real-time
- On speech end: faster-whisper STT → streaming Ollama LLM → CSM TTS
- Audio chunks stream back to browser as generated
- Barge-in: VAD detects new speech → stop current TTS → process new input

TTS pipeline:
- CSM (Sesame CSM 1B) is the primary TTS engine for all speech
- Short filler ("Hmm.") via /generate, full sentences via /generate_full
- Sentence-level streaming: each LLM sentence is generated + played as it arrives
- Kokoro is the fallback if the CSM server is down

No tap-to-talk. Mic stays on. Scarlett listens, thinks, speaks — continuously.
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
from pathlib import Path
from websockets.http11 import Response
from websockets.http import Headers

# Add receptionist dir to path for tts module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# RAG / TTS imports
import mcp_client
from prompt import build_context, build_prompt
import tts as tts_engine

# --- Config ---
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3-coder:30b"
CSM_SERVER_URL = "http://127.0.0.1:8766/generate"
CSM_FULL_URL = "http://127.0.0.1:8766/generate_full"
STT_MODEL_SIZE = "small"
LIVE_LANGUAGE = "fr"
RAG_ASK_URL = "http://127.0.0.1:8000/ask"
VOICE_ASSETS_ROOT = Path(__file__).resolve().parent / "scarlett_core" / "voice" / "assets"
PREFILLER_MANIFEST = Path("/Users/samg/Media/voices/french_sources/xUiKafk2gWM/qwen3_tts_fr_lora_overnight_20260504-215150/prefiller_bank_req112_v2_p0_speed075/manifest.json")
SYSTEM_PROMPT = """Tu es Scarlett, la réception virtuelle chaleureuse de l’Académie de Massage Scientifique. Réponds en français canadien naturel, clairement et brièvement. Tu aides avec les formations, prix, campus, inscriptions et prochaines étapes. Tu parles à voix haute: 1 à 3 phrases, pas de longs paragraphes."""

# VAD settings
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 700
VAD_MIN_SPEECH_MS = 300
VAD_SAMPLE_RATE = 16000


# --- Cached FR-CA prefiller bank ---
_prefillers = None

def load_prefillers():
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
    bank = load_prefillers()["by_id"]
    if service_state == "receipt":
        return bank.get("p0_receipt_003") or bank.get("p0_receipt_002")
    if service_state == "lookup" and retrieval_running:
        return bank.get("p0_lookup_004") or bank.get("p0_lookup_001")
    if service_state == "repair":
        return bank.get("p0_repair_003")
    if service_state == "answer_bridge" and answer_ready:
        return bank.get("p0_answer_bridge_001")
    return None

async def send_cached_prefiller(websocket, service_state, **state):
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
        "filler": True,
        "prefiller_id": item.get("id"),
    }))
    print(f"  🎵 Cached prefiller: {item.get('id')} — {item.get('text')}", flush=True)
    return True


def resolve_voice_asset(voice):
    """Return the ready cached service-tile WAV path for a /ask voice block."""
    if not voice or not voice.get("recording_ready"):
        return None
    asset_id = voice.get("asset_id")
    if not asset_id:
        return None
    path = (VOICE_ASSETS_ROOT / asset_id).resolve()
    try:
        path.relative_to(VOICE_ASSETS_ROOT.resolve())
    except ValueError:
        return None
    if path.exists() and path.stat().st_size > 1000:
        return path
    return None


async def send_service_tile_audio(websocket, voice, *, elapsed_sec=None):
    """Send the ready cached service-tile WAV before generated answer TTS."""
    wav_path = resolve_voice_asset(voice)
    if not wav_path:
        return False
    await websocket.send(json.dumps({
        "type": "audio_info",
        "time": f"{elapsed_sec:.2f}s" if elapsed_sec is not None else "cached",
        "sampleRate": 24000,
        "streaming": True,
        "service_tile": True,
        "asset_id": voice.get("asset_id"),
        "tile_id": voice.get("tile_id"),
        "intent": voice.get("intent"),
        "line": voice.get("line"),
    }))
    with open(wav_path, "rb") as f:
        await websocket.send(f.read())
    await websocket.send(json.dumps({
        "type": "audio_chunk",
        "service_tile": True,
        "asset_id": voice.get("asset_id"),
        "intent": voice.get("intent"),
    }))
    print(f"  🎙️ Service tile asset: {voice.get('asset_id')} — {voice.get('line')}", flush=True)
    return True

def split_sentences(text):
    return [s.strip() for s in tts_engine._split_sentences(text) if s.strip()] or [text.strip()]


def split_voice_chunks(text, max_chars=155):
    """Split answer text into small speakable chunks for fast first audio."""
    import re
    base = split_sentences(text or "")
    chunks = []
    for sentence in base:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        parts = []
        current = ""
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


def generate_qwen3_wav_bytes(text, speed=0.65):
    path = tts_engine.generate_voice(text, lang=LIVE_LANGUAGE, speed=speed)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass

def ask_grounded_receptionist(question):
    payload = json.dumps({"question": question, "language": LIVE_LANGUAGE}).encode()
    req = urllib.request.Request(RAG_ASK_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data

# --- Models (lazy-loaded) ---
_stt = None
_vad_model = None
_vad_utils = None
_conversation = [{"role": "system", "content": SYSTEM_PROMPT}]


def get_stt():
    global _stt
    if _stt is None:
        from faster_whisper import WhisperModel
        _stt = WhisperModel(STT_MODEL_SIZE, device="cpu", compute_type="int8")
    return _stt


def get_vad():
    global _vad_model, _vad_utils
    if _vad_model is None:
        import torch
        _vad_model, _vad_utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            trust_repo=True
        )
    return _vad_model, _vad_utils


# --- VAD Processing ---
class VADProcessor:
    def __init__(self):
        self.model, self.utils = get_vad()
        self.VADIterator = self.utils[3]
        self.iterator = self.VADIterator(
            self.model,
            threshold=VAD_THRESHOLD,
            sampling_rate=VAD_SAMPLE_RATE,
            min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        )
        self.buffer = np.array([], dtype=np.float32)
        self.is_speech = False

    def process_chunk(self, audio_chunk):
        self.buffer = np.concatenate([self.buffer, audio_chunk])
        result = self.iterator(audio_chunk, return_seconds=False)
        events = []
        if result and 'start' in result and not self.is_speech:
            self.is_speech = True
            events.append('speech_start')
        if result and 'end' in result and self.is_speech:
            self.is_speech = False
            events.append('speech_end')
        return events

    def get_speech_audio(self):
        audio = self.buffer.copy()
        self.buffer = np.array([], dtype=np.float32)
        return audio

    def reset(self):
        self.buffer = np.array([], dtype=np.float32)
        self.is_speech = False
        self.iterator.reset_states()


# --- STT ---
def transcribe(audio_data, sample_rate=16000):
    model = get_stt()
    if isinstance(audio_data, np.ndarray):
        data = audio_data.astype(np.float32)
    else:
        data = audio_data
    segments, _ = model.transcribe(data, language=LIVE_LANGUAGE, condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()


# --- Streaming LLM ---
async def stream_llm(text, on_sentence=None):
    """Stream LLM response. Calls on_sentence(sentence) for each complete sentence."""
    import urllib.request

    _conversation.append({"role": "user", "content": text})

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": _conversation,
        "stream": True
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )

    full_reply = []
    sentence_buffer = ""
    thinking = True  # Skip thinking tokens

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                content = data.get("message", {}).get("content", "")
                think = data.get("message", {}).get("thinking", "")

                # Skip thinking phase — only use content
                if think:
                    continue

                if content:
                    thinking = False
                    full_reply.append(content)
                    sentence_buffer += content

                    # Check sentence boundary
                    if content and content[-1] in '.!?' and len(sentence_buffer.strip()) > 10:
                        abbrevs = ['Mr.', 'Mrs.', 'Dr.', 'etc.', 'i.e.', 'e.g.']
                        is_abbrev = any(sentence_buffer.rstrip().endswith(a) for a in abbrevs)
                        if not is_abbrev:
                            if on_sentence and sentence_buffer.strip():
                                await on_sentence(sentence_buffer.strip())
                            sentence_buffer = ""

                if data.get("done"):
                    if on_sentence and sentence_buffer.strip():
                        await on_sentence(sentence_buffer.strip())
                    break
    except Exception as e:
        print(f"  ❌ LLM error: {e}")

    reply = "".join(full_reply)
    _conversation.append({"role": "assistant", "content": reply})
    if len(_conversation) > 20:
        _conversation[:] = [_conversation[0]] + _conversation[-18:]
    return reply


# --- TTS ---
async def generate_csm_audio(text, is_filler=False, max_audio_ms=None):
    """Generate audio via CSM server.

    Uses /generate for short filler phrases (max 5s audio),
    /generate_full for longer LLM sentences (max 20s audio).
    Returns raw WAV bytes, or None on failure.
    """
    try:
        import urllib.request
        if is_filler:
            url = CSM_SERVER_URL
            if max_audio_ms is None:
                max_audio_ms = 5000
        else:
            url = CSM_FULL_URL
            if max_audio_ms is None:
                max_audio_ms = 20000

        req = urllib.request.Request(
            url,
            data=json.dumps({"text": text, "max_audio_length_ms": max_audio_ms}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=15)
        wav_data = resp.read()
        gen_time = float(resp.headers.get("X-Gen-Time", "0"))
        audio_dur = float(resp.headers.get("X-Audio-Duration", "0"))
        rtf = float(resp.headers.get("X-RTF", "0"))
        label = "FILLER" if is_filler else "FULL"
        print(f"  🎵 CSM [{label}]: '{text[:40]}' gen={gen_time:.2f}s audio={audio_dur:.2f}s RTF={rtf:.2f}")
        return wav_data
    except Exception as e:
        print(f"  ❌ CSM error: {e}")
        return None


# --- WebSocket handler ---
tts_cancel = False
processing = False


async def handle_ws(websocket):
    global tts_cancel, processing

    print("  🔗 Client connected")
    vad = VADProcessor()
    speech_audio = np.array([], dtype=np.float32)
    is_speaking = False
    chunk_count = 0
    total_audio = 0

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Audio chunk from browser (16-bit PCM at 16kHz)
                try:
                    audio_int16 = np.frombuffer(message, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0
                except Exception:
                    continue

                chunk_count += 1
                total_audio += len(audio_float32)
                if chunk_count == 1:
                    print(f"  🎤 First audio chunk: {len(audio_int16)} samples")
                if chunk_count % 50 == 0:
                    print(f"  🎤 {chunk_count} chunks, {total_audio/VAD_SAMPLE_RATE:.1f}s audio, speaking={is_speaking}")

                # Silero VAD requires EXACTLY 512 samples at 16kHz
                # Browser sends 2048 samples per chunk (4x512)
                vad_buffer = getattr(websocket, '_vad_buf', np.array([], dtype=np.float32))
                vad_buffer = np.concatenate([vad_buffer, audio_float32])

                while len(vad_buffer) >= 512:
                    chunk = vad_buffer[:512]
                    vad_buffer = vad_buffer[512:]

                    events = vad.process_chunk(chunk)
                    for event in events:
                        if event == 'speech_start':
                            is_speaking = True
                            speech_audio = np.array([], dtype=np.float32)
                            await websocket.send(json.dumps({"type": "state", "state": "hearing"}))
                            print("  👤 Speech started")

                            # Barge-in
                            if processing:
                                tts_cancel = True
                                print("  🛑 Barge-in!")
                                await websocket.send(json.dumps({"type": "barge_in"}))

                        elif event == 'speech_end':
                            is_speaking = False
                            # Add remaining audio from this chunk
                            speech_audio = np.concatenate([speech_audio, audio_float32])
                            print(f"  👤 Speech ended ({len(speech_audio)/VAD_SAMPLE_RATE:.1f}s)")

                            if not processing and len(speech_audio) > VAD_SAMPLE_RATE * 0.3:
                                processing = True
                                asyncio.create_task(
                                    process_utterance(websocket, speech_audio.copy(), vad)
                                )
                                speech_audio = np.array([], dtype=np.float32)

                websocket._vad_buf = vad_buffer

                # Accumulate speech audio
                if is_speaking:
                    speech_audio = np.concatenate([speech_audio, audio_float32])

    except Exception as e:
        print(f"  ❌ WS error: {e}")
    finally:
        print("  🔗 Client disconnected")


async def process_utterance(websocket, audio_data, vad):
    global tts_cancel, processing

    try:
        # STT
        t0 = time.time()
        transcript = await asyncio.to_thread(transcribe, audio_data)
        stt_time = time.time() - t0

        if not transcript or len(transcript.strip()) < 2:
            await websocket.send(json.dumps({"type": "state", "state": "listening"}))
            return

        await websocket.send(json.dumps({
            "type": "transcript", "text": transcript, "time": f"{stt_time:.2f}s"
        }))
        print(f"  📝 STT: '{transcript}' ({stt_time:.2f}s)")

        # Cached-first voice layer.
        # Receipt does not imply work. Lookup is only spoken if the real
        # RAG/service request is slow, avoiding stacked filler when answers are instant.
        tts_cancel = False
        await send_cached_prefiller(websocket, "receipt")

        # Grounded receptionist answer via the existing RAG/service API.
        rag_t0 = time.time()
        rag_task = asyncio.create_task(asyncio.to_thread(ask_grounded_receptionist, transcript))
        lookup_sent = False
        try:
            rag_data = await asyncio.wait_for(asyncio.shield(rag_task), timeout=0.70)
        except asyncio.TimeoutError:
            lookup_sent = await send_cached_prefiller(websocket, "lookup", retrieval_running=True)
            try:
                rag_data = await rag_task
            except Exception as e:
                print(f"  ❌ RAG ask error: {e}")
                rag_data = {"answer": "Je suis désolée, je n’arrive pas à vérifier l’information en ce moment.", "sources": []}
        except Exception as e:
            print(f"  ❌ RAG ask error: {e}")
            rag_data = {"answer": "Je suis désolée, je n’arrive pas à vérifier l’information en ce moment.", "sources": []}

        reply = (rag_data.get("answer") or "").strip() or "Je ne veux pas deviner. Je préfère vérifier avant de vous répondre."
        sources = rag_data.get("sources") or []
        voice = rag_data.get("voice") or {}
        rag_elapsed = time.time() - rag_t0
        print(f"  🔍 RAG ask: {len(sources)} sources ({rag_elapsed:.2f}s)")
        await websocket.send(json.dumps({
            "type": "nodes",
            "results": [{"path": str(src), "score": 1, "snippet": ""} for src in sources[:6]]
        }))
        service_tile_sent = await send_service_tile_audio(websocket, voice, elapsed_sec=rag_elapsed)
        await websocket.send(json.dumps({
            "type": "reply",
            "text": reply,
            "voice": {
                "intent": voice.get("intent"),
                "asset_id": voice.get("asset_id"),
                "recording_ready": voice.get("recording_ready"),
                "service_tile_sent": service_tile_sent,
            },
        }))

        chunks = split_voice_chunks(reply)
        if service_tile_sent and voice.get("line") and reply.strip() == str(voice.get("line")).strip():
            chunks = []
        if chunks and not service_tile_sent and (not lookup_sent or len(reply) > 90):
            await send_cached_prefiller(websocket, "answer_bridge", answer_ready=True)

        # Generate grounded answer chunks with the approved FR-CA Qwen3 LoRA voice.
        total_tts_start = time.time()
        first_audio = True
        sent_chunks = 0
        for i, sentence in enumerate(chunks, start=1):
            if tts_cancel:
                break
            wav_data = await asyncio.to_thread(generate_qwen3_wav_bytes, sentence, 0.65)
            if not wav_data or tts_cancel:
                continue
            if first_audio:
                first_audio = False
                await websocket.send(json.dumps({
                    "type": "audio_info",
                    "time": f"{time.time()-total_tts_start:.2f}s",
                    "sampleRate": 24000,
                    "streaming": len(chunks) > 1,
                    "chunk": i,
                    "total": len(chunks),
                }))
            await websocket.send(wav_data)
            await websocket.send(json.dumps({"type": "audio_chunk", "text": sentence, "chunk": i, "total": len(chunks)}))
            sent_chunks += 1
            print(f"  🔊 Sent Qwen3 chunk {i}/{len(chunks)}: {sentence[:70]}")
            await asyncio.sleep(0.04)

        await websocket.send(json.dumps({"type": "audio_done", "time": f"{time.time()-total_tts_start:.2f}s", "chunks": sent_chunks, "planned_chunks": len(chunks)}))
        print(f"  ✅ Complete: STT={stt_time:.2f}s, answer_tts={time.time()-total_tts_start:.2f}s")

    except Exception as e:
        print(f"  ❌ Process error: {e}")
    finally:
        processing = False
        tts_cancel = False
        vad.reset()
        await websocket.send(json.dumps({"type": "state", "state": "listening"}))

# --- HTTP server (static files, separate thread) ---
UI_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

async def handle_http(connection, request):
    """Serve static files for non-WebSocket HTTP requests."""
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None  # Let websockets handle it

    path = request.path
    if path == '/' or path == '/live_voice_conversation.html':
        file_path = UI_DIR / 'live_voice_conversation.html'
    else:
        file_path = UI_DIR / path.lstrip('/')

    if file_path.exists() and file_path.is_file():
        body = file_path.read_bytes()
        content_types = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css'}
        content_type = content_types.get(file_path.suffix, 'application/octet-stream')
        return Response(
            200, 'OK',
            Headers([('Content-Type', content_type), ('Content-Length', str(len(body)))]),
            body=body,
        )
    return None  # 404 will be handled by websockets


# --- Main ---
async def main():
    print()
    print("=" * 50)
    print("  Scarlett Live Conversation")
    print("=" * 50)
    print("  Loading models...")
    get_stt()
    get_vad()
    print("  ✅ STT + VAD ready")
    load_prefillers()
    print("  🎙️ Voice: FR-CA Qwen3 LoRA + cached REQ-112 prefillers")

    # Single port — both HTTP and WS on 8765
    import websockets

    async with websockets.serve(
        handle_ws,
        "127.0.0.1",
        8765,
        process_request=handle_http,
        ping_interval=20,
        ping_timeout=60,
        close_timeout=5,
    ):
        print("  🌐 HTTP + WS on http://localhost:8765")
        print("  🔗 Tailscale: https://samgs-mac-studio.tail3e92a8.ts.net/")
        print(flush=True)
        await asyncio.Future()

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())