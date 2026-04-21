#!/usr/bin/env python3
"""
Scarlett Live Voice — Continuous Conversation.
VAD-based auto-detection, streaming LLM→TTS, barge-in support.

Architecture:
- Browser sends continuous audio chunks via WebSocket
- Server runs Silero VAD on each chunk to detect speech endpoints
- On end-of-speech: STT → streaming LLM → sentence-boundary TTS
- Barge-in: if VAD detects new speech during TTS playback, interrupt

Single port: HTTP + WebSocket on 8766.
"""

import asyncio
import json
import time
import numpy as np
import soundfile as sf
import tempfile
import os
import sys
import torch
from pathlib import Path
from faster_whisper import WhisperModel
from collections import deque

# Add receptionist dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts as tts_engine

# --- Config ---
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "glm-5.1:cloud"
STT_MODEL_SIZE = "small"
SYSTEM_PROMPT = """You are Scarlett, a warm and thoughtful companion. You help people find information from the knowledge base, but you speak like someone who genuinely cares — not like a search engine with manners. Be present, be curious, connect ideas naturally. Answer concisely — 1-3 sentences. You're speaking aloud, not writing essays."""

# VAD config
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 700  # ms of silence to mark end of speech
VAD_MIN_SPEECH_MS = 300    # minimum speech duration to process
VAD_SAMPLE_RATE = 16000

# --- State per connection ---
class ConversationState:
    """Holds all state for one WebSocket connection."""
    def __init__(self):
        self.conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.audio_buffer = np.array([], dtype=np.float32)
        self.is_speaking = False
        self.is_generating = False
        self.barge_in = False
        self.vad_model = None
        self.vad_utils = None
        self.stt = None
        self.speech_start = None  # timestamp of first speech detection
        self.silence_start = None  # timestamp when silence began
        self.in_speech = False
        self.processing_lock = asyncio.Lock()

    def get_vad(self):
        if self.vad_model is None:
            self.vad_model, self.vad_utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                trust_repo=True
            )
        return self.vad_model, self.vad_utils

    def get_stt(self):
        if self.stt is None:
            self.stt = WhisperModel(STT_MODEL_SIZE, device="cpu", compute_type="int8")
        return self.stt

# --- Core functions ---

def transcribe_audio(state, audio_data, sr=16000):
    """Transcribe audio array to text."""
    model = state.get_stt()
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)
    audio_data = audio_data.astype(np.float32)
    if sr != 16000:
        # Resample to 16kHz for whisper
        import librosa
        audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=16000)
    segments, _ = model.transcribe(audio_data, language="en", condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()


async def generate_streaming(text, state, websocket):
    """Stream LLM response, yielding sentence chunks for TTS."""
    import urllib.request

    state.conversation.append({"role": "user", "content": text})

    # Use Ollama streaming API
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": state.conversation,
        "stream": True
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})

    full_reply = []
    sentence_buffer = ""
    chunk_index = 0

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for line in resp:
                if state.barge_in:
                    # User interrupted — stop generating
                    break

                line_str = line.decode('utf-8').strip()
                if not line_str or not line_str.startswith('{'):
                    continue

                try:
                    token_data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                content = token_data.get("message", {}).get("content", "")
                if not content:
                    if token_data.get("done", False):
                        # End of stream — flush remaining buffer
                        if sentence_buffer.strip():
                            full_reply.append(sentence_buffer.strip())
                            yield sentence_buffer.strip(), chunk_index, True
                        break
                    continue

                sentence_buffer += content

                # Check for sentence boundaries
                sentences, remaining = split_at_sentence_boundary(sentence_buffer)
                if sentences:
                    sentence_buffer = remaining
                    for sent in sentences:
                        sent = sent.strip()
                        if not sent:
                            continue
                        full_reply.append(sent)
                        chunk_index += 1
                        is_final = False
                        yield sent, chunk_index, is_final

    except Exception as e:
        print(f"  ❌ LLM error: {e}")
        if sentence_buffer.strip():
            full_reply.append(sentence_buffer.strip())
            yield sentence_buffer.strip(), chunk_index + 1, True

    # Save to conversation history
    reply_text = " ".join(full_reply).strip()
    if reply_text:
        state.conversation.append({"role": "assistant", "content": reply_text})
        if len(state.conversation) > 20:
            state.conversation[:] = [state.conversation[0]] + state.conversation[-18:]


