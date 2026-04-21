#!/usr/bin/env python3
"""
Scarlett Live Voice — Real-time conversational voice assistant prototype.

Architecture:
  Mic → VAD → STT (faster-whisper small, int8) → LLM (Ollama) → TTS (Kokoro via mlx-audio) → Speaker
  Barge-in: VAD interrupts TTS playback when user speaks again.

Benchmarks on M4 Max (2026-04-19):
  - faster-whisper small (int8, CPU): ~0.7s for 5s audio, 0.5s load
  - Kokoro TTS: 0.04s ("Yes."), 0.11s (longer sentence), 1.2s cold
  - Ollama glm-5.1:cloud: ~3s non-streaming, ~3.8s first-token streaming
  - mlx-whisper tiny: 0.03s warm (but less accurate)
  
  Total estimated latency: 4-5s (dominated by LLM)
  With sentence-boundary streaming: could cut to 1-2s perceived

Based on research in: Research/Live Voice Assistant.md
"""

import json
import queue
import signal
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

# --- Configuration ---
SAMPLE_RATE = 16000          # Whisper expects 16kHz
CHANNELS = 1
DTYPE = np.float32
SILENCE_THRESHOLD = 0.015   # RMS threshold for silence detection
SILENCE_CHUNKS = 8           # Silent chunks before end-of-speech
MAX_RECORDING_S = 30         # Max recording length
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "glm-5.1:cloud"

# TTS config — Kokoro for prototype, fine-tuned Scarlett voice later
TTS_MODEL_ID = "mlx-community/Kokoro-82M-bf16"
TTS_VOICE = "af_bella"
TTS_LANG = "a"  # American English

# STT config
STT_MODEL_SIZE = "small"     # faster-whisper model size
STT_DEVICE = "cpu"           # Use CPU (sufficient on M4 Max)
STT_COMPUTE = "int8"         # Quantization for speed
STT_LANGUAGE = "en"

# Scarlett persona — grounded RAG prompt
from prompt import get_system_prompt, get_refusal, build_context, build_prompt
from mcp_client import search as vault_search
from config import VAULT_PATH, SIMILARITY_THRESHOLD, MAX_CONTEXT_NOTES

SYSTEM_PROMPT = get_system_prompt("en")

# --- Globals ---
audio_queue = queue.Queue()
interrupt_event = threading.Event()
is_speaking = False
speak_lock = threading.Lock()
conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

# --- Model Singletons ---
_stt_model = None
_tts_model = None


def get_stt_model():
    """Lazy-load STT model."""
    global _stt_model
    if _stt_model is None:
        from faster_whisper import WhisperModel
        print("  ⏳ Loading STT model (faster-whisper small)...")
        _stt_model = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=STT_COMPUTE)
        print("  ✅ STT model ready")
    return _stt_model


def get_tts_model():
    """Lazy-load TTS model."""
    global _tts_model
    if _tts_model is None:
        from mlx_audio.tts.generate import load_model
        print("  ⏳ Loading TTS model (Kokoro-82M)...")
        _tts_model = load_model(TTS_MODEL_ID)
        print("  ✅ TTS model ready")
    return _tts_model


# --- VAD (Voice Activity Detection) using energy ---
def is_speech(audio_data: np.ndarray, threshold: float = SILENCE_THRESHOLD) -> bool:
    """Simple energy-based VAD."""
    rms = np.sqrt(np.mean(audio_data ** 2))
    return rms > threshold


# --- STT ---
def transcribe(audio_data: np.ndarray) -> str:
    """Transcribe audio using faster-whisper."""
    model = get_stt_model()
    segments, info = model.transcribe(audio_data, language=STT_LANGUAGE, condition_on_previous_text=False)
    text = " ".join([s.text for s in segments]).strip()
    return text


# --- LLM ---
def generate_response(messages: list) -> str:
    """Generate response from Ollama."""
    import urllib.request
    
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }).encode()
    
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"  [LLM Error] {e}")
        return "I'm having trouble thinking right now. Could you try again?"


# --- TTS ---
def synthesize_to_file(text: str, output_path: str = "/tmp/scarlett_voice.wav") -> str | None:
    """Synthesize speech using Kokoro via mlx-audio."""
    if not text:
        return None
    
    try:
        model = get_tts_model()
        audio_chunks = []
        sample_rate = 24000  # Kokoro default
        
        for result in model.generate(text, voice=TTS_VOICE, lang_code=TTS_LANG):
            if hasattr(result, 'audio') and result.audio is not None:
                audio_chunks.append(np.array(result.audio))
        
        if not audio_chunks:
            return None
        
        # Concatenate and save
        audio_data = np.concatenate(audio_chunks)
        
        # Handle sample rate
        if hasattr(result, 'sample_rate'):
            sample_rate = result.sample_rate
        
        # Convert to int16 WAV
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        with wave.open(output_path, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())
        
        return output_path
    except Exception as e:
        print(f"  [TTS Error] {e}")
        import traceback
        traceback.print_exc()
        return None


