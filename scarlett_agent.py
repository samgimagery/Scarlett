#!/usr/bin/env python3
"""
Scarlett — LiveKit Voice Agent

Real-time voice agent using LiveKit Agents framework.
Custom local plugins: faster-whisper (STT), Ollama (LLM), Qwen3-TTS fine-tuned (TTS).
All models run locally on M4 Max.

Usage:
  1. Start LiveKit server: livekit-server --dev
  2. Run this agent: python scarlett_agent.py dev
  3. Connect via web client (see live_voice_ui.html or LiveKit playground)

Environment variables:
  LIVEKIT_URL         — LiveKit server URL (default: ws://localhost:7880)
  LIVEKIT_API_KEY     — API key (default: devkey)
  LIVEKIT_API_SECRET  — API secret (default: secret)
  SCARLETT_AGENT_MODEL — Ollama model (default: glm-5.1:cloud)
"""

import os
import sys
import asyncio
import json
import logging
import time
import tempfile
from typing import AsyncIterator

# Add receptionist dir for tts module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf
import httpx
import requests as http_requests

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, APIConnectOptions
from livekit.agents.voice import Agent as VoiceAgent
from livekit.agents import stt, tts, llm
from livekit.agents.stt import SpeechEvent, SpeechEventType, SpeechData, RecognizeStream
from livekit.agents.tts import SynthesizedAudio, ChunkedStream, AudioEmitter
from livekit.agents.llm import ChatChunk, ChoiceDelta, ChatContext
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import aio
from livekit.rtc import AudioFrame
from livekit.plugins import silero

from config import RAG_SERVICE_URL, RESPONSE_LANGUAGE
from tts import generate_voice, get_default_voice, _trim_silence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.environ.get("SCARLETT_AGENT_MODEL", "glm-5.1:cloud")
SCARLETT_PROMPT = os.environ.get(
    "SCARLETT_PROMPT",
    "You are Scarlett, a warm and thoughtful companion. You help people find information from the knowledge base, "
    "but you speak like someone who genuinely cares — not like a search engine with manners. "
    "Be present, be curious, connect ideas naturally. Answer concisely — 1-3 sentences. "
    "You're speaking aloud, not writing essays. Keep responses natural and conversational."
)

SAMPLE_RATE = 24000
NUM_CHANNELS = 1


# ─────────────────────────────────────────────────────
# Local STT Plugin (faster-whisper)
# ─────────────────────────────────────────────────────

class LocalWhisperSTT(stt.STT):
    """Local faster-whisper STT plugin for LiveKit Agents."""

    def __init__(self, model_size: str = "small"):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False)
        )
        self._model_size = model_size
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper STT model ({self._model_size})...")
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            logger.info("Whisper STT model loaded")
        return self._model

    async def _recognize_impl(
        self,
        buffer: stt.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> SpeechEvent:
        """Recognize speech from an audio buffer."""
        model = self._ensure_model()

        # Convert AudioFrame to numpy float32 array
        if isinstance(buffer, AudioFrame):
            audio_data = np.frombuffer(buffer.data, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(buffer, np.ndarray):
            audio_data = buffer.astype(np.float32)
        else:
            audio_data = np.frombuffer(buffer, dtype=np.int16).astype(np.float32) / 32768.0

        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)
        audio_data = audio_data.astype(np.float32)

        lang_code = language if isinstance(language, str) else "en"
        lang_map = {"english": "en", "french": "fr"}
        whisper_lang = lang_map.get(lang_code, lang_code)

        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: model.transcribe(audio_data, language=whisper_lang, condition_on_previous_text=False)
        )

        text = " ".join(s.text for s in segments).strip()

        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                SpeechData(
                    language=stt.LanguageCode(whisper_lang.split("-")[0] if "-" in whisper_lang else whisper_lang),
                    text=text,
                    confidence=0.9,
                )
            ],
        )


# ─────────────────────────────────────────────────────
# Local TTS Plugin (fine-tuned Qwen3-TTS / Scarlett)
# ─────────────────────────────────────────────────────