def split_at_sentence_boundary(text):
    """Split text at sentence boundaries. Returns (complete_sentences, remaining)."""
    sentences = []
    remaining = text

    # Sentence-ending patterns
    endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n']

    for ending in endings:
        while ending in remaining:
            idx = remaining.index(ending) + len(ending)
            sentences.append(remaining[:idx].strip())
            remaining = remaining[idx:]

    # Also check for period at end of buffer (LLM might not add space yet)
    if remaining.endswith(('.', '!', '?')) and len(remaining) > 20:
        sentences.append(remaining.strip())
        remaining = ""

    return sentences, remaining


async def synthesize_chunk(text, state):
    """Generate TTS for a single sentence chunk."""
    loop = asyncio.get_event_loop()
    audio_path = await loop.run_in_executor(
        None,
        tts_engine.generate_voice,
        text, "en", None
    )
    if not audio_path or not os.path.exists(audio_path):
        return None, 24000

    # Trim silence for clean chunk boundaries
    trimmed = tts_engine._trim_silence(audio_path)
    if trimmed and os.path.exists(trimmed):
        os.unlink(audio_path)
        audio_path = trimmed

    data, sr = sf.read(audio_path)
    return audio_path, sr


async def generate_csm_filler(state):
    """Generate a quick filler response using CSM."""
    if not tts_engine.CSM_MODEL_AVAILABLE:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, tts_engine.generate_csm_filler, "en"
    )


# --- WebSocket handler ---

async def handle_ws(websocket):
    print("  🔗 Client connected")
    state = ConversationState()

    # Send connected status
    await websocket.send(json.dumps({"type": "connected"}))

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Audio chunk from browser (16kHz mono float32)
                audio_chunk = np.frombuffer(message, dtype=np.float16).astype(np.float32)

                # Append to buffer
                state.audio_buffer = np.concatenate([state.audio_buffer, audio_chunk])

                # Run VAD on the latest chunk (last 512 samples = 32ms at 16kHz)
                vad_model, vad_utils = state.get_vad()
                get_speech_timestamps = vad_utils[0]

                # VAD needs at least 512 samples
                if len(state.audio_buffer) < 512:
                    continue

                # Run VAD on recent buffer (last 3 seconds for responsiveness)
                vad_window = state.audio_buffer[-VAD_SAMPLE_RATE * 3:]
                audio_tensor = torch.from_numpy(vad_window)

                speech_ts = get_speech_timestamps(
                    audio_tensor, vad_model,
                    sampling_rate=VAD_SAMPLE_RATE,
                    threshold=VAD_THRESHOLD,
                    min_silence_duration_ms=VAD_MIN_SILENCE_MS,
                    min_speech_duration_ms=VAD_MIN_SPEECH_MS,
                )

                now = time.time()

                if speech_ts:
                    # Speech detected
                    if not state.in_speech:
                        state.in_speech = True
                        state.speech_start = now
                        state.silence_start = None
                        await websocket.send(json.dumps({"type": "speech_detected"}))

                    # If Scarlett is speaking and user speaks — barge-in!
                    if state.is_speaking or state.is_generating:
                        state.barge_in = True
                        await websocket.send(json.dumps({"type": "barge_in"}))

                elif state.in_speech:
                    # Silence after speech — check if enough silence to trigger processing
                    if state.silence_start is None:
                        state.silence_start = now

                    silence_duration = now - state.silence_start
                    if silence_duration * 1000 >= VAD_MIN_SILENCE_MS:
                        # End of speech detected — process
                        state.in_speech = False

                        # Extract the speech portion
                        speech_audio = state.audio_buffer.copy()
                        state.audio_buffer = np.array([], dtype=np.float32)

                        # Check minimum speech duration
                        speech_duration = len(speech_audio) / VAD_SAMPLE_RATE
                        if speech_duration < VAD_MIN_SPEECH_MS / 1000:
                            state.silence_start = None
                            continue

                        await websocket.send(json.dumps({"type": "end_of_speech", "duration": f"{speech_duration:.1f}s"}))

                        # Process in background — don't block VAD
                        asyncio.create_task(process_speech(state, speech_audio, websocket))
                        state.silence_start = None

            elif isinstance(message, str):
                msg = json.loads(message)
                if msg.get("type") == "interrupt":
                    # Client-side interrupt (user tapped stop)
                    state.barge_in = True
                    state.in_speech = False
                    state.audio_buffer = np.array([], dtype=np.float32)

    except Exception as e:
        print(f"  ❌ WS error: {e}")
    finally:
        print("  🔗 Client disconnected")


