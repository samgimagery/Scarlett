#!/usr/bin/env python3
"""
Scarlett Live Conversation — continuous voice flow.

Architecture:
- Browser streams mic audio continuously via WebSocket
- Silero VAD detects speech start/end in real-time
- On speech end: faster-whisper STT → streaming Ollama LLM → CSM streaming TTS
- Audio chunks stream back to browser as generated
- Barge-in: VAD detects new speech → stop current TTS → process new input

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
from pathlib import Path
from websockets.http11 import Response
from websockets.http import Headers

# Add receptionist dir to path for tts module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Config ---
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "glm-5.1:cloud"
CSM_SERVER_URL = "http://127.0.0.1:8766/generate"
STT_MODEL_SIZE = "small"
SYSTEM_PROMPT = """You are Scarlett, a warm and thoughtful companion. You help people find information from the knowledge base, but you speak like someone who genuinely cares — not like a search engine with manners. Be present, be curious, connect ideas naturally. Answer concisely — 1-3 sentences. You're speaking aloud, not writing essays."""

# VAD settings
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 700
VAD_MIN_SPEECH_MS = 300
VAD_SAMPLE_RATE = 16000

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
    segments, _ = model.transcribe(data, language="en", condition_on_previous_text=False)
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
async def generate_csm_sentence(text):
    """Generate audio via CSM filler server."""
    try:
        import urllib.request
        req = urllib.request.Request(
            CSM_SERVER_URL,
            data=json.dumps({"text": text, "max_audio_length_ms": 3000}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=15)
        wav_data = resp.read()
        gen_time = float(resp.headers.get("X-Gen-Time", "0"))
        audio_dur = float(resp.headers.get("X-Audio-Duration", "0"))
        print(f"  🎵 CSM: '{text[:40]}' gen={gen_time:.2f}s audio={audio_dur:.2f}s")
        return wav_data
    except Exception as e:
        print(f"  ❌ CSM error: {e}")
        return None


async def generate_qwen3_sentence(text, lang="en"):
    """Generate audio via Qwen3-TTS Scarlett."""
    import tts as tts_engine
    try:
        path = await asyncio.to_thread(
            tts_engine.generate_voice, text, lang, None, 0.9
        )
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            os.unlink(path)
            return data
    except Exception as e:
        print(f"  ❌ Qwen3-TTS error: {e}")
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

        # CSM Filler (instant) — keep short (3s max audio)
        filler_task = asyncio.create_task(generate_csm_sentence("Hmm."))
        tts_cancel = False

        # Send filler
        try:
            filler_data = await asyncio.wait_for(filler_task, timeout=5.0)
            if filler_data and not tts_cancel:
                await websocket.send(json.dumps({
                    "type": "audio_info", "time": f"{time.time()-t0:.2f}s",
                    "sampleRate": 24000, "streaming": True, "filler": True
                }))
                await websocket.send(filler_data)
                print(f"  🎵 Filler sent ({time.time()-t0:.2f}s, {len(filler_data)} bytes)")
        except asyncio.TimeoutError:
            print(f"  ⏰ Filler timeout ({time.time()-t0:.2f}s)")
        except Exception as e:
            print(f"  ❌ Filler error: {e}")

        # Streaming LLM → TTS
        audio_queue = asyncio.Queue()
        first_audio = True
        total_tts_start = time.time()

        async def on_llm_sentence(sentence):
            if tts_cancel:
                return
            audio_data = await generate_qwen3_sentence(sentence, "en")
            if audio_data and not tts_cancel:
                await audio_queue.put({"audio": audio_data, "text": sentence})

        llm_task = asyncio.create_task(stream_llm(transcript, on_sentence=on_llm_sentence))

        # Stream TTS chunks
        llm_done = False
        while not llm_done or not audio_queue.empty():
            if tts_cancel:
                break
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                if llm_task.done():
                    llm_done = True
                continue

            if first_audio:
                first_audio = False
                await websocket.send(json.dumps({
                    "type": "audio_info",
                    "time": f"{time.time()-total_tts_start:.2f}s",
                    "sampleRate": 24000, "streaming": True
                }))

            await websocket.send(chunk["audio"])
            print(f"  🔊 Sent audio chunk: {len(chunk['audio'])} bytes, text: '{chunk['text'][:50]}'")
            await websocket.send(json.dumps({
                "type": "audio_chunk", "text": chunk["text"]
            }))

            if llm_task.done():
                llm_done = True

        try:
            reply = await asyncio.wait_for(llm_task, timeout=10.0)
            await websocket.send(json.dumps({"type": "reply", "text": reply}))
        except asyncio.TimeoutError:
            pass

        await websocket.send(json.dumps({"type": "audio_done", "time": f"{time.time()-total_tts_start:.2f}s"}))
        print(f"  ✅ Audio complete ({time.time()-total_tts_start:.2f}s)")
        print(f"  ✅ Complete: STT={stt_time:.2f}s")

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