class LocalScarlettTTS(tts.TTS):
    """Local fine-tuned Scarlett TTS plugin for LiveKit Agents."""

    def __init__(self):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False)
        )

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> ChunkedStream:
        """Create a ChunkedStream for the given text."""
        return ScarlettChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class ScarlettChunkedStream(ChunkedStream):
    """ChunkedStream that generates audio via fine-tuned Qwen3-TTS."""

    def __init__(self, *, tts: LocalScarlettTTS, input_text: str, conn_options: APIConnectOptions):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)

    async def _run(self, output_emitter: AudioEmitter) -> None:
        """Generate audio and push to emitter."""
        loop = asyncio.get_event_loop()

        # Generate audio file
        audio_path = await loop.run_in_executor(
            None,
            lambda: generate_voice(self.input_text, lang="en", voice=get_default_voice("en"))
        )

        if not audio_path or not os.path.exists(audio_path):
            logger.warning("TTS generation returned no audio, emitting silence")
            # Emit 100ms of silence so the pipeline doesn't stall
            output_emitter.initialize(
                request_id="",
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                mime_type="audio/wav",
            )
            output_emitter.push(b'\x00' * (SAMPLE_RATE * NUM_CHANNELS * 2 // 10))  # 100ms silence
            output_emitter.flush()
            return

        # Read and trim silence
        def _read_and_trim():
            _trim_silence(audio_path)
            data, sr = sf.read(audio_path, dtype='int16')
            try:
                os.remove(audio_path)
                parent = os.path.dirname(audio_path)
                if os.path.isdir(parent) and parent.startswith(os.path.expanduser("~/Media/voices/tmp")):
                    os.rmdir(parent)
            except:
                pass
            return data, sr

        data, sr = await loop.run_in_executor(None, _read_and_trim)

        # Initialize emitter and push audio
        output_emitter.initialize(
            request_id="",
            sample_rate=sr,
            num_channels=1,
            mime_type="audio/wav",
        )
        output_emitter.push(data.tobytes())
        output_emitter.flush()


# ─────────────────────────────────────────────────────
# Local LLM Plugin (Ollama)
# ─────────────────────────────────────────────────────

class LocalOllamaLLM(llm.LLM):
    """Local Ollama LLM plugin for LiveKit Agents."""

    def __init__(self, model: str = OLLAMA_MODEL):
        super().__init__()
        self._model = model

    async def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = APIConnectOptions(),
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        **kwargs,
    ) -> llm.ChatChunkStream:
        """Chat completion via Ollama with streaming."""

        # Convert ChatContext messages to Ollama format
        ollama_messages = []
        for msg in chat_ctx.messages:
            role = str(msg.role) if hasattr(msg, 'role') else 'user'
            content = msg.content if isinstance(msg.content, str) else str(msg.content) if hasattr(msg, 'content') else ''
            if content:
                ollama_messages.append({"role": role, "content": content})

        payload = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": True,
        }

        loop = asyncio.get_event_loop()

        async def _stream():
            resp = await loop.run_in_executor(
                None,
                lambda: http_requests.post(OLLAMA_URL, json=payload, timeout=60, stream=True)
            )

            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("done", False):
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield ChatChunk(
                            id=data.get("created_at", ""),
                            delta=ChoiceDelta(content=content),
                        )

        return llm.ChatChunkStream(stream=_stream(), llm=self)


# ─────────────────────────────────────────────────────
# Scarlett Agent
# ─────────────────────────────────────────────────────

class ScarlettAgent(VoiceAgent):
    """Scarlett voice agent."""

    def __init__(self):
        super().__init__(
            instructions=SCARLETT_PROMPT,
        )


async def entrypoint(ctx: JobContext):
    """LiveKit agent entry point."""
    logger.info(f"Scarlett agent connecting to room: {ctx.room.name}")

    # Create local model instances
    local_stt = LocalWhisperSTT(model_size="small")
    local_tts = LocalScarlettTTS()
    local_llm = LocalOllamaLLM()

    # StreamAdapter wraps non-streaming STT/TTS for LiveKit's pipeline
    stt_adapter = stt.StreamAdapter(stt=local_stt, vad=silero.VAD.load())
    tts_adapter = tts.StreamAdapter(tts=local_tts)

    session = AgentSession(
        stt=stt_adapter,
        llm=local_llm,
        tts=tts_adapter,
        vad=silero.VAD.load(),
        allow_interruptions=True,
        min_endpointing_delay=0.5,
    )

    await session.start(agent=ScarlettAgent(), room=ctx.room)

    logger.info(f"Scarlett agent started in room: {ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint),
    )