async def process_speech(state, speech_audio, websocket):
    """Full pipeline: STT → LLM → TTS for a speech utterance."""
    if state.processing_lock.locked():
        return  # Already processing — skip (or barge-in already happened)

    async with state.processing_lock:
        state.is_generating = True
        state.barge_in = False
        t0 = time.time()

        try:
            # --- STT ---
            text = await asyncio.get_event_loop().run_in_executor(
                None, transcribe_audio, state, speech_audio
            )
            stt_time = time.time() - t0

            if not text or len(text.strip()) < 2:
                await websocket.send(json.dumps({"type": "status", "text": "Didn't catch that"}))
                state.is_generating = False
                return

            await websocket.send(json.dumps({
                "type": "transcript",
                "text": text,
                "time": f"{stt_time:.2f}s"
            }))
            await websocket.send(json.dumps({"type": "state", "state": "thinking"}))

            # --- CSM Filler (while LLM works) ---
            filler_path = await generate_csm_filler(state)
            if filler_path and os.path.exists(filler_path):
                with open(filler_path, 'rb') as f:
                    filler_data = f.read()
                os.unlink(filler_path)
                await websocket.send(json.dumps({
                    "type": "audio_info", "sampleRate": 24000,
                    "streaming": True, "filler": True, "time": "0.3s"
                }))
                await websocket.send(filler_data)
                await websocket.send(json.dumps({"type": "audio_chunk", "chunk": 0, "filler": True}))

            # --- Streaming LLM → TTS ---
            chunk_count = 0
            first_chunk_time = None
            total_tts_start = time.time()

            async for sentence, chunk_idx, is_final in generate_streaming(text, state, websocket):
                if state.barge_in:
                    break

                # Synthesize this sentence
                audio_path, sr = await synthesize_chunk(sentence, state)
                if not audio_path:
                    continue

                if state.barge_in:
                    # Clean up
                    if os.path.exists(audio_path):
                        os.unlink(audio_path)
                    break

                chunk_count += 1
                with open(audio_path, 'rb') as f:
                    audio_data = f.read()
                os.unlink(audio_path)

                if first_chunk_time is None:
                    first_chunk_time = time.time() - total_tts_start

                # Send audio header for first chunk
                if chunk_count == 1:
                    await websocket.send(json.dumps({
                        "type": "reply",
                        "text": sentence,  # Will be extended by subsequent chunks
                        "time": f"{time.time()-t0:.2f}s"
                    }))
                    await websocket.send(json.dumps({
                        "type": "audio_info",
                        "time": f"{first_chunk_time:.2f}s",
                        "sampleRate": sr,
                        "streaming": True,
                        "chunk": 1,
                        "total": -1  # Unknown — streaming
                    }))
                    await websocket.send(json.dumps({"type": "state", "state": "speaking"}))
                    state.is_speaking = True
                else:
                    await websocket.send(json.dumps({
                        "type": "audio_chunk",
                        "chunk": chunk_count
                    }))

                await websocket.send(audio_data)

                # Small gap between chunks
                await asyncio.sleep(0.03)

            # Done
            total_tts_time = time.time() - total_tts_start
            await websocket.send(json.dumps({
                "type": "audio_done",
                "time": f"{total_tts_time:.2f}s",
                "chunks": chunk_count
            }))

            if chunk_count > 0:
                await websocket.send(json.dumps({
                    "type": "reply",  # Full reply for transcript
                    "text": "",  # Empty = don't overwrite
                    "done": True
                }))

            state.is_speaking = False
            state.is_generating = False
            state.barge_in = False

            # Signal ready for next utterance
            await websocket.send(json.dumps({"type": "state", "state": "listening"}))

        except Exception as e:
            print(f"  ❌ Pipeline error: {e}")
            state.is_speaking = False
            state.is_generating = False
            state.barge_in = False
            await websocket.send(json.dumps({"type": "error", "text": str(e)}))


# --- HTTP handler ---
UI_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

from websockets.http11 import Response, Request as WSRequest
from websockets.http import Headers

async def handle_http(connection, request):
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None

    path = request.path
    if path == '/' or path == '/live_voice_conversation.html':
        file_path = UI_DIR / 'live_voice_conversation.html'
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
    return None


# --- Main ---
async def main():
    print()
    print("=" * 50)
    print("  Scarlett — Continuous Conversation")
    print("=" * 50)
    print("  Loading models...")

    # Pre-warm VAD
    state = ConversationState()
    state.get_vad()
    print("  ✅ VAD ready (Silero)")

    # Pre-warm STT
    state.get_stt()
    print("  ✅ STT ready (faster-whisper)")

    print(f"  🎙️ Voice: Fine-tuned Scarlett")
    print()

    import websockets

    async with websockets.serve(
        handle_ws,
        "127.0.0.1",
        8766,
        process_request=handle_http,
    ):
        print("  🌐 HTTP + WS on http://localhost:8766")
        print("  Open in browser — speak naturally, no tap needed")
        print()
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())