"""
TTS engine for Scarlett's voice responses.
Supports four engines (priority order):
1. Finetuned: Qwen3-TTS with Scarlett voice baked in (best quality, English)
2. CSM: Sesame CSM 1B for filler responses (no warm-up artifact, streaming)
3. Clone: Qwen3-TTS zero-shot cloning from reference audio
4. Preset: Kokoro-82M fast fallback voices

Scarlett's voice = Samantha from HER (Scarlett Johansson).
Interim: Kokoro af_bella (warm female) until fine-tuned model is ready.

Filler pipeline: CSM generates 2-3 word filler instantly while Qwen3-TTS
cooks the real answer. Zero warm-up artifact, ~300ms first-chunk latency.
"""

import os
import logging
import time
import re
import json
import numpy as np

logger = logging.getLogger(__name__)

# --- Configuration ---
# Fine-tuned model path (Scarlett voice, trained on Alice audiobook)
# "merged" dir has the LoRA-fused LLM backbone weights (no speaker encoder etc.)
# "final_adapter" dir has the raw LoRA adapters
FINETUNED_MODEL = os.path.expanduser("~/Media/voices/scarlett_finetuned/merged")
FINETUNED_ADAPTER = os.path.expanduser("~/Media/voices/scarlett_finetuned/final_adapter")
# Base model for loading speaker encoder + codec (merged model is missing these)
BASE_MODEL = os.path.expanduser("~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48")

# Reference audio for Scarlett voice — short clip from Alice audiobook (4s)
# Short reference = correct output duration. Long ref (12s) caused 6s output for 2s phrases.
SCARLETT_VOICE_REF = os.path.expanduser("~/Media/voices/scarlett_reference_short.wav")
SCARLETT_VOICE_REF_TEXT = "Why? I wouldn't say anything about it even if I fell off the top of the house."

# Old HER reference (12s) — kept for French zero-shot fallback only
HER_VOICE_REF = os.path.expanduser("~/Media/voices/her_reference_10s.wav")
HER_VOICE_REF_TEXT = "Earlier I was thinking about how I was annoyed, and it's gonna sound strange."

# Zero-shot model
ZEROSHOT_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"

# Voice mode: "preset" uses Kokoro af_bella (interim, until fine-tune is done)
#             "finetuned" uses the fine-tuned model (best quality)
#             "clone" uses Qwen3-TTS zero-shot with reference audio
VOICE_MODE = "finetuned"

# CSM filler model (Sesame CSM 1B via csm-mlx)
# Separate Python 3.12 venv — csm-mlx requires Python <3.13
CSM_VENV = os.path.expanduser("~/AI/OpenClaw/dev/csm-env")
CSM_PYTHON = os.path.join(CSM_VENV, "bin", "python3")
CSM_MODEL_AVAILABLE = os.path.isfile(CSM_PYTHON)

# Filler phrases — short, natural thinking sounds
CSM_FILLERS = [
    "Hmm, good question.",
    "Let me think about that.",
    "That's interesting.",
    "Good question.",
    "Let me see.",
    "Right, let me think.",
    "Interesting.",
    "Hmm, let me think.",
]

# Lazy-loaded pipelines
_kokoro_pipeline = None
_kokoro_lang = None
_finetuned_model = None
_finetuned_model_loaded = False
_csm_model = None
_csm_model_loaded = False


def _get_kokoro_pipeline(lang="en"):
    """Load or reuse the KokoroPipeline."""
    global _kokoro_pipeline, _kokoro_lang
    
    if _kokoro_pipeline is not None and _kokoro_lang == lang:
        return _kokoro_pipeline
    
    from mlx_audio.tts.models.kokoro.pipeline import KokoroPipeline
    logger.info(f"Loading KokoroPipeline for language: {lang}")
    start = time.time()
    _kokoro_pipeline = KokoroPipeline(lang=lang)
    _kokoro_lang = lang
    logger.info(f"KokoroPipeline loaded in {time.time() - start:.1f}s")
    return _kokoro_pipeline


def _truncate_text(text, max_chars=500):
    """Truncate text for TTS, keeping sentence boundaries."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    for sep in ['. ', '! ', '? ']:
        idx = truncated.rfind(sep)
        if idx > 100:
            return text[:idx + len(sep)].rstrip()
    return truncated.rstrip() + '.'


def generate_voice(text, lang="en", voice=None, speed=0.9):
    """
    Generate a voice audio file from text.
    
    Args:
        text: Text to speak
        lang: Language code (en, fr)
        voice: Voice name or path to reference audio for cloning
        speed: Speech speed multiplier
    
    Returns:
        Path to the generated WAV file, or None if generation fails
    """
    if not text or not text.strip():
        return None
    
    text = _truncate_text(text)
    
    # Decide which engine to use
    if voice and os.path.isfile(voice):
        # Explicit reference audio path — use zero-shot cloning
        return _generate_qwen3_clone(text, voice, lang)
    elif VOICE_MODE == "finetuned" and os.path.isdir(FINETUNED_MODEL) and lang == "en":
        # Fine-tuned model — best quality for English, no reference needed
        # French sounds male with fine-tuned model — use zero-shot clone instead
        return _generate_qwen3_finetuned(text, lang)
    elif (VOICE_MODE in ("finetuned", "clone")) and os.path.isfile(HER_VOICE_REF):
        # Zero-shot clone mode (also used for French with fine-tuned setting)
        return _generate_qwen3_clone(text, HER_VOICE_REF, lang, HER_VOICE_REF_TEXT)
    else:
        # Fallback to Kokoro preset voice
        voice = voice or ("af_bella" if lang == "en" else "bf_alice")
        return _generate_kokoro(text, lang, voice, speed)


def _crossfade_join(audio_paths, crossfade_ms=80, silence_ms=150, sample_rate=24000):
    """Join multiple audio files with crossfade transitions and short silence.
    
    Each chunk starts with a sibilant onset artifact. By crossfading the end
    of chunk N into the start of chunk N+1, we eliminate the harsh transition
    and create smooth, natural-sounding speech across chunk boundaries.
    
    Args:
        audio_paths: List of WAV file paths to join
        crossfade_ms: Duration of crossfade overlap in milliseconds
        silence_ms: Milliseconds of silence between segments (after crossfade)
        sample_rate: Sample rate of the audio
    
    Returns:
        Path to the joined WAV file, or None if joining fails
    """
    if not audio_paths:
        return None
    if len(audio_paths) == 1:
        return audio_paths[0]
    
    import soundfile as sf
    
    crossfade_samples = int(crossfade_ms * sample_rate / 1000)
    silence_samples = int(silence_ms * sample_rate / 1000)
    
    segments = []
    for path in audio_paths:
        data, sr = sf.read(path, dtype='float32')
        if sr != sample_rate:
            pass  # TODO: resample
        segments.append(data)
    
    # Build joined audio with crossfade + silence between chunks
    joined = segments[0]
    
    for seg in segments[1:]:
        # Apply cosine crossfade: fade out end of previous, fade in start of next
        fade_out = np.cos(np.linspace(0, np.pi / 2, crossfade_samples)) ** 2
        fade_in = np.sin(np.linspace(0, np.pi / 2, crossfade_samples)) ** 2
        
        # Fade out the tail of joined audio
        joined[-crossfade_samples:] *= fade_out
        # Fade in the head of the new segment
        seg[:crossfade_samples] *= fade_in
        
        # Short silence gap between chunks (natural breathing pause)
        silence = np.zeros(silence_samples, dtype=np.float32)
        
        # Overlap crossfade region then add silence
        # The crossfade samples overlap, so we replace the tail with blended audio
        overlap = joined[-crossfade_samples:] + seg[:crossfade_samples]
        joined = np.concatenate([
            joined[:-crossfade_samples],  # everything before the fade-out
            overlap,                         # blended crossfade region
            silence,                        # natural pause
            seg[crossfade_samples:]          # rest of new segment
        ])
    
    output_path = audio_paths[0].rsplit('.', 1)[0] + '_joined.wav'
    sf.write(output_path, joined, sample_rate)
    
    # Clean up individual segment files
    for path in audio_paths:
        if path != output_path and '_joined' not in path:
            try:
                os.remove(path)
            except OSError:
                pass
    
    return output_path


def _add_silence_padding(audio_paths, silence_ms=400, sample_rate=24000):
    """Join multiple audio files with silence padding between them.
    
    Legacy method — use _crossfade_join() for streaming chunks instead.
    
    Args:
        audio_paths: List of WAV file paths to join
        silence_ms: Milliseconds of silence between segments
        sample_rate: Sample rate of the audio
    
    Returns:
        Path to the joined WAV file, or None if joining fails
    """
    if not audio_paths:
        return None
    if len(audio_paths) == 1:
        return audio_paths[0]
    
    import soundfile as sf
    
    silence_samples = int(silence_ms * sample_rate / 1000)
    silence = np.zeros(silence_samples, dtype=np.float32)
    
    segments = []
    for path in audio_paths:
        data, sr = sf.read(path, dtype='float32')
        if sr != sample_rate:
            # Resample would go here — for now just use as-is
            pass
        segments.append(data)
    
    # Join with silence padding
    joined = segments[0]
    for seg in segments[1:]:
        joined = np.concatenate([joined, silence, seg])
    
    output_path = audio_paths[0].rsplit('.', 1)[0] + '_joined.wav'
    sf.write(output_path, joined, sample_rate)
    
    # Clean up individual segment files
    for path in audio_paths:
        if path != output_path and '_joined' not in path:
            try:
                os.remove(path)
            except OSError:
                pass
    
    return output_path


def _split_sentences(text):
    """Split text into sentences for TTS with natural pauses.
    
    Handles abbreviations (Mr., Dr., etc.), ellipses, and preserves
    punctuation. Merges very short fragments (< 15 chars) with the
    previous sentence to avoid tiny TTS chunks that sound unnatural.
    """
    # Protect abbreviations from false splits
    protected = text
    abbrevs = ['Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Sr.', 'Jr.', 'St.', 'vs.',
               'i.e.', 'e.g.', 'etc.', 'approx.', 'inc.', 'ltd.', 'corp.']
    placeholders = {}
    for i, abbr in enumerate(abbrevs):
        token = f'__ABBR{i}__'
        placeholders[token] = abbr
        protected = protected.replace(abbr, token)
    
    # Protect ellipses
    protected = protected.replace('...', '__ELLIPSIS__')
    
    # Split on sentence-ending punctuation followed by space or end
    # Use lookbehind for .!? plus space or end-of-string
    sentences = re.split(r'(?<=[.!?])\s+', protected)
    
    # Restore abbreviations and ellipses
    result = []
    for s in sentences:
        s = s.strip()
        for token, abbr in placeholders.items():
            s = s.replace(token, abbr)
        s = s.replace('__ELLIPSIS__', '...')
        if s:
            result.append(s)
    
    # Merge very short fragments (< 8 chars, like "No." or "Yes.") with previous sentence
    # Don't merge actual sentences just because they're brief
    merged = []
    for s in result:
        if merged and len(s) < 8:
            merged[-1] = merged[-1] + ' ' + s
        else:
            merged.append(s)
    
    return merged


def generate_voice_streaming(text, lang="en", chunk_callback=None):
    """Generate voice audio with sentence-boundary streaming.
    
    Splits text into sentences, generates audio for each chunk, and
    calls chunk_callback(path, index, total) as each chunk completes.
    The callback receives the WAV file path, chunk index (0-based),
    and total number of chunks.
    
    Returns the final concatenated WAV file path, or None on failure.
    """
    if not text or not text.strip():
        return None
    
    text = _truncate_text(text)
    sentences = _split_sentences(text)
    
    if len(sentences) <= 1:
        # Single sentence — no streaming needed, generate normally
        result = generate_voice(text, lang)
        if result and chunk_callback:
            chunk_callback(result, 0, 1)
        return result
    
    logger.info(f"Streaming TTS: {len(sentences)} chunks for {len(text)} chars")
    chunk_paths = []
    
    for i, sentence in enumerate(sentences):
        try:
            logger.info(f"Generating chunk {i+1}/{len(sentences)}: {sentence[:50]}...")
            chunk_path = generate_voice(sentence, lang)
            
            if chunk_path:
                # For streaming chunks, aggressively remove the Qwen3-TTS warm-up
                # artifact. The warm-up is 100-400ms of low-level noise (RMS 0.005-0.03)
                # before actual speech content. We detect the energy inflection point
                # where amplitude suddenly ramps up (3-5x increase in adjacent windows).
                chunk_path = _trim_silence(chunk_path, threshold=0.01, 
                                          min_leading_ms=10, min_trailing_ms=100,
                                          fade_in_ms=150)
                chunk_paths.append(chunk_path)
                if chunk_callback:
                    chunk_callback(chunk_path, i, len(sentences))
            else:
                logger.warning(f"Chunk {i+1}/{len(sentences)} failed, skipping")
        except Exception as e:
            logger.error(f"Chunk {i+1}/{len(sentences)} error: {e}")
            continue
    
    if not chunk_paths:
        logger.error("All chunks failed in streaming generation")
        return None
    
    # Crossfade join all chunks for smooth transitions
    if len(chunk_paths) == 1:
        return chunk_paths[0]
    
    return _crossfade_join(chunk_paths, crossfade_ms=80, silence_ms=150, sample_rate=24000)


def _load_finetuned_model():
    """Load and cache the fine-tuned model (base + merged LoRA weights)."""
    global _finetuned_model, _finetuned_model_loaded
    
    if _finetuned_model_loaded and _finetuned_model is not None:
        return _finetuned_model
    
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx
    
    logger.info("Loading fine-tuned Scarlett model (one-time)...")
    start = time.time()
    
    # Load base model architecture (speaker encoder, codec, etc.)
    model = load_model(BASE_MODEL, strict=False)
    
    # Overlay merged LoRA-fused backbone weights
    merged_weights = mx.load(os.path.join(FINETUNED_MODEL, "model.safetensors"))
    model.load_weights(list(merged_weights.items()), strict=False)
    mx.eval(model.parameters())
    
    _finetuned_model = model
    _finetuned_model_loaded = True
    logger.info(f"Fine-tuned model loaded in {time.time() - start:.1f}s")
    return model


def _trim_silence(audio_path, threshold=0.01, min_leading_ms=80, min_trailing_ms=150, fade_in_ms=120):
    """Trim Qwen3-TTS warm-up artifacts and apply fade-in for clean speech onset.
    
    Qwen3-TTS generates a "warm-up" artifact at the start: 100-400ms of low-level
    noise (RMS 0.005-0.03) that gradually builds before the actual speech content
    begins with a sharp energy increase. This sounds like a breathy pre-voice.
    
    Detection: Find the energy inflection point — where amplitude suddenly
    jumps up (3x+ increase between adjacent 10ms windows). This marks the
    transition from warm-up noise to real speech. Everything before that is cut.
    
    Returns the path to the trimmed file (overwrites in place).
    """
    try:
        import soundfile as sf
        data, sr = sf.read(audio_path, dtype='float32')
        
        if len(data) < 100:
            return audio_path
        
        # --- Find the energy inflection point ---
        # Real speech starts with a sharp increase in energy.
        # Warm-up noise: RMS 0.005-0.03, real speech: RMS 0.08+
        # We look for where energy jumps sharply (3x+ between windows).
        window_ms = 10
        window_samples = int(window_ms * sr / 1000)
        n_windows = min(80, len(data) // window_samples)  # Check first 800ms
        
        if n_windows < 3:
            return audio_path
        
        # Calculate RMS for each window
        rms_values = []
        for i in range(n_windows):
            start = i * window_samples
            end = min(start + window_samples, len(data))
            chunk = data[start:end]
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            rms_values.append(rms)
        
        # Find where real speech begins using three strategies:
        # 1. Sharp energy increase (3x+ jump between adjacent windows)
        # 2. First window above 0.03 with sustained energy after
        # 3. First window above 0.05
        speech_start_window = None
        
        # Strategy 1: Energy inflection point
        for i in range(1, n_windows - 1):
            prev_rms = rms_values[i-1]
            curr_rms = rms_values[i]
            next_rms = rms_values[i+1]
            
            # 3x+ jump in energy
            if prev_rms > 0.001:  # avoid div-by-zero
                ratio = curr_rms / prev_rms
                if ratio > 3.0 and curr_rms > 0.03:
                    speech_start_window = i
                    break
            
            # Also: transition from quiet (RMS < 0.02) to loud (RMS > 0.03)
            if prev_rms < 0.02 and curr_rms > 0.03 and next_rms > 0.02:
                speech_start_window = i
                break
        
        # Strategy 2: First RMS > 0.03 with sustained energy after
        if speech_start_window is None:
            for i in range(n_windows - 3):
                if rms_values[i] > 0.03:
                    # Check next 3 windows for sustained energy
                    sustained = sum(1 for j in range(i+1, min(i+4, n_windows)) if rms_values[j] > 0.05)
                    if sustained >= 2:
                        speech_start_window = i
                        break
        
        # Strategy 3: Last resort — first window above 0.05
        if speech_start_window is None:
            for i in range(n_windows):
                if rms_values[i] > 0.05:
                    speech_start_window = i
                break
        
        # Build trimmed audio
        if speech_start_window is not None:
            speech_start_sample = speech_start_window * window_samples
        else:
            speech_start_sample = 0
        
        leading_samples = int(min_leading_ms * sr / 1000)
        start = max(0, speech_start_sample - leading_samples)
        
        # Find end of speech
        trailing_samples = int(min_trailing_ms * sr / 1000)
        last_loud = len(data) - 1
        for i in range(len(data) - 1, -1, -1):
            if abs(data[i]) > threshold:
                last_loud = i
                break
        
        end = min(len(data), last_loud + 1 + trailing_samples)
        trimmed = data[start:end]
        
        logger.debug(f"_trim_silence: raw={len(data)/sr:.2f}s, "
                    f"speech_start={speech_start_sample/sr*1000:.0f}ms (window {speech_start_window}), "
                    f"trimmed={len(trimmed)/sr:.2f}s")
        
        # --- Apply cosine fade-in ---
        fade_samples = min(int(fade_in_ms * sr / 1000), len(trimmed))
        if fade_samples > 0:
            t = np.linspace(0, 1, fade_samples, dtype=np.float32)
            fade = 0.5 * (1 - np.cos(np.pi * t))
            trimmed[:fade_samples] *= fade
        
        # Short cosine fade-out (10ms)
        fade_out_samples = min(int(10 * sr / 1000), len(trimmed))
        if fade_out_samples > 0:
            t = np.linspace(0, 1, fade_out_samples, dtype=np.float32)
            fade = 0.5 * (1 + np.cos(np.pi * t))
            trimmed[-fade_out_samples:] *= fade
        
        sf.write(audio_path, trimmed, sr)
        return audio_path
    except Exception as e:
        logger.warning(f"Silence trimming failed: {e}")
        return audio_path


def _generate_qwen3_finetuned(text, lang="en"):
    """Generate voice using fine-tuned Qwen3-TTS model (best quality).
    
    Uses short (4s) Alice audiobook reference for speaker embedding.
    The long (12s) HER reference caused 6s output for 2s phrases.
    Short ref gives correct duration + Scarlett voice quality.
    """
    try:
        from mlx_audio.tts.generate import generate_audio
        
        output_dir = os.path.expanduser("~/Media/voices/tmp")
        os.makedirs(output_dir, exist_ok=True)
        gen_id = f"scarlett_{int(time.time() * 1000)}"
        output_path = os.path.join(output_dir, gen_id)
        os.makedirs(output_path, exist_ok=True)
        
        start = time.time()
        
        # Use cached model (loads once, reuses after)
        model = _load_finetuned_model()
        
        # Generate with short Scarlett reference for voice character
        generate_audio(
            text=text,
            output_path=output_path,
            model=model,
            lang_code=lang,
            speed=0.9,
            ref_audio=SCARLETT_VOICE_REF,
            ref_text=SCARLETT_VOICE_REF_TEXT,
            stt_model=None,
        )
        
        actual_file = None
        for f in os.listdir(output_path):
            if f.endswith('.wav'):
                actual_file = os.path.join(output_path, f)
                break
        
        if not actual_file or not os.path.exists(actual_file):
            logger.error(f"No fine-tuned audio generated at {output_path}")
            return None
        
        # Trim excessive silence from the output
        actual_file = _trim_silence(actual_file)
        
        elapsed = time.time() - start
        size = os.path.getsize(actual_file)
        logger.info(f"Fine-tuned voice: {size/1024:.1f}KB in {elapsed:.1f}s")
        return actual_file
        
    except Exception as e:
        logger.error(f"Fine-tuned generation failed: {e}")
        logger.info("Falling back to zero-shot clone")
        return _generate_qwen3_clone(text, HER_VOICE_REF, lang, HER_VOICE_REF_TEXT)


def _generate_qwen3_clone(text, ref_audio, lang="en", ref_text=None):
    """Generate voice using Qwen3-TTS with zero-shot cloning from reference audio."""
    try:
        from mlx_audio.tts.generate import generate_audio
        
        output_dir = os.path.expanduser("~/Media/voices/tmp")
        os.makedirs(output_dir, exist_ok=True)
        gen_id = f"scarlett_{int(time.time() * 1000)}"
        output_path = os.path.join(output_dir, gen_id)
        os.makedirs(output_path, exist_ok=True)
        
        kwargs = {
            "text": text,
            "output_path": output_path,
            "model": ZEROSHOT_MODEL,
            "voice": ref_audio,
            "lang_code": lang,
        }
        if ref_text:
            kwargs["ref_text"] = ref_text
        
        start = time.time()
        generate_audio(**kwargs)
        
        actual_file = None
        for f in os.listdir(output_path):
            if f.endswith('.wav'):
                actual_file = os.path.join(output_path, f)
                break
        
        if not actual_file or not os.path.exists(actual_file):
            logger.error(f"No Qwen3 clone audio generated at {output_path}")
            return None
        
        elapsed = time.time() - start
        size = os.path.getsize(actual_file)
        logger.info(f"Qwen3 cloned voice: {size/1024:.1f}KB in {elapsed:.1f}s")
        return actual_file
        
    except Exception as e:
        logger.error(f"Qwen3 clone failed: {e}")
        # Fallback to Kokoro
        logger.info("Falling back to Kokoro voice")
        return _generate_kokoro(text, lang, "af_bella", 1.0)


def _generate_kokoro(text, lang, voice, speed):
    """Generate voice using Kokoro-82M (fast, preset voices)."""
    try:
        from mlx_audio.tts.generate import generate_audio
        
        output_dir = os.path.expanduser("~/Media/voices/tmp")
        os.makedirs(output_dir, exist_ok=True)
        gen_id = f"scarlett_{int(time.time() * 1000)}"
        output_path = os.path.join(output_dir, gen_id)
        os.makedirs(output_path, exist_ok=True)
        
        start = time.time()
        generate_audio(
            text=text,
            output_path=output_path,
            model="mlx-community/Kokoro-82M-bf16",
            voice=voice,
            speed=speed,
            lang_code=lang,
        )
        
        actual_file = None
        for f in os.listdir(output_path):
            if f.endswith('.wav'):
                actual_file = os.path.join(output_path, f)
                break
        
        if not actual_file or not os.path.exists(actual_file):
            logger.error(f"No Kokoro audio generated at {output_path}")
            return None
        
        elapsed = time.time() - start
        size = os.path.getsize(actual_file)
        logger.info(f"Kokoro voice: {size/1024:.1f}KB in {elapsed:.1f}s")
        return actual_file
        
    except Exception as e:
        logger.error(f"Kokoro generation failed: {e}")
        return None


# --- CSM (Sesame Conversational Speech Model) ---

def generate_csm_filler(text=None, lang="en"):
    """Generate a short filler audio using Sesame CSM 1B.
    
    CSM has zero warm-up artifact and streams in ~300ms — perfect for
    instant filler while Qwen3-TTS generates the full answer.
    
    Uses the CSM filler server (port 8766) — a persistent process that keeps
    the model loaded. Falls back to subprocess if server is not running.
    
    Args:
        text: Filler text. If None, picks a random one from CSM_FILLERS.
        lang: Language code (CSM is English-only, FR falls back to Kokoro)
    
    Returns:
        Path to generated WAV file, or None if generation fails
    """
    if lang != "en":
        logger.info("CSM filler skipped for non-English")
        return None
    
    import random as _random
    if text is None:
        text = _random.choice(CSM_FILLERS)
    
    output_dir = os.path.expanduser("~/Media/voices/tmp")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"csm_filler_{int(time.time() * 1000)}.wav")
    
    # --- Try CSM filler server first (persistent, model already loaded) ---
    try:
        import urllib.request
        t0 = time.time()
        req = urllib.request.Request(
            "http://127.0.0.1:8766/generate",
            data=json.dumps({"text": text, "max_audio_length_ms": 5000}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=15)
        gen_time = float(resp.headers.get("X-Gen-Time", "0"))
        audio_dur = float(resp.headers.get("X-Audio-Duration", "0"))
        wav_data = resp.read()
        
        if wav_data:
            with open(output_path, "wb") as f:
                f.write(wav_data)
            logger.info(f"CSM filler via server: gen={gen_time:.2f}s audio={audio_dur:.2f}s")
            return output_path
    except Exception as e:
        logger.debug(f"CSM server not available ({e}), trying subprocess")
    
    # --- Fallback: subprocess in csm-mlx venv ---
    if not CSM_MODEL_AVAILABLE:
        logger.warning("CSM not available (csm-env Python 3.12 not found)")
        return None
    
    script = (
        'import sys\n'
        'sys.path.insert(0, "' + os.path.expanduser('~/AI/OpenClaw/dev/csm-env/lib/python3.12/site-packages') + '")\n'
        'import os\n'
        'os.environ["NO_TORCH_COMPILE"] = "1"\n'
        '\n'
        'from huggingface_hub import hf_hub_download\n'
        'from csm_mlx import CSM, csm_1b, generate\n'
        'import audiofile\n'
        'import numpy as np\n'
        'import time\n'
        '\n'
        't0 = time.time()\n'
        'csm = CSM(csm_1b())\n'
        'weight = hf_hub_download(repo_id="senstella/csm-1b-mlx", filename="ckpt.safetensors")\n'
        'csm.load_weights(weight)\n'
        'load_time = time.time() - t0\n'
        '\n'
        't1 = time.time()\n'
        'audio = generate(csm, text=' + repr(text) + ', speaker=0, context=[], max_audio_length_ms=5000)\n'
        'gen_time = time.time() - t1\n'
        '\n'
        'duration = len(audio) / 24000\n'
        'audiofile.write(' + repr(output_path) + ', np.asarray(audio), 24000)\n'
        'print(f"CSM filler: load={load_time:.2f}s gen={gen_time:.2f}s audio={duration:.2f}s")\n'
    )
    
    try:
        import subprocess as _sp
        result = _sp.run(
            [CSM_PYTHON, "-c", script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            logger.error(f"CSM filler subprocess failed: {result.stderr[-200:]}")
            return None
        
        if os.path.exists(output_path):
            logger.info(f"CSM filler generated: {output_path}")
            return output_path
        else:
            logger.error("CSM filler: output file not created")
            return None
            
    except _sp.TimeoutExpired:
        logger.error("CSM filler timed out (30s)")
        return None
    except Exception as e:
        logger.error(f"CSM filler error: {e}")
        return None


def generate_csm_streaming(text, lang="en", speaker=0, context=None):
    """Generate full audio using CSM with streaming chunk delivery.
    
    Uses csm-mlx's stream_generate() for real-time chunk output.
    Falls back to non-streaming generate() if streaming fails.
    
    Args:
        text: Text to speak
        lang: Language code (CSM is English-only)
        speaker: Speaker ID (0 = random speaker)
        context: List of Segment objects for conversation history
    
    Returns:
        Path to generated WAV file, or None if generation fails
    """
    if not CSM_MODEL_AVAILABLE:
        logger.warning("CSM not available")
        return None
    
    if lang != "en":
        logger.info("CSM skipped for non-English")
        return None
    
    context = context or []
    output_dir = os.path.expanduser("~/Media/voices/tmp")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"csm_full_{int(time.time() * 1000)}.wav")
    
    script = (
        'import sys\n'
        'sys.path.insert(0, "' + os.path.expanduser('~/AI/OpenClaw/dev/csm-env/lib/python3.12/site-packages') + '")\n'
        'import os\n'
        'os.environ["NO_TORCH_COMPILE"] = "1"\n'
        '\n'
        'from huggingface_hub import hf_hub_download\n'
        'from csm_mlx import CSM, csm_1b, generate\n'
        'import audiofile\n'
        'import numpy as np\n'
        'import time\n'
        '\n'
        't0 = time.time()\n'
        'csm = CSM(csm_1b())\n'
        'weight = hf_hub_download(repo_id="senstella/csm-1b-mlx", filename="ckpt.safetensors")\n'
        'csm.load_weights(weight)\n'
        'load_time = time.time() - t0\n'
        '\n'
        't1 = time.time()\n'
        'audio = generate(csm, text=' + repr(text) + ', speaker=' + str(speaker) + ', context=[], max_audio_length_ms=15000)\n'
        'gen_time = time.time() - t1\n'
        '\n'
        'duration = len(audio) / 24000\n'
        'audiofile.write(' + repr(output_path) + ', np.asarray(audio), 24000)\n'
        'print(f"CSM full: load={load_time:.2f}s gen={gen_time:.2f}s audio={duration:.2f}s RTF={gen_time/duration:.3f}")\n'
    )
    
    try:
        import subprocess as _sp
        result = _sp.run(
            [CSM_PYTHON, "-c", script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logger.error(f"CSM generation failed: {result.stderr[-200:]}")
            return None
        
        if os.path.exists(output_path):
            logger.info(f"CSM generated: {output_path}")
            return output_path
        else:
            logger.error("CSM: output file not created")
            return None
            
    except Exception as e:
        logger.error(f"CSM generation error: {e}")
        return None


def generate_voice_with_filler(text, lang="en", voice=None, speed=0.9):
    """Generate voice with CSM filler while the main TTS cooks.
    
    Pipeline:
    1. CSM generates a short filler ("Hmm, good question") in ~300ms
    2. Qwen3-TTS generates the full answer (2-4s)
    3. Both are returned — filler plays immediately, main answer follows
    
    Args:
        text: Text to speak (full answer)
        lang: Language code
        voice: Voice setting for main TTS
        speed: Speech speed for main TTS
    
    Returns:
        Dict with 'filler_path' (CSM audio) and 'main_path' (Qwen3-TTS audio),
        or just 'main_path' if CSM is unavailable
    """
    result = {}
    
    # Step 1: Generate CSM filler in a background thread
    import threading
    filler_result = {'path': None}
    
    def _gen_filler():
        filler_result['path'] = generate_csm_filler(lang=lang)
    
    filler_thread = threading.Thread(target=_gen_filler, daemon=True)
    filler_thread.start()
    
    # Step 2: Generate main TTS answer
    main_path = generate_voice(text, lang, voice, speed)
    result['main_path'] = main_path
    
    # Wait for filler (should finish well before main, but just in case)
    filler_thread.join(timeout=5.0)
    result['filler_path'] = filler_result['path']
    
    return result


# Available preset voices
VOICES = {
    "en": {
        "af_bella": "Bella (female, warm)",
        "af_sarah": "Sarah (female, clear)", 
        "af_nicole": "Nicole (female, professional)",
        "af_aoede": "Aoede (female, gentle)",
        "af_river": "River (female, calm)",
        "af_nova": "Nova (female, smooth)",
        "am_michael": "Michael (male, warm)",
    },
    "fr": {
        "bf_alice": "Alice (female, warm)",
        "bf_lily": "Lily (female, bright)",
        "ef_dora": "Dora (female, clear)",
        "ff_siwis": "Siwis (female, Swiss French)",
    }
}

def get_default_voice(lang="en"):
    """Get the default voice for a language.
    
    Fine-tuned HER model is now active for English.
    French uses zero-shot clone or Kokoro fallback.
    """
    return "af_bella" if lang == "en" else "bf_alice"