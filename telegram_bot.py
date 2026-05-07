"""
Receptionist Bot — Telegram Interface

Writing-first: text messages get text replies.
Voice memos transcribe with faster-whisper and receive a local preset voice reply.
Cloned/fine-tuned Scarlett voice is reserved for Mind Vault reader features.
"""
import os
import asyncio
import tempfile
import requests
import logging
import html
import shutil
import json
import glob
import difflib
import unicodedata
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from config import RAG_SERVICE_URL, RESPONSE_LANGUAGE, BOT_TOKEN
from tts import generate_fast_voice, get_default_voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INSCRIPTION_URL = "https://www.academiedemassage.com/inscription/"
CONTACT_URL = "https://www.academiedemassage.com/contact/"


STUDIO_COUNCIL_CHAT_ID = os.environ.get("STUDIO_COUNCIL_CHAT_ID", "-1003527002328")
OPENCLAW_SESSION_GLOB = os.path.expanduser("~/.openclaw/agents/main/sessions/*.jsonl")

def _text_from_message_content(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text") or ""
                if txt:
                    parts.append(txt)
        return "\n".join(parts).strip()
    return ""

def _latest_council_transcript(chat_id: str) -> Path | None:
    markers = [
        f'"chat_id": "telegram:{chat_id}"',
        f'\\"chat_id\\": \\"telegram:{chat_id}\\"',
        f'Studio Council id:{chat_id}',
    ]
    candidates = sorted((Path(p) for p in glob.glob(OPENCLAW_SESSION_GLOB)), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    for path in candidates[:80]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in markers):
                return path
        except Exception:
            continue
    return None

def _studio_council_context(chat_id: int | str, max_turns: int = 8) -> str:
    """Bridge Council context from OpenClaw's existing transcript.

    Telegram Bot API does not deliver bot messages to other bots, so Scarlett cannot
    see Alfred directly in the group. This reads the already-existing OpenClaw
    transcript on demand; no extra daemon or parent process.
    """
    chat_id = str(chat_id)
    if chat_id != STUDIO_COUNCIL_CHAT_ID:
        return ""
    transcript = _latest_council_transcript(chat_id)
    if not transcript:
        return ""
    turns = []
    try:
        for line in transcript.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("type") != "message":
                continue
            msg = row.get("message") or {}
            role = msg.get("role")
            text = _text_from_message_content(msg.get("content"))
            if not text or text == "NO_REPLY":
                continue
            if role == "user":
                speaker = "Sam"
            elif role == "assistant":
                speaker = "Alfred"
            else:
                continue
            # Keep Council bridge small and factual.
            turns.append(f"{speaker}: {text[:700]}")
    except Exception as e:
        logger.warning(f"Council bridge read failed: {e}")
        return ""
    if not turns:
        return ""
    recent = turns[-max_turns:]
    return "Contexte récent du Studio Council (inclut Alfred; Telegram ne livre pas les messages bot-à-bot):\n" + "\n".join(f"- {t}" for t in recent)

# --- Voice memo transcription ---
_stt_model = None

def _get_stt():
    """Lazy-load faster-whisper model."""
    global _stt_model
    if _stt_model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper STT model...")
        _stt_model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Whisper STT model loaded")
    return _stt_model

def _clean_transcript(text: str) -> str:
    """Remove common Whisper hallucinations from silence/unclear clips."""
    if not text:
        return ""
    import re
    cleaned = text.strip()
    lower = cleaned.lower()
    boilerplate_markers = [
        "sous-titres réalisés par la communauté d'amara.org",
        "sous titres réalisés par la communauté d'amara.org",
        "subtitles by the amara.org community",
        "captioning by amara.org",
        "merci d'avoir regardé",
        "thanks for watching",
        "c'est la fin de cette vidéo",
    ]
    # If the whole transcript is dominated by subtitle/video boilerplate, reject it.
    if any(m in lower for m in boilerplate_markers):
        non_boiler = lower
        for m in boilerplate_markers:
            non_boiler = non_boiler.replace(m, "")
        non_boiler = re.sub(r"[\s.,!?’'\-]+", "", non_boiler)
        if len(non_boiler) < 20:
            return ""
    bad_patterns = [
        r"sous[- ]titres réalisés par la communauté d['’]amara\.org",
        r"subtitles by the amara\.org community",
        r"captioning by amara\.org",
        r"merci d['’]avoir regardé(?: cette vidéo)?",
        r"thanks for watching",
        r"c['’]est la fin de cette vidéo",
    ]
    for pat in bad_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", cleaned).strip()


def _voice_text(text: str) -> str:
    """Convert a chat-formatted answer into clean plain text for TTS."""
    if not text:
        return ""
    import re
    plain = html.unescape(text)
    plain = re.sub(r"<\s*/?\s*b\s*>", "", plain, flags=re.IGNORECASE)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = plain.replace("•", "")
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


def _transcribe_with_cli(file_path, language="fr"):
    """Fallback transcription with the OpenAI Whisper CLI."""
    import subprocess
    import tempfile as _tempfile
    whisper = shutil.which("whisper")
    if not whisper:
        return ""
    with _tempfile.TemporaryDirectory() as outdir:
        cmd = [
            whisper, file_path,
            "--model", "small",
            "--output_format", "txt",
            "--output_dir", outdir,
            "--fp16", "False",
            "--condition_on_previous_text", "False",
            "--no_speech_threshold", "0.98",
        ]
        if language in ("fr", "en"):
            cmd.extend(["--language", language])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if result.returncode != 0:
                logger.warning(f"Whisper CLI failed: {result.stderr[-300:]}")
                return ""
            txt_files = [p for p in os.listdir(outdir) if p.endswith(".txt")]
            if not txt_files:
                return ""
            with open(os.path.join(outdir, txt_files[0]), "r", encoding="utf-8") as f:
                text = _clean_transcript(f.read().strip())
            logger.info(f"STT CLI text={text!r}")
            return text
        except Exception as e:
            logger.warning(f"Whisper CLI exception: {e}")
            return ""


def _transcribe_audio(file_path, language="en"):
    """Transcribe audio file to text using faster-whisper with fallbacks.

    Telegram voice memos can be very short/quiet. Forced French sometimes returns
    an empty transcript, so retry with auto language and English before giving up.
    """
    model = _get_stt()
    lang_map = {"en": "en", "fr": "fr"}
    preferred = lang_map.get(language, language)
    attempts = []
    if preferred:
        attempts.append(preferred)
    attempts.extend([None, "en" if preferred != "en" else "fr"])

    best = ""
    for lang_try in attempts:
        try:
            kwargs = dict(
                language=lang_try,
                condition_on_previous_text=False,
                beam_size=5,
                vad_filter=False,
                no_speech_threshold=0.98,
                log_prob_threshold=-2.0,
                compression_ratio_threshold=2.8,
            )
            segments, info = model.transcribe(file_path, **kwargs)
            text = _clean_transcript(" ".join(s.text for s in segments).strip())
            logger.info(f"STT attempt lang={lang_try or 'auto'} detected={getattr(info, 'language', None)} text={text!r}")
            if len(text) > len(best):
                best = text
            if len(text.strip()) >= 2:
                return text
        except Exception as e:
            logger.warning(f"STT attempt failed lang={lang_try}: {e}")
    cli_text = _transcribe_with_cli(file_path, preferred or "fr")
    if len(cli_text) > len(best):
        best = cli_text
    return best

def _convert_ogg_to_wav(ogg_path, wav_path):
    """Convert OGG audio to normalized WAV using ffmpeg."""
    import subprocess
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", ogg_path,
            "-ar", "16000", "-ac", "1",
            "-af", "highpass=f=80,lowpass=f=7600,loudnorm=I=-18:TP=-2:LRA=11,volume=1.8",
            "-f", "wav", wav_path
        ],
        capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-200:]}")
    return wav_path


def _is_greeting(question: str) -> bool:
    import re
    q = question.lower().strip().replace("’", "'")
    q = re.sub(r"[!?.,]+$", "", q).strip()
    # A caller may naturally add a tiny opener before small-talk after /start.
    # That is social small-talk, not consent to continue the pending guided offer.
    q = re.sub(r"^(oui|yes|ok|okay|d'accord|parfait|wow|oh|ah|hey|yo)[, \-!]+", "", q).strip()
    greeting_patterns = [
        r"^(hello|hi|hey|bonjour|salut|coucou|yo|howdy|allo|allô)$",
        r"^(hello|hi|hey|bonjour|salut|coucou|yo|allo|allô)[, ]+(how are you|how are you doing|ça va|ca va|comment ça va|comment ca va|comment allez[- ]?vous|comment vas[- ]?tu|tu vas bien|vous allez bien)$",
        r"^(how are you|how are you doing|ça va|ca va|comment ça va|comment ca va|comment allez[- ]?vous|comment vas[- ]?tu|tu vas bien|vous allez bien)$",
    ]
    # Do not treat short acknowledgements like "ok" as greetings; they often mean
    # "continue the active offer" in Scarlett's guided flow.
    return any(re.match(p, q) for p in greeting_patterns) or len(q) == 0


def _smooth_guided_offer(text: str) -> str:
    """Remove loop-prone closing offers after the answer already gave that info."""
    if not text:
        return text
    import re
    plain = html.unescape(text).lower()
    already_gave_price = any(x in plain for x in ["4 995", "4995", "prix"])
    if already_gave_price:
        text = re.sub(
            r"(?:\n\s*)?Je peux vous donner le prix du parcours habituel\.?\s*$",
            "\n\nJe peux ensuite regarder les prochaines dates.",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(?:\n\s*)?Je peux vous donner le prix du point de départ\.?\s*$",
            "\n\nJe peux ensuite regarder les prochaines dates.",
            text,
            flags=re.IGNORECASE,
        )

    # Avoid closing with two-choice menus; keep one logical next offer.
    text = re.sub(
        r"(?:\n\s*)?Qu[’']est-ce que vous aimeriez savoir ensuite\s*:\s*les prochaines dates disponibles ou les détails sur l[’']inscription\s*\?\s*$",
        "\n\nJe peux ensuite regarder les prochaines dates disponibles.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:\n\s*)?Qu[’']est-ce que vous aimeriez savoir en premier pour voir si ça vous convient\s*:\s*le contenu(?: détaillé| des cours)?, les horaires? disponibles ou l[’']inscription\s*\?\s*$",
        "\n\nJe peux commencer par le contenu du parcours.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:\n\s*)?Souhaitez-vous connaître les horaires disponibles ou les prochaines dates de début\s*\?\s*$",
        "\n\nJe peux ensuite regarder les prochaines dates de début.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:\n\s*)?Est-ce que cela vous intéresse\s*\?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _chat_safe(text: str, strip_intro: bool = False) -> str:
    """Format LLM output for readable Telegram HTML.

    Allows a tiny safe subset: <b>bold</b>, line breaks, and simple bullets.
    Everything else is escaped so customer chat stays clean.
    """
    if not text:
        return text
    import re
    text = text.replace("### ", "").replace("## ", "").replace("# ", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "- ", text)
    text = "\n".join(line for line in text.splitlines() if not re.match(r"^\s*\|?\s*:?-{3,}:?", line))
    if strip_intro:
        # Remove leaked meta-instruction refusals and repeated receptionist intros.
        text = re.sub(r"(?is)^Je ne peux pas répondre en tant que .*?(?=Bonjour,|$)", "", text).strip()
        intro_patterns = [
            r"^Bonjour,?\s+je suis Scarlett,?\s+la réception virtuelle de l['’]AMS\.\s*",
            r"^Bonjour,?\s+je suis Scarlett,?\s+la réceptionniste virtuelle de l['’]Académie de Massage Scientifique\.\s*",
            r"^Bonjour,?\s+je suis Scarlett,?\s+la réception virtuelle de l['’]AMS\.\s*",
            r"^Bonjour,?\s+je suis Scarlett\.\s*",
            r"^Je suis Scarlett,?\s+la réception virtuelle de l['’]AMS\.\s*",
            r"^Je suis Scarlett,?\s+la réceptionniste virtuelle de l['’]Académie de Massage Scientifique\.\s*",
            r"^Scarlett,?\s+la réception virtuelle de l['’]AMS\.\s*",
        ]
        for pat in intro_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = escaped.replace("**", "").replace("__", "")
    # Auto-bold short label lines: Prix:, Durée:, Parcours:, etc.
    escaped = re.sub(r"(?m)^([A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9 /|’'\-]{1,38}) :", r"<b>\1</b> :", escaped)
    escaped = re.sub(r"(?m)^([A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9 /|’'\-]{1,38}):", r"<b>\1</b>:", escaped)
    return escaped


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    context.user_data["welcomed"] = True
    context.user_data["welcomed_once"] = True
    context.user_data["pending_offer"] = "Expliquer calmement comment Scarlett fonctionne et comment elle oriente une personne vers le bon parcours AMS; si la personne dit oui ou demande comment ça marche, donner le fonctionnement en mode service client, puis commencer par le parcours débutant Niveau 1."
    if RESPONSE_LANGUAGE == "fr":
        await update.message.reply_text(
            "Bonjour, je suis Scarlett.\n\n"
            "Je peux vous aider à trouver le bon parcours à l’Académie de Massage Scientifique — formations, prix, campus et prochaines étapes.\n\n"
            "Vous commencez en massage, ou vous avez déjà une formation ?"
        )
    else:
        await update.message.reply_text(
            "Hi, I’m Scarlett.\n\n"
            "I can help you find the right path at the academy — programs, pricing, campuses, and next steps.\n\n"
            "Are you starting fresh, or do you already have massage training?"
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    if RESPONSE_LANGUAGE == "fr":
        await update.message.reply_text(
            "Scarlett — Réception AMS\n\n"
            "Posez une question par écrit sur les formations, les prix, les campus, l’inscription ou le bon parcours selon votre situation.\n\n"
            "Commandes :\n"
            "/start — Recommencer l’accueil\n"
            "/help — Cette aide\n"
            "/lang en|fr — Changer la langue\n"
            "/voice — État du mode vocal"
        )
    else:
        await update.message.reply_text(
            "Scarlett — Reception\n\n"
            "Ask a written question about programs, pricing, campuses, registration, or the right path for your situation.\n\n"
            "Commands:\n"
            "/start — Restart the welcome flow\n"
            "/help — This help\n"
            "/lang en|fr — Switch language\n"
            "/voice — Voice mode status"
        )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command."""
    try:
        resp = requests.get(f"{RAG_SERVICE_URL}/stats", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                notes = data.get("totalNotes", "?")
                blocks = data.get("totalBlocks", "?")
                model = data.get("modelKey", "?")
                await update.message.reply_text(
                    f"📊 Statistiques internes\n\n"
                    f"Fiches: {notes}\n"
                    f"Blocks: {blocks}\n"
                    f"Embedding model: {model}"
                )
            else:
                await update.message.reply_text(f"Stats: {data}")
        else:
            await update.message.reply_text("Could not fetch stats from RAG service.")
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await update.message.reply_text("RAG service unavailable.")


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lang command to switch language."""
    if not context.args:
        await update.message.reply_text(f"Current language: {RESPONSE_LANGUAGE}\nUsage: /lang en or /lang fr")
        return

    lang = context.args[0].lower()
    if lang in ("en", "fr"):
        context.user_data["lang"] = lang
        await update.message.reply_text(f"Language set to {'English' if lang == 'en' else 'Français'}")
    else:
        await update.message.reply_text("Supported languages: en, fr")


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explain voice behaviour."""
    await update.message.reply_text("Pour l’instant, Scarlett répond seulement par écrit. Envoyez votre question en message texte.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice memo messages — transcribe, then respond."""
    lang = context.user_data.get("lang", RESPONSE_LANGUAGE)
    # Voice memos always receive voice replies.

    # Show recording indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    ogg_path = None
    wav_path = None

    try:
        # Download voice file
        voice = update.message.voice or update.message.audio
        if not voice:
            await update.message.reply_text("Couldn't read that voice message.")
            return

        file = await voice.get_file()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            ogg_path = tmp.name
            await file.download_to_drive(ogg_path)

        # Convert OGG to WAV for whisper
        wav_path = ogg_path.replace(".ogg", ".wav")
        await asyncio.to_thread(_convert_ogg_to_wav, ogg_path, wav_path)
        # Keep latest incoming clip for live debugging, even if transcription succeeds.
        try:
            shutil.copy2(wav_path, "/tmp/scarlett_last_voice.wav")
            shutil.copy2(ogg_path, "/tmp/scarlett_last_voice.ogg")
        except Exception:
            pass

        # Transcribe
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        transcript = await asyncio.to_thread(_transcribe_audio, wav_path, lang)

        logger.info(f"Voice transcript: {transcript}")

        if not transcript or len(transcript.strip()) < 2:
            # Keep the latest failed clip locally so we can inspect STT failures.
            try:
                if wav_path and os.path.exists(wav_path):
                    shutil.copy2(wav_path, "/tmp/scarlett_last_failed_voice.wav")
                if ogg_path and os.path.exists(ogg_path):
                    shutil.copy2(ogg_path, "/tmp/scarlett_last_failed_voice.ogg")
            except Exception:
                pass
            # Clean up temp originals after debug copy.
            for p in [ogg_path, wav_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
            ogg_path = wav_path = None
            await update.message.reply_text("Je n’ai pas réussi à bien entendre. Pouvez-vous réessayer un peu plus près du micro ?")
            return

        # Clean up audio files
        for p in [ogg_path, wav_path]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        ogg_path = wav_path = None

        # Now process as text — same flow as handle_message
        question = transcript.strip()

        # Handle greetings locally; do not send small talk through RAG.
        if _is_greeting(question):
            context.user_data["welcomed"] = True
            if context.user_data.get("welcomed_once"):
                await update.message.reply_text("Oui, je suis là. Quelle information AMS souhaitez-vous vérifier ?")
            else:
                context.user_data["welcomed_once"] = True
                await update.message.reply_text("Bonjour, je suis Scarlett. Je peux vous aider à trouver le bon parcours à l’AMS.")
            return

        if _is_repeat_complaint(question):
            answer = _repeat_complaint_reply(context.user_data)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_capability_query(question):
            answer = _capability_reply(context.user_data)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_how_it_works_query(question):
            answer = _how_it_works_reply(context.user_data)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_old_bot_query(question):
            answer = _old_bot_reply(context.user_data, question)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_assumption_challenge(question):
            answer = _assumption_challenge_reply(context.user_data)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_lost_query(question):
            answer = _lost_reply(context.user_data)
            _update_conversation_state(context.user_data, question, answer)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_new_student_intro(question):
            answer = _new_student_intro_reply(context.user_data, question)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        if _is_trained_student_intro(question):
            answer = _trained_student_intro_reply(context.user_data, question)
            await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
            return

        direct = _direct_flow_reply(context.user_data, question)
        if direct:
            answer, button_text, url = direct
            _update_conversation_state(context.user_data, question, answer)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=url)]]) if button_text and url else None
            await update.message.reply_text(
                _chat_safe(answer),
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return

        # Show typing while we query RAG
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        conv_parts = []
        conv_ctx = _conversation_context(context.user_data)
        if conv_ctx:
            conv_parts.append(conv_ctx)
        council_ctx = _studio_council_context(update.effective_chat.id)
        if council_ctx:
            conv_parts.append(council_ctx)
        question_for_rag = _expand_followup_question(context.user_data, question)
        payload = {"question": question_for_rag, "language": lang}
        if conv_parts:
            payload["conversation_context"] = "\n\n".join(conv_parts)
        resp = requests.post(
            f"{RAG_SERVICE_URL}/ask",
            json=payload,
            timeout=30
        )

        if resp.status_code != 200:
            await update.message.reply_text("Sorry, I couldn't process that right now.")
            return

        data = resp.json()
        raw_answer = data.get("answer", "I couldn't process that question.")
        answer = _smooth_guided_offer(_chat_safe(raw_answer, strip_intro=True))
        answer = _de_repeat_answer(context.user_data, answer)
        answer_for_voice = _voice_text(answer)
        sources = data.get("sources", [])
        refused = data.get("refused", False)

        # Format text response
        message = answer
        # Internal source names are never shown to customers.

        if len(message) > 4000:
            message = message[:3997] + "..."

        # Reply with voice (always voice reply to voice input)
        if answer and not refused:
            caption = ""
            # Internal source names are never shown to customers.

            # Show what we heard as context
            heard_text = f"🎤 \"{transcript}\"\n\n" if len(transcript) < 100 else ""

            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
            _update_conversation_state(context.user_data, question, answer_for_voice)
            voice_path = await asyncio.to_thread(
                generate_fast_voice, answer_for_voice, lang, get_default_voice(lang)
            )
            if voice_path:
                try:
                    with open(voice_path, 'rb') as audio_file:
                        await update.message.reply_voice(
                            voice=audio_file,
                            caption=(heard_text + caption).strip()[:200] or None
                        )
                    logger.info(f"Voice reply sent for voice memo: {voice_path}")
                except Exception as e:
                    logger.warning(f"Failed to send voice reply: {e}")
                    await update.message.reply_text(html.escape(heard_text) + message, parse_mode="HTML")
                finally:
                    try:
                        os.remove(voice_path)
                        parent = os.path.dirname(voice_path)
                        if os.path.isdir(parent) and parent.startswith(os.path.expanduser("~/Media/voices/tmp")):
                            os.rmdir(parent)
                    except:
                        pass
            else:
                await update.message.reply_text(html.escape(heard_text) + message, parse_mode="HTML")
        else:
            await update.message.reply_text(message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Voice memo error: {e}", exc_info=True)
        await update.message.reply_text("Something went wrong processing your voice message. Try again?")

    finally:
        # Clean up temp files
        for p in [ogg_path, wav_path]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


def _conversation_context(user_data) -> str:
    facts = user_data.get("facts", {})
    parts = []
    if user_data.get("welcomed") or user_data.get("welcomed_once"):
        parts.append("L'accueil a déjà été fait dans cette conversation. Ne pas répéter 'Bonjour, je suis Scarlett' ni réintroduire le rôle; répondre directement.")
    if facts.get("student_status") == "new":
        parts.append("La personne a déjà dit qu'elle est nouvelle/débutante en massage. Ne pas redemander si elle débute; présenter la suite logique du Niveau 1.")
    elif facts.get("student_status") == "trained":
        parts.append("La personne a déjà dit qu'elle a une formation en massage. Ne pas redemander si elle débute. Pour l'orientation, présenter d'abord le parcours principal le plus complet: Niveau 2 | Masso-kinésithérapie spécialisation en sportif OU Niveau 2 | Massothérapie avancée spécialisation anti-stress, 600 h, 7 345 $. Ensuite seulement Niveau 3 Orthothérapie avancée, puis les cours à la carte comme options complémentaires.")
    if facts.get("name"):
        parts.append(f"Prénom du client: {facts['name']}. Utiliser le prénom rarement, seulement quand ça confirme ou guide naturellement; jamais à chaque réponse.")
    if facts.get("active_goal"):
        label = _goal_label(facts.get("active_goal")) or facts.get("active_goal")
        parts.append(f"Objectif déjà exprimé: {label}. Ne pas redemander l'objectif; utiliser ce contexte pour choisir les cours, le parcours ou la prochaine étape. Si la personne demande 'lesquels', 'quoi ensuite' ou répond oui/ok, continuer dans cet objectif.")
    if facts.get("signup_link_sent"):
        parts.append("Le lien/formulaire d'inscription vient déjà d'être transmis. Ne pas le reproposer tout de suite sauf si la personne le redemande clairement; proposer plutôt de répondre aux questions ou clarifier le contenu/horaire.")
    if facts.get("pre_signup_question_asked") and not facts.get("signup_link_sent"):
        parts.append("La personne a demandé à s'inscrire, mais Scarlett doit confirmer au moins une chose utile avant d'envoyer le formulaire: parcours visé, campus, ou s'il reste une question. Ne transmettre le formulaire que si la personne confirme après cette étape.")
    if user_data.get("pending_offer"):
        parts.append(f"Dernière offre active: {user_data['pending_offer']}. Si la personne répond seulement oui/ok, continuer avec cette offre sans répéter le choix.")
    last = user_data.get("recent_turns", [])[-3:]
    recent_payment_covered = any(
        any(token in _repeat_norm(t.get("a", "")) for token in ["104 semaine", "ifinance", "paiement echelonne", "marge de credit", "banque"])
        for t in last
    )
    if recent_payment_covered:
        parts.append("Les options de paiement/financement ont déjà été couvertes récemment. Ne pas les réénumérer ni laisser croire qu'il y en a d'autres. Si la personne dit que c'est trop cher ou qu'elle n'a pas les moyens, répondre avec empathie et patience, puis demander si elle veut détailler une option précise ou passer à autre chose.")
    if last:
        parts.append("Anti-répétition stricte: ne jamais reprendre la même formule d'ouverture, le même paragraphe d'explication, ou la même offre finale que dans les échanges récents. Répondre à la nouvelle demande avec de l'information nouvelle ou un angle plus précis. Éviter complètement les amorces génériques déjà utilisées comme « C'est une excellente question ».")
        openings = _recent_answer_openings(last)
        if openings:
            parts.append("Ouvertures déjà utilisées à ne pas réutiliser:")
            for opening in openings:
                parts.append(f"- {opening}")
        parts.append("Derniers échanges résumés:")
        for t in last:
            parts.append(f"- Client: {t.get('q','')[:140]} | Scarlett: {t.get('a','')[:220]}")
    return "\n".join(parts)


def _plain_text(text: str) -> str:
    import re
    raw = html.unescape(text or "")
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = raw.replace("**", "")
    return re.sub(r"\s+", " ", raw).strip()


def _repeat_norm(text: str) -> str:
    import re
    text = _plain_text(text).lower().replace("’", "'")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9$% ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_response_units(text: str) -> list[str]:
    """Split a bot answer into paragraphs / leading sentences for repeat guards."""
    import re
    raw = html.unescape(text or "").strip()
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", "", raw)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if not paragraphs and raw:
        paragraphs = [raw]
    units = []
    for p in paragraphs[:2]:
        units.append(p)
        units.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", p)[:2] if s.strip())
    return units


def _recent_answer_openings(turns: list[dict], limit: int = 3) -> list[str]:
    openings = []
    for t in turns:
        units = _split_response_units(t.get("a", ""))
        if units:
            opening = _plain_text(units[0])[:180]
            if opening and opening not in openings:
                openings.append(opening)
    return openings[-limit:]


def _similar(a: str, b: str) -> float:
    na, nb = _repeat_norm(a), _repeat_norm(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _de_repeat_answer(user_data, answer: str) -> str:
    """Post-process Scarlett replies so prompt-level anti-repeat failures do not reach customers."""
    import re
    if not answer:
        return answer

    if user_data.pop("_allow_repeat_once", None):
        return answer

    recent_answers = [t.get("a", "") for t in user_data.get("recent_turns", [])[-3:] if t.get("a")]
    if not recent_answers:
        return answer

    guarded = answer.strip()
    guarded_plain = _plain_text(guarded).lower()
    # A focused course answer can overlap a previous catalogue/list answer.
    # Do not collapse it into a generic anti-repeat apology; the caller has
    # narrowed from catalogue to a specific course, which is useful progress.
    if ("aromathérapie" in guarded_plain or "aromatherapie" in guarded_plain) and (
        "formation à la carte" in guarded_plain
        or "formation a la carte" in guarded_plain
        or "aromathérapie : les bases" in guarded_plain
        or "aromatherapie : les bases" in guarded_plain
        or "huiles essentielles" in guarded_plain
    ):
        return guarded
    if _repeat_norm(guarded).startswith("c est une excellente question"):
        guarded = re.sub(r"^[^.!?]*[.!?]\s*", "", guarded, count=1).strip()
    generic_openers = [
        r"^C['’]est une excellente question,?\s*(?:et c['’]est (?:tout à fait )?normal de vouloir[^.!?]*[.!?]\s*)?",
        r"^C['’]est (?:tout à fait )?normal de vouloir[^.!?]*[.!?]\s*",
        r"^Je comprends que les détails financiers ou administratifs peuvent sembler[^.!?]*[.!?]\s*",
        r"^Je comprends que c['’]est stressant de voir le prix total[^.!?]*[.!?]\s*",
        r"^Je comprends\.?\s*",
        r"^Pour vous donner une idée réaliste,?\s*",
    ]
    if any("c est une excellente question" in _repeat_norm(a) for a in recent_answers):
        before = guarded
        for pat in generic_openers:
            guarded = re.sub(pat, "", guarded, flags=re.IGNORECASE).strip()
        # Last-resort opener trim if wording varied beyond the known patterns.
        if guarded == before and _repeat_norm(guarded).startswith("c est une excellente question"):
            guarded = re.sub(r"^[^.!?]*[.!?]\s*", "", guarded, count=1).strip()

    for _ in range(3):
        units = _split_response_units(guarded)
        if not units:
            break
        # Prefer sentence-level trimming over deleting the whole paragraph.
        lead = units[1] if len(units) > 1 else units[0]
        lead_norm = _repeat_norm(lead)
        if len(lead_norm) < 20:
            break
        repeated = any(_similar(lead, old_unit) >= 0.82 for old in recent_answers for old_unit in _split_response_units(old))
        if not repeated:
            break
        pattern = re.escape(lead)
        guarded = re.sub(pattern, "", guarded, count=1).strip()
        guarded = re.sub(r"^(?:<br\s*/?>|\s|\n)+", "", guarded).strip()

    if any(_similar(guarded, old) >= 0.76 for old in recent_answers):
        return (
            "Vous avez raison — je ne vais pas répéter la même réponse.\n\n"
            "Je garde le contexte déjà couvert. Pouvez-vous préciser l’angle que vous voulez : le contenu du cours, le prix, la durée, ou le meilleur choix selon votre objectif ?"
        )

    payment_tokens = ["104 $", "104$", "ifinance", "paiement échelonné", "paiement echelonne", "marge de crédit", "marge de credit"]
    payment_recent = any(any(tok in _plain_text(old).lower() for tok in payment_tokens) for old in recent_answers)
    payment_now = any(tok in _plain_text(guarded).lower() for tok in payment_tokens)
    affordability_now = any(tok in _repeat_norm(guarded) for tok in ["trop cher", "pas les moyens", "budget"])
    if payment_recent and payment_now and affordability_now:
        guarded = (
            "Je comprends. C’est beaucoup d’argent, et je ne veux pas vous faire tourner en rond.\n\n"
            "Les options de paiement connues ont déjà été couvertes. Voulez-vous que je détaille une option précise, ou est-ce que je peux vous aider avec autre chose ?"
        )

    guarded = re.sub(r"^(Cependant|Toutefois|Par contre),?\s+", "", guarded, flags=re.IGNORECASE).strip()
    if not guarded:
        return (
            "Vous avez raison — je ne vais pas répéter la même réponse.\n\n"
            "Je garde ce qui a déjà été couvert et je réponds seulement au nouvel angle demandé."
        )
    if guarded and guarded[0].islower():
        guarded = guarded[0].upper() + guarded[1:]
    return guarded


def _is_repeat_complaint(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in [
        "arrete de repeter", "arrête de répéter", "tu repetes", "tu répètes", "vous repetez", "vous répétez",
        "stop repeating", "same answer", "meme reponse", "même réponse", "encore la meme", "encore la même",
        "tu viens de dire", "vous venez de dire"
    ])


def _repeat_complaint_reply(user_data) -> str:
    user_data["repeat_guard_active"] = True
    user_data.pop("pending_offer", None)
    return (
        "Vous avez raison — je vais arrêter de reprendre la même formule.\n\n"
        "À partir d’ici, je réponds directement à la nouvelle question et je garde en tête ce qui a déjà été couvert."
    )


def _norm_chat(text: str) -> str:
    import re
    q = (text or "").lower().strip()
    q = q.replace("’", "'")
    q = re.sub(r"[!?.,]+$", "", q).strip()
    return re.sub(r"\s+", " ", q)


def _is_affirmation(question: str) -> bool:
    q = _norm_chat(question)
    if _is_greeting(question):
        return False
    social_or_question = [
        "comment", "ça va", "ca va", "allez vous", "allez-vous", "vas tu", "vas-tu",
        "qui", "quoi", "pourquoi", "combien", "quel", "quelle", "où", "ou ", "when", "what", "how",
    ]
    if q.startswith(("oui ", "yes ", "ok ", "okay ", "d'accord ")) and any(x in q for x in social_or_question):
        return False
    affirmations = {
        "oui", "yes", "yep", "yeah", "ok", "okay", "d'accord", "dac",
        "parfait", "vas-y", "vas y", "allez", "go", "oui svp",
        "oui s'il vous plait", "oui s'il te plait", "oui merci"
    }
    return q in affirmations or (q.startswith("oui") and len(q) <= 40) or ("d'accord" in q and len(q) <= 40)


def _is_capability_query(question: str) -> bool:
    """User asks what Scarlett can do; answer capabilities, do not infer a course path."""
    q = _norm_chat(question)
    exact = any(x in q for x in [
        "qu'est ce que tu peux faire", "qu'est-ce que tu peux faire", "quest ce que tu peux faire",
        "qu'est ce que vous pouvez faire", "qu'est-ce que vous pouvez faire", "quest ce que vous pouvez faire",
        "tu peux faire quoi", "vous pouvez faire quoi", "que peux-tu faire", "que pouvez-vous faire",
        "comment tu peux m'aider", "comment vous pouvez m'aider", "comment peux-tu m'aider",
        "what can you do", "how can you help",
    ])
    loose = any(x in q for x in ["peux faire", "pouvez faire"]) and any(x in q for x in ["pour moi", "m'aider", "aider", "quoi", "que"])
    return exact or loose


def _capability_reply(user_data) -> str:
    user_data.pop("pending_offer", None)
    return (
        "Je peux vous aider à vous orienter dans les formations AMS : le bon parcours selon votre situation, "
        "les prix, les campus, l’inscription, les dates générales et les questions pratiques.\n\n"
        "Je peux aussi vous éviter de fouiller tout le site : vous me dites ce que vous cherchez, "
        "et je vous donne la prochaine étape claire."
    )


def _is_how_it_works_query(question: str) -> bool:
    """User asks how Scarlett/the school process works; answer confidently, do not fail to office."""
    q = _norm_chat(question)
    for prefix in ("oui ", "ok ", "d'accord ", "parfait "):
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
    return any(x in q for x in [
        "comment ca fonctionne", "comment ça fonctionne", "comment sa fonctionne",
        "comment ca marche", "comment ça marche", "comment sa marche",
        "ca fonctionne comment", "ça fonctionne comment", "sa fonctionne comment",
        "ca marche comment", "ça marche comment", "sa marche comment",
        "comment fonctionne", "comment marche", "fonctionne", "fonctionement", "fonctionnement",
        "how does it work", "how it works",
    ])


def _how_it_works_reply(user_data) -> str:
    user_data["pending_offer"] = "Continuer avec un aperçu débutant Niveau 1: prix, durée, format hybride et prochaine étape de découverte. Ne pas envoyer le formulaire sauf demande claire."
    return (
        "Bien sûr. Le fonctionnement est simple.\n\n"
        "Je vous aide d’abord à situer votre point de départ : est-ce que vous commencez en massage, est-ce que vous êtes déjà étudiant, ou est-ce que vous avez déjà une formation. Ensuite, je vous donne le parcours le plus logique, avec les prix, le format, les campus et les prochaines étapes.\n\n"
        "Si vous commencez, le point de départ habituel est le **Niveau 1 | Praticien en massothérapie** : 400 heures, format hybride, 4 995 $.\n\n"
        "Je peux vous expliquer ce parcours clairement, sans vous envoyer trop vite vers un formulaire."
    )


def _is_old_bot_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in ["ancien bot", "ancienne bot", "ancien robot", "ancienne robot", "bot du site", "julie"])


def _old_bot_reply(user_data, question: str) -> str:
    user_data.pop("pending_offer", None)
    return (
        "Je vois. L’ancien bot pouvait être limité; moi, je vais rester concrète et vous aider directement.\n\n"
        "Dites-moi simplement ce que vous voulez comprendre — les formations, les prix, les campus, l’inscription ou le bon parcours — et je vous donne une réponse claire."
    )


def _is_assumption_challenge(question: str) -> bool:
    """User is challenging a wrong assumption; do not treat mentioned status terms as facts."""
    q = _norm_chat(question)
    challenge = any(x in q for x in [
        "comment tu assume", "comment tu assumes", "pourquoi tu assume", "pourquoi tu assumes",
        "tu assumes", "tu assume", "t'assumes", "t assume", "pourquoi tu penses",
        "comment ca tu assume", "comment ça tu assume", "comment ca tu assumes", "comment ça tu assumes",
    ])
    status_terms = any(x in q for x in [
        "niveau 1", "niveau 2", "formation", "déjà", "deja", "praticien", "praticienne",
        "massothérapeute", "massotherapeute", "400h", "400 heures",
    ])
    return challenge and status_terms


def _assumption_challenge_reply(user_data) -> str:
    facts = user_data.setdefault("facts", {})
    facts.pop("student_status", None)
    user_data.pop("pending_offer", None)
    return (
        "Vous avez raison — je suis allée trop vite. Je ne devrais pas supposer que vous avez déjà le Niveau 1.\n\n"
        "On reprend proprement : vous commencez en massage, vous êtes déjà étudiant à l’AMS, "
        "ou vous avez déjà une formation en massage ?"
    )


def _is_dates_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in ["date", "dates", "session", "sessions", "quand", "debut", "début", "horaire", "horaires"])


def _is_lost_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in [
        "je suis perdu", "je suis perdue", "suis perdu", "suis perdue", "un peu perdu", "un peu perdue",
        "je ne sais pas", "je sais pas", "jsais pas", "j'sais pas", "pas sur", "pas sûr", "pas sure", "pas sûre",
        "je veux comprendre", "aide moi", "aidez moi", "besoin d'aide", "besoin aide",
    ])


def _lost_reply(user_data) -> str:
    user_data.pop("pending_offer", None)
    user_data.setdefault("facts", {}).pop("signup_link_sent", None)
    user_data["pending_offer"] = "Aider la personne à s'orienter doucement; si elle répond oui/ok, donner l'aperçu débutant Niveau 1 en mode découverte."
    return (
        "Bien sûr. On va y aller simplement.\n\n"
        "À l’AMS, si vous commencez en massage, le point de départ habituel est le **Niveau 1 | Praticien en massothérapie**.\n\n"
        "Je peux vous expliquer le parcours, le prix et comment la formation fonctionne, étape par étape."
    )


def _is_enrolment_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in [
        "inscription", "inscrire", "m'inscrire", "minscrire", "m inscrire", "formulaire", "lien", "site web",
        "réserver", "reserver", "ma place", "place", "j'aimerais m'inscrire", "jaimerais minscrire",
        "je veux m'inscrire", "veux minscrire", "prêt à m'inscrire", "prete a minscrire", "prête à m'inscrire"
    ])


def _needs_pre_signup_check(user_data, question: str) -> bool:
    """Before sending the form, ask at least one useful sorting/satisfaction question."""
    facts = user_data.setdefault("facts", {})
    if facts.get("signup_link_sent"):
        return False
    if facts.get("pre_signup_question_asked") and _is_affirmation(question):
        return False
    return _is_enrolment_query(question) and not facts.get("pre_signup_question_asked")


def _pre_signup_check_reply(user_data, question: str) -> str:
    facts = user_data.setdefault("facts", {})
    facts["pre_signup_question_asked"] = True
    status = facts.get("student_status")
    campus = facts.get("campus")
    if status == "new":
        base = "Parfait. Avant de vous envoyer le formulaire, je veux juste m’assurer que vous partez dans le bon parcours : pour débuter, ce serait le **Niveau 1 | Praticien en massothérapie**."
    elif status == "trained":
        base = "Parfait. Avant de vous envoyer le formulaire, je veux juste confirmer le bon parcours : comme vous avez déjà une formation, on regarde généralement le **Niveau 2** en premier."
    else:
        base = "Parfait. Avant de vous envoyer le formulaire, je veux juste vous placer dans le bon parcours pour éviter de vous envoyer au mauvais endroit."
    if campus:
        follow = f"Vous voulez que je vous l’envoie pour {campus}, et il ne vous reste pas de question sur le programme avant de commencer ?"
    else:
        follow = "Vous commencez en massage, vous êtes déjà étudiant à l’AMS, ou vous avez déjà une formation ?"
    user_data["pending_offer"] = "Si la personne confirme après cette question pré-inscription, transmettre le formulaire d'inscription officiel. Si elle donne son statut/campus ou pose une question, répondre d'abord puis confirmer avant le formulaire."
    return f"{base}\n\n{follow}"


def _detect_level(question: str) -> str | None:
    q = _norm_chat(question)
    if any(x in q for x in ["niveau 3", "niveau trois", "n3", "orthotherapie", "orthothérapie"]):
        return "Niveau 3"
    if any(x in q for x in ["niveau 2", "niveau deux", "n2"]):
        return "Niveau 2"
    if any(x in q for x in ["niveau 1", "niveau un", "n1"]):
        return "Niveau 1"
    return None


def _detect_goal(question: str) -> str | None:
    """Detect transferable advisor goals so follow-ups keep the same lane."""
    q = _norm_chat(question)
    goal_patterns = [
        ("sport", ["massage sportif", "sportif", "sport", "athlete", "athlète", "athletes", "athlètes", "recuperation sportive", "récupération sportive", "performance", "entrainement", "entraînement"]),
        ("aromatherapy", ["aroma", "aromatherapie", "aromathérapie", "laromatherapie", "l aromatherapie", "l'aromatherapie", "laromathérapie", "l aromathérapie", "l'aromathérapie", "huiles essentielles", "huile essentielle"]),
        ("family", ["grossesse", "enceinte", "femme enceinte", "bébé", "bebe", "enfant", "enfants", "famille", "familial"]),
        ("spa", ["spa", "hotel", "hôtel", "salon", "massages relaxants", "soins relaxants"]),
        ("pain_mobility", ["douleur", "douleurs", "mobilite", "mobilité", "mouvement", "trigger", "myofascial", "myofasciale", "kinesitherapie", "kinésithérapie", "orthotherapie", "orthothérapie", "decongestion", "décongestion", "tension", "tensions", "musculaire", "musculaires", "therapeutique", "thérapeutique"]),
        ("stress", ["stress", "anti stress", "anti-stress", "detente", "détente", "relaxation", "relaxant", "anxiete", "anxiété", "calme", "bien etre", "bien-être"]),
        ("career", ["carriere", "carrière", "emploi", "travailler", "travail", "clinique", "ouvrir", "pratique", "cabinet", "a mon compte", "à mon compte", "professionnel", "professionnelle"]),
    ]
    for goal, patterns in goal_patterns:
        if any(x in q for x in patterns):
            return goal
    return None


def _goal_label(goal: str | None) -> str | None:
    return {
        "sport": "sport / performance",
        "stress": "stress / détente",
        "pain_mobility": "douleur / mobilité",
        "aromatherapy": "aromathérapie",
        "family": "grossesse / bébé / famille",
        "spa": "spa / relaxation",
        "career": "carrière / ouvrir sa pratique",
    }.get(goal or "")


def _goal_expansion(goal: str) -> str:
    label = _goal_label(goal) or goal
    return (
        f"La personne reste dans l'objectif {label}. Réponds en gardant ce contexte, sans redemander son objectif. "
        f"Présente le bundle AMS pertinent pour {label}, puis propose une seule prochaine étape utile. "
        "Ne pas envoyer vers le site web et ne pas dire que la liste manque."
    )


def _extract_conversation_facts(user_data, question: str):
    """Remember lightweight routing facts before choosing deterministic replies."""
    q = question.lower()
    facts = user_data.setdefault("facts", {})
    level = _detect_level(question)
    if level:
        facts["level"] = level
    goal = _detect_goal(question)
    if goal:
        facts["active_goal"] = goal
    for campus in ["Laval", "Montréal", "Montreal", "Québec", "Quebec", "Brossard", "Sherbrooke", "Terrebonne", "Drummondville", "Trois-Rivières", "Trois Rivieres"]:
        if campus.lower() in q:
            facts["campus"] = "Montréal" if campus == "Montreal" else "Québec" if campus == "Quebec" else "Trois-Rivières" if campus == "Trois Rivieres" else campus
            break


def _direct_flow_reply(user_data, question: str):
    """Deterministic closures for dates/registration so Scarlett does not loop on exact dates."""
    _extract_conversation_facts(user_data, question)
    q = _norm_chat(question)
    pending = user_data.get("pending_offer", "").lower()
    facts = user_data.get("facts", {})
    name = facts.get("name")
    campus = facts.get("campus")
    level = facts.get("level") or _detect_level(question) or "Niveau 1"
    prefix = f"Oui, {name}." if name and _is_affirmation(question) else "Oui."

    wants_dates = _is_dates_query(question) or (_is_affirmation(question) and any(x in pending for x in ["date", "dates", "session", "sessions"]))
    explicit_signup_pending = any(x in pending for x in ["transmettre le formulaire", "formulaire d'inscription officiel", "réserver sa place", "reserver sa place"])
    wants_signup = _is_enrolment_query(question) or (_is_affirmation(question) and explicit_signup_pending)
    wants_details = any(x in q for x in ["contenu", "détail", "detail", "détaillé", "detaille", "cours", "module", "modules", "apprendre"])
    if wants_details and not _is_enrolment_query(question):
        return None

    if wants_signup:
        if _needs_pre_signup_check(user_data, question):
            return (_pre_signup_check_reply(user_data, question), None, None)
        user_data.pop("pending_offer", None)
        facts["signup_link_sent"] = True
        facts.pop("pre_signup_question_asked", None)
        user_data["pending_offer"] = "Aider la personne avec une question précise sur le formulaire, le campus ou le paiement; ne pas retransmettre le formulaire sauf demande claire."
        return (
            f"{prefix} Pour commencer officiellement, le plus simple est de remplir le formulaire d’inscription AMS.\n\n"
            f"Vous pourrez choisir {campus} directement dans le formulaire. Les frais administratifs sont de 100 $ pour les programmes professionnels.\n\n"
            "Si vous voulez valider une date précise avant de soumettre, contactez l’AMS au 1 800 475-1964 ou via la page contact.",
            "Ouvrir le formulaire d’inscription",
            INSCRIPTION_URL,
        )

    if wants_dates:
        user_data.pop("pending_offer", None)
        campus_part = f" à **{campus}**" if campus else ""
        signature = f"dates:{level}:{campus or 'unknown'}"
        repeated_same_dates = facts.get("last_dates_signature") == signature
        facts["last_dates_signature"] = signature

        if level == "Niveau 1":
            base = (
                f"Pour le **Niveau 1**{campus_part}, les prochaines sessions débutent généralement en **septembre** et en **janvier**. "
                "Les horaires peuvent varier selon le campus et la formule choisie, donc les dates exactes doivent être confirmées avec l’AMS."
            )
        else:
            base = (
                f"Pour le **{level}**{campus_part}, les dates exactes doivent être confirmées directement avec l’AMS, "
                "car elles varient selon le campus, la cohorte et les préalables."
            )
            if level == "Niveau 3":
                base += " Le point important : le Niveau 3 vient après le Niveau 2 ou une équivalence."

        if repeated_same_dates:
            follow = "Je garde cette réponse en tête; je ne vais pas vous la répéter."
        else:
            follow = "Pour valider une date précise, le mieux est de contacter l’AMS au 1 800 475-1964 ou via la page contact."
        user_data["pending_offer"] = "Si la personne confirme, donner le contact AMS ou la page contact pour valider les dates exactes; ne pas répéter les mêmes dates générales."
        return (f"{base}\n\n{follow}", None, None)

    return None


def _is_new_student_intro(question: str) -> bool:
    q = _norm_chat(question)
    has_new = any(x in q for x in ["je suis nouveau", "je suis nouvelle", "je debute", "je débute", "debutant", "débutant", "nouveau ici", "nouvelle ici", "je commence"])
    explicit_request = any(x in q for x in [
        "combien", "prix", "coute", "coûte", "cout", "coût", "tarif", "total",
        "niveau", "niveaux", "3 niveau", "trois niveau", "orthotherapeute", "orthothérapeute",
        "contenu", "horaire", "date", "inscription", "formulaire"
    ])
    return has_new and not explicit_request and len(q) < 140


def _is_trained_student_intro(question: str) -> bool:
    q = _norm_chat(question)
    has_trained = any(x in q for x in [
        "je suis praticien", "je suis praticienne", "praticien en massage", "praticienne en massage",
        "je suis massothérapeute", "je suis massotherapeute", "j'ai deja une formation", "jai deja une formation",
        "j'ai déjà une formation", "deja praticien", "déjà praticien", "j'ai mon niveau 1", "jai mon niveau 1",
        "j'ai le niveau 1", "jai le niveau 1", "400 heures", "400h"
    ])
    explicit_request = any(x in q for x in [
        "combien", "prix", "coute", "coûte", "cout", "coût", "tarif", "total", "niveau 2", "niveau 3",
        "orthotherapeute", "orthothérapeute", "contenu", "horaire", "date", "inscription", "formulaire"
    ])
    return has_trained and not explicit_request and len(q) < 180


def _trained_student_intro_reply(user_data, question: str) -> str:
    _update_conversation_state(user_data, question, "")
    user_data["facts"]["student_status"] = "trained"
    user_data["pending_offer"] = "Présenter le parcours principal pour une personne déjà praticienne: Niveau 2 600 h à 7 345 $ en premier, puis Niveau 3 Orthothérapie avancée, puis les cours à la carte seulement comme compléments."
    return (
        "Parfait. Si vous êtes déjà praticien en massage, le parcours principal à regarder d’abord est le **Niveau 2** — c’est le programme complet de 600 heures, à **7 345 $**.\n\n"
        "Il y a deux branches principales :\n"
        "- **Masso-kinésithérapie spécialisation en sportif** : douleur, mouvement, biomécanique, clientèle sportive.\n"
        "- **Massothérapie avancée spécialisation anti-stress** : stress, détente thérapeutique, approche psychocorporelle.\n\n"
        "Ensuite vient le **Niveau 3 | Orthothérapie avancée**. Les petits cours à la carte peuvent être utiles, mais seulement comme compléments.\n\n"
        "Votre objectif est plutôt douleur/mouvement/sport, ou stress/détente thérapeutique ?"
    )


def _new_student_intro_reply(user_data, question: str) -> str:
    _update_conversation_state(user_data, question, "")
    name = user_data.get("facts", {}).get("name")
    prefix = f"Parfait, {name}." if name else "Parfait."
    user_data["pending_offer"] = "Répondre à la première question précise sur le Niveau 1; si la personne veut avancer, demander ensuite ville/campus et préférence d'horaire."
    return (
        f"{prefix} Le point de départ est généralement le **Niveau 1 | Praticien en massothérapie**.\n\n"
        "Qu’est-ce que vous aimeriez savoir en premier pour voir si ça vous convient ?"
    )


def _expand_followup_question(user_data, question: str) -> str:
    """Resolve short follow-ups like 'oui' or 'quelle est la liste' using recent topic."""
    q = _norm_chat(question)

    pending = user_data.pop("pending_offer", None) if _is_affirmation(question) else None
    if pending:
        p = pending.lower()
        if any(x in p for x in ["comment scarlett fonctionne", "comment elle oriente", "comment ça marche", "comment ca marche"]):
            return "Explique avec assurance comment Scarlett fonctionne comme réception AMS: elle situe le profil de la personne, explique le bon parcours, donne les prix/campus/dates générales/inscription, puis propose une prochaine étape simple. Si la personne débute, commence par Niveau 1: 400 h, format hybride, 4 995 $. Ne pas envoyer vers un conseiller ni le formulaire sauf demande claire."
        if any(x in p for x in ["orienter doucement", "aperçu débutant", "apercu debutant", "mode découverte", "mode decouverte"]):
            return "La personne est perdue et veut d'abord comprendre. Explique doucement le parcours habituel Niveau 1: à qui ça s'adresse, durée 400 h, prix 4 995 $, format hybride, et demande ce qui compte le plus pour elle (rythme, budget, contenu ou campus). Reste en mode découverte; ne pousse pas vers une action administrative."
        if any(x in p for x in ["première question", "premiere question", "répondre à la première", "voir si ça vous convient", "voir si ca vous convient"]):
            return "Donne un aperçu utile du Niveau 1 pour aider la personne à découvrir le parcours avant toute inscription: prix, durée, format hybride, contenu principal et bénéfices. Termine par une question ouverte sur ce qui compte le plus pour elle (rythme, budget, contenu, campus), sans proposer le formulaire."
        if any(x in p for x in ["stage", "stages", "pratique", "international", "étranger", "etranger", "france", "modalités pour étudiant international"]):
            return "Explique les modalités pour une personne en France qui veut étudier au Niveau 1: théorie 100 % en ligne, pratique à faire au Québec sur campus pendant les périodes intensives, bénéfices du format hybride, et pose une question ouverte pour savoir ce qui compte le plus pour elle (voyage, rythme, budget, reconnaissance). Ne donne pas le formulaire sauf si elle demande clairement à s'inscrire."
        if any(x in p for x in ["parcours principal", "déjà praticienne", "deja praticienne", "déjà praticien", "deja praticien", "niveau 2 600 h", "niveau 2 600"]):
            return "Présente le parcours principal pour quelqu'un déjà praticien en massage, dans cet ordre: Niveau 2 600 h à 7 345 $ d'abord (sportif ou anti-stress), puis Niveau 3 Orthothérapie avancée, puis cours à la carte seulement comme compléments. Demande ensuite si son objectif est plutôt douleur/mouvement/sport ou stress/détente thérapeutique."
        if any(x in p for x in ["question pré-inscription", "pre inscription", "pré-inscription", "transmettre le formulaire d'inscription officiel"]):
            return "La personne confirme après la question pré-inscription. Transmets maintenant le formulaire d'inscription officiel AMS, rappelle brièvement qu'elle pourra choisir le campus dans le formulaire, et reste disponible pour une question sur programme/campus/paiement."
        if any(x in p for x in ["details", "détails", "prix", "contenu"]):
            return "Donne les détails du parcours habituel pour débuter: Niveau 1 | Praticien en massothérapie, prix, durée, format hybride, contenu principal, et prochaine étape simple. Ne propose pas le formulaire sauf demande claire d'inscription."
        return pending

    vague_list = q in {
        "quelle est la liste", "c'est quoi la liste", "cest quoi la liste",
        "la liste", "liste", "quels sont-ils", "quelles sont-elles"
    }
    recent = "\n".join(
        f"{t.get('q','')} {t.get('a','')}" for t in user_data.get("recent_turns", [])[-3:]
    ).lower()
    content_followup = any(x in q for x in ["contenu", "dans le cours", "du cours", "apprend", "apprendre", "plus d'info", "plus info", "parler du cours", "info sur le contenu", "information sur le contenu"])
    facts = user_data.get("facts", {})
    active_goal = facts.get("active_goal")
    current_goal = _detect_goal(question)
    recent_aromatherapy = any(x in recent for x in ["aromatherapie", "aromathérapie", "huiles essentielles", "huile essentielle"])
    explicitly_not_main_path = any(x in q for x in ["pas praticien", "pas practicien", "pas le praticien", "pas niveau 1", "pas le niveau 1"])
    explicitly_main_path = any(x in q for x in ["niveau 1", "praticien en massotherapie", "praticien en massothérapie"])

    if explicitly_not_main_path and (current_goal == "aromatherapy" or recent_aromatherapy):
        facts["active_goal"] = "aromatherapy"
        facts.pop("level", None)
        if facts.get("student_status") == "trained":
            facts.pop("student_status", None)
        user_data["_allow_repeat_once"] = True
        return "Quel est le contenu des cours d'aromathérapie à la carte? Explique Aromathérapie : les bases, Aromathérapie clinique et scientifique 1, et le forfait bases + clinique/scientifique 1. Reste sur ces cours à la carte; ne parle pas du parcours principal."

    if content_followup and (current_goal == "aromatherapy" or active_goal == "aromatherapy" or (recent_aromatherapy and not explicitly_main_path)):
        facts["active_goal"] = "aromatherapy"
        user_data["_allow_repeat_once"] = True
        return "Quel est le contenu des cours d'aromathérapie à la carte? Explique Aromathérapie : les bases, Aromathérapie clinique et scientifique 1, et le forfait bases + clinique/scientifique 1. Reste sur ces cours à la carte; ne parle pas du parcours principal."

    if active_goal and content_followup:
        return _goal_expansion(active_goal)

    if content_followup and ("niveau 1" in recent or user_data.get("facts", {}).get("student_status") == "new"):
        return "Quel est le contenu et les objectifs du Niveau 1 | Praticien en massothérapie? Parle du cours: anatomie, massage suédois, aromathérapie, éthique, lois, protocole MOST et stages."

    goal_followup = vague_list or q in {
        "oui", "ok", "d'accord", "dac", "parfait", "continue", "vas-y", "go",
        "quoi d'autre", "quoi d’autre", "et apres", "et après", "la suite",
        "quel cours", "quels cours", "lesquels", "lequel", "que choisir", "tu proposes quoi"
    }
    if active_goal and goal_followup:
        return _goal_expansion(active_goal)

    if vague_list:
        if any(word in recent for word in ["campus", "collège", "college", "adresse"]):
            return "Quelle est la liste des campus AMS avec les adresses?"
    return question


def _remember_pending_offer(user_data, question: str, answer: str):
    """Keep the last single offered next step so a bare 'oui' can move forward."""
    import html as _html
    import re
    text = _html.unescape(answer or "")
    clean = re.sub(r"<[^>]+>", "", text).lower()
    q = _norm_chat(question)

    offer = None
    signup_already_sent = user_data.get("facts", {}).get("signup_link_sent")
    if any(x in clean for x in ["stages pratiques", "stages pratique", "partie pratique", "formation pratique", "étudiant international", "etranger", "étranger", "france", "modalités d'inscription", "modalites d'inscription"]):
        offer = "Expliquer les stages/la pratique au Québec et les modalités pour une personne à l'étranger; poser ensuite une question ouverte sur ce qui compte le plus (voyage, rythme, budget, reconnaissance). Ne pas envoyer le formulaire sauf demande claire."
    elif any(x in clean for x in ["détails du parcours", "details du parcours", "prix et le contenu", "prix et contenu", "détails et prix", "details et prix"]):
        offer = "Donne les détails du parcours habituel pour débuter: Niveau 1 | Praticien en massothérapie, prix, durée, format hybride, contenu principal, et prochaine étape simple."
    elif any(x in clean for x in ["formulaire", "s'inscrire", "s’inscrire", "réserver", "reserver", "ma place", "lien d'inscription", "lien d’inscription"]):
        offer = "Aider avec une question précise sur le formulaire, le campus ou le paiement; ne pas retransmettre le formulaire sauf demande claire." if signup_already_sent else "Transmettre le formulaire d'inscription officiel si la personne veut commencer ou réserver sa place."
    elif any(x in clean for x in ["horaire", "horaires", "prochaine date", "prochaines dates", "dates disponibles", "session", "sessions"]):
        offer = "Donner les mois généraux des prochaines sessions et expliquer que les dates exactes doivent être confirmées avec l'AMS; ne pas prétendre vérifier en temps réel."
    elif any(x in clean for x in ["conseiller", "conseillère", "suivi"]):
        offer = "Donner le contact AMS ou la page contact pour parler à un conseiller."
    elif any(x in clean for x in ["niveau 1", "4 995", "4995", "prix", "coût", "cout"]):
        offer = "Demander la ville et la préférence d'horaire, puis orienter vers le campus ou le formulaire d'inscription si la personne est prête."
    elif any(x in clean for x in ["campus", "adresse", "plus proche"]):
        offer = "Donner la prochaine information utile sur ce campus: adresse, formulaire d'inscription ou contact AMS, selon le dernier contexte."

    goal = _detect_goal(answer) or user_data.get("facts", {}).get("active_goal")
    if goal and any(x in clean for x in ["cours à la carte pertinents", "cours a la carte pertinents", "voie principale", "parcours plus complet", "objectif", "spécialiser votre offre", "specialiser votre offre"]):
        user_data.setdefault("facts", {})["active_goal"] = goal
        label = _goal_label(goal) or goal
        offer = f"Continuer dans l'objectif {label}: aider à choisir le meilleur cours ou expliquer le parcours complet associé, sans redemander l'objectif et sans envoyer vers le site web."

    # Do not let generic yes after tiny greetings trigger a product answer.
    if offer and not _is_greeting(question):
        user_data["pending_offer"] = offer


def _update_conversation_state(user_data, question: str, answer: str):
    import re
    _extract_conversation_facts(user_data, question)
    q = question.lower()
    facts = user_data.setdefault("facts", {})
    if _is_capability_query(question) or _is_how_it_works_query(question) or _is_old_bot_query(question) or _is_assumption_challenge(question) or _is_lost_query(question):
        turns = user_data.setdefault("recent_turns", [])
        turns.append({"q": question, "a": answer})
        del turns[:-5]
        return
    if any(x in q for x in ["je débute", "je debute", "je suis nouveau", "je suis nouvelle", "nouveau", "nouvelle", "débutant", "debutant", "je commence", "aucune formation", "pas de formation"]):
        facts["student_status"] = "new"
    if any(x in q for x in ["j'ai déjà", "jai deja", "déjà une formation", "deja une formation", "je suis massothérapeute", "je suis massotherapeute", "massotherapeute", "massothérapeute", "praticien en massage", "praticienne en massage", "niveau 1", "niveau 2", "400 heures", "400h"]):
        if facts.get("student_status") != "new" or any(x in q for x in ["niveau 1", "niveau 2", "massothérapeute", "massotherapeute", "praticien", "praticienne", "déjà", "deja", "400"]):
            facts["student_status"] = "trained"
    goal = _detect_goal(question)
    if goal:
        facts["active_goal"] = goal
    for campus in ["Laval", "Montréal", "Montreal", "Québec", "Quebec", "Brossard", "Sherbrooke", "Terrebonne", "Drummondville", "Trois-Rivières", "Trois Rivieres"]:
        if campus.lower() in q:
            facts["campus"] = "Montréal" if campus == "Montreal" else "Québec" if campus == "Quebec" else "Trois-Rivières" if campus == "Trois Rivieres" else campus
            break
    m = re.search(r"(?:je m'appelle|mon nom est|mon prénom est|mon prenom est|c'est|moi c'est)\s+([A-Za-zÀ-ÿ'’-]{2,30})", question, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().title()
        if candidate.lower() not in {"oui", "non", "ok", "parfait"}:
            facts["name"] = candidate
    _remember_pending_offer(user_data, question, answer)
    turns = user_data.setdefault("recent_turns", [])
    turns.append({"q": question, "a": answer})
    del turns[:-5]


async def handle_voice_disabled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat-only mode: ask users to type instead of processing voice."""
    await update.message.reply_text("Je suis en mode écrit pour l’instant. Pouvez-vous m’envoyer votre question en texte ?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages — the main Q&A flow."""
    question = update.message.text.strip()
    lang = context.user_data.get("lang", RESPONSE_LANGUAGE)
    # Text messages always receive text replies.

    # Handle greetings locally; do not send small talk through RAG.
    if _is_greeting(question):
        context.user_data["welcomed"] = True
        # Social small-talk should not accidentally accept a pending guided offer.
        context.user_data.pop("pending_offer", None)
        if context.user_data.get("welcomed_once"):
            await update.message.reply_text("Ça va très bien, merci. Quelle information AMS souhaitez-vous vérifier ?")
        else:
            context.user_data["welcomed_once"] = True
            await update.message.reply_text("Bonjour, je suis Scarlett. Je peux vous aider à trouver le bon parcours à l’AMS.")
        return

    if _is_repeat_complaint(question):
        answer = _repeat_complaint_reply(context.user_data)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_capability_query(question):
        answer = _capability_reply(context.user_data)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_how_it_works_query(question):
        answer = _how_it_works_reply(context.user_data)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_old_bot_query(question):
        answer = _old_bot_reply(context.user_data, question)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_assumption_challenge(question):
        answer = _assumption_challenge_reply(context.user_data)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_lost_query(question):
        answer = _lost_reply(context.user_data)
        _update_conversation_state(context.user_data, question, answer)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_new_student_intro(question):
        answer = _new_student_intro_reply(context.user_data, question)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    if _is_trained_student_intro(question):
        answer = _trained_student_intro_reply(context.user_data, question)
        await update.message.reply_text(_chat_safe(answer), parse_mode="HTML")
        return

    direct = _direct_flow_reply(context.user_data, question)
    if direct:
        answer, button_text, url = direct
        _update_conversation_state(context.user_data, question, answer)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=url)]]) if button_text and url else None
        await update.message.reply_text(
            _chat_safe(answer),
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        conv_ctx = _conversation_context(context.user_data)
        question_for_rag = _expand_followup_question(context.user_data, question)
        payload = {"question": question_for_rag, "language": lang}
        if conv_ctx:
            payload["conversation_context"] = conv_ctx
        resp = requests.post(
            f"{RAG_SERVICE_URL}/ask",
            json=payload,
            timeout=30
        )

        if resp.status_code == 200:
            data = resp.json()
            answer = _smooth_guided_offer(_chat_safe(data.get("answer", "I couldn't process that question."), strip_intro=True))
            answer = _de_repeat_answer(context.user_data, answer)
            sources = data.get("sources", [])
            refused = data.get("refused", False)

            # Format text response (used as fallback and for text mode)
            message = answer

            # Internal source names are never shown to customers.

            # Telegram message limit
            if len(message) > 4000:
                message = message[:3997] + "..."

            _update_conversation_state(context.user_data, question, answer)
            # Text messages always get written replies. Voice is reserved for voice memos.
            await update.message.reply_text(message, parse_mode="HTML")
        else:
            await update.message.reply_text("Sorry, I couldn't process your question right now.")

    except requests.exceptions.Timeout:
        await update.message.reply_text("That took too long. Try a simpler question.")
    except requests.exceptions.ConnectionError:
        await update.message.reply_text("The knowledge service is offline. Please try again later.")
    except Exception as e:
        logger.error(f"Message error: {e}")
        await update.message.reply_text("Something went wrong. Please try again.")


def main():
    token = BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set. Create a bot via @BotFather and set the env var.")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_disabled))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🛎️ Scarlett — Receptionist Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