def play_audio(file_path: str):
    """Play audio file, interruptible via interrupt_event."""
    global is_speaking
    
    try:
        import soundfile as sf
        data, sr = sf.read(file_path, dtype='float32')
    except Exception:
        with wave.open(file_path, 'r') as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            data = np.frombuffer(wf.readframes(n_frames), dtype=np.int16).astype(np.float32) / 32767.0
    
    if len(data.shape) > 1:
        data = data[:, 0]
    
    chunk_size = int(sr * 0.03)  # 30ms chunks for responsive interrupt
    
    with speak_lock:
        is_speaking = True
    
    try:
        with sd.OutputStream(samplerate=sr, channels=1, dtype='float32') as stream:
            for i in range(0, len(data), chunk_size):
                if interrupt_event.is_set():
                    print("  ⏹ Interrupted")
                    break
                chunk = data[i:i + chunk_size]
                if len(chunk) > 0:
                    stream.write(chunk.reshape(-1, 1))
    finally:
        with speak_lock:
            is_speaking = False


# --- Audio Recording ---
def record_until_silence() -> np.ndarray | None:
    """Record audio until silence is detected after speech."""
    print("  🎤 Listening...")
    
    chunk_samples = int(SAMPLE_RATE * 0.3)  # 300ms chunks
    max_chunks = int(MAX_RECORDING_S / 0.3)
    chunks = []
    silent_count = 0
    speech_detected = False
    
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,
                        blocksize=chunk_samples) as stream:
        for _ in range(max_chunks):
            data, overflowed = stream.read(chunk_samples)
            mono = data.flatten()
            chunks.append(mono)
            
            if is_speech(mono):
                silent_count = 0
                speech_detected = True
            else:
                silent_count += 1
            
            # End after sustained silence following speech
            if speech_detected and silent_count >= SILENCE_CHUNKS:
                # Remove trailing silence
                while silent_count > 0 and len(chunks) > 1:
                    chunks.pop()
                    silent_count -= 1
                break
    
    if not chunks:
        return None
    
    audio = np.concatenate(chunks)
    
    # Verify we captured actual speech
    if not speech_detected or np.sqrt(np.mean(audio ** 2)) < SILENCE_THRESHOLD * 0.5:
        return None
    
    return audio


# --- Main Loop ---
def main():
    print()
    print("=" * 55)
    print("  Scarlett Live Voice — Prototype v1")
    print("=" * 55)
    print(f"  STT: faster-whisper {STT_MODEL_SIZE} ({STT_COMPUTE})")
    print(f"  LLM: {OLLAMA_MODEL} via Ollama")
    print(f"  TTS: Kokoro-82M ({TTS_VOICE})")
    print()
    print("  Say something! (Ctrl+C to quit)")
    print("=" * 55)
    
    # Pre-load models
    print()
    get_stt_model()
    get_tts_model()
    print()
    print("  🟢 Ready! Speak into the microphone.")
    print()
    
    try:
        while True:
            # Record
            audio = record_until_silence()
            if audio is None:
                continue
            
            # Interrupt any ongoing speech
            interrupt_event.set()
            time.sleep(0.05)
            interrupt_event.clear()
            
            # STT
            print("  📝 Transcribing...")
            t0 = time.time()
            text = transcribe(audio)
            stt_time = time.time() - t0
            
            if not text or len(text.strip()) < 2:
                print("  (no speech detected, try again)")
                continue
            
            print(f"  👤 You: {text} ({stt_time:.2f}s)")
            
            # RAG: Search vault for context
            print("  🔍 Searching vault...")
            t_rag = time.time()
            search_results = vault_search(text, limit=MAX_CONTEXT_NOTES, threshold=SIMILARITY_THRESHOLD)
            rag_time = time.time() - t_rag
            
            context = build_context(search_results) if search_results else ""
            
            if search_results:
                print(f"  📚 Found {len(search_results)} notes ({rag_time:.2f}s)")
            else:
                print(f"  📚 No vault matches ({rag_time:.2f}s)")
            
            # LLM with grounded context
            system_prompt, user_msg = build_prompt(text, context, lang="en")
            
            # Update system prompt with current context
            conversation_history[0] = {"role": "system", "content": system_prompt}
            conversation_history.append({"role": "user", "content": user_msg if context else text})
            
            print("  🧠 Thinking...")
            t0 = time.time()
            response = generate_response(conversation_history)
            llm_time = time.time() - t0
            
            print(f"  🤖 Scarlett: {response} ({llm_time:.2f}s)")
            conversation_history.append({"role": "assistant", "content": response})
            
            # TTS
            print("  🔊 Speaking...")
            t0 = time.time()
            audio_path = synthesize_to_file(response)
            tts_time = time.time() - t0
            
            if audio_path:
                print(f"  🔊 Playing... (TTS: {tts_time:.2f}s)")
                play_audio(audio_path)
            
            # Trim conversation history
            if len(conversation_history) > 20:
                conversation_history[:] = [conversation_history[0]] + conversation_history[-18:]
    
    except KeyboardInterrupt:
        print("\n\n  👋 Goodbye!")
        return


if __name__ == "__main__":
    main()