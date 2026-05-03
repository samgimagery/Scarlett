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
    q = question.lower().strip()
    q = re.sub(r"[!?.,]+$", "", q).strip()
    greeting_patterns = [
        r"^(hello|hi|hey|bonjour|salut|coucou|yo|howdy)$",
        r"^(hello|hi|hey|bonjour|salut|coucou|yo)[, ]+(how are you|how are you doing|ça va|ca va|comment ça va|comment ca va|tu vas bien|vous allez bien)$",
        r"^(how are you|how are you doing|ça va|ca va|comment ça va|comment ca va|tu vas bien|vous allez bien)$",
    ]
    return any(re.match(p, q) for p in greeting_patterns) or len(q) < 3


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
    if facts.get("signup_link_sent"):
        parts.append("Le lien/formulaire d'inscription vient déjà d'être transmis. Ne pas le reproposer tout de suite sauf si la personne le redemande clairement; proposer plutôt de répondre aux questions ou clarifier le contenu/horaire.")
    if user_data.get("pending_offer"):
        parts.append(f"Dernière offre active: {user_data['pending_offer']}. Si la personne répond seulement oui/ok, continuer avec cette offre sans répéter le choix.")
    last = user_data.get("recent_turns", [])[-3:]
    if last:
        parts.append("Derniers échanges résumés:")
        for t in last:
            parts.append(f"- Client: {t.get('q','')[:140]} | Scarlett: {t.get('a','')[:220]}")
    return "\n".join(parts)


def _norm_chat(text: str) -> str:
    import re
    q = (text or "").lower().strip()
    q = q.replace("’", "'")
    q = re.sub(r"[!?.,]+$", "", q).strip()
    return re.sub(r"\s+", " ", q)


def _is_affirmation(question: str) -> bool:
    q = _norm_chat(question)
    affirmations = {
        "oui", "yes", "yep", "yeah", "ok", "okay", "d'accord", "dac",
        "parfait", "vas-y", "vas y", "allez", "go", "oui svp",
        "oui s'il vous plait", "oui s'il te plait", "oui merci"
    }
    return q in affirmations or (q.startswith("oui") and len(q) <= 40) or ("d'accord" in q and len(q) <= 40)


def _is_dates_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in ["date", "dates", "session", "sessions", "quand", "debut", "début", "horaire", "horaires"])


def _is_enrolment_query(question: str) -> bool:
    q = _norm_chat(question)
    return any(x in q for x in ["inscription", "inscrire", "m'inscrire", "minscrire", "formulaire", "lien", "site web", "comment je fais", "comment faire", "réserver", "reserver", "ma place", "place"])


def _direct_flow_reply(user_data, question: str):
    """Deterministic closures for dates/registration so Scarlett does not loop on exact dates."""
    q = _norm_chat(question)
    pending = user_data.get("pending_offer", "").lower()
    facts = user_data.get("facts", {})
    name = facts.get("name")
    campus = facts.get("campus") or "le campus choisi"
    prefix = f"Oui, {name}." if name and _is_affirmation(question) else "Oui."

    wants_dates = _is_dates_query(question) or (_is_affirmation(question) and any(x in pending for x in ["date", "dates", "session", "sessions"]))
    explicit_signup_pending = any(x in pending for x in ["transmettre le formulaire", "formulaire d'inscription officiel", "réserver sa place", "reserver sa place"])
    wants_signup = _is_enrolment_query(question) or (_is_affirmation(question) and explicit_signup_pending)
    wants_details = any(x in q for x in ["contenu", "détail", "detail", "détaillé", "detaille", "cours", "module", "modules", "apprendre"])
    if wants_details and not _is_enrolment_query(question):
        return None

    if wants_signup:
        user_data.pop("pending_offer", None)
        facts["signup_link_sent"] = True
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
        user_data["pending_offer"] = "Continuer la découverte: aider à choisir selon rythme, budget, contenu ou campus; ne transmettre le formulaire que sur demande claire."
        return (
            "Pour le **Niveau 1**, les prochaines sessions débutent généralement en **septembre** et en **janvier**. "
            "Les horaires peuvent varier selon le campus et la formule choisie, donc les dates exactes doivent être confirmées avec l’AMS.\n\n"
            f"Pour {campus}, le plus utile avant de s’inscrire est de choisir la formule qui vous convient : semaine, fin de semaine ou accélérée.\n\n"
            "Qu’est-ce qui compte le plus pour vous en ce moment : le rythme, le budget, le contenu du cours ou le campus ?",
            None,
            None,
        )

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
        if any(x in p for x in ["première question", "premiere question", "répondre à la première", "voir si ça vous convient", "voir si ca vous convient"]):
            return "Donne un aperçu utile du Niveau 1 pour aider la personne à découvrir le parcours avant toute inscription: prix, durée, format hybride, contenu principal et bénéfices. Termine par une question ouverte sur ce qui compte le plus pour elle (rythme, budget, contenu, campus), sans proposer le formulaire."
        if any(x in p for x in ["stage", "stages", "pratique", "international", "étranger", "etranger", "france", "modalités pour étudiant international"]):
            return "Explique les modalités pour une personne en France qui veut étudier au Niveau 1: théorie 100 % en ligne, pratique à faire au Québec sur campus pendant les périodes intensives, bénéfices du format hybride, et pose une question ouverte pour savoir ce qui compte le plus pour elle (voyage, rythme, budget, reconnaissance). Ne donne pas le formulaire sauf si elle demande clairement à s'inscrire."
        if any(x in p for x in ["parcours principal", "déjà praticienne", "deja praticienne", "déjà praticien", "deja praticien", "niveau 2 600 h", "niveau 2 600"]):
            return "Présente le parcours principal pour quelqu'un déjà praticien en massage, dans cet ordre: Niveau 2 600 h à 7 345 $ d'abord (sportif ou anti-stress), puis Niveau 3 Orthothérapie avancée, puis cours à la carte seulement comme compléments. Demande ensuite si son objectif est plutôt douleur/mouvement/sport ou stress/détente thérapeutique."
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
    content_followup = any(x in q for x in ["contenu", "dans le cours", "du cours", "apprend", "apprendre", "plus d'info", "plus info", "parler du cours"])
    if content_followup and ("niveau 1" in recent or user_data.get("facts", {}).get("student_status") == "new"):
        return "Quel est le contenu et les objectifs du Niveau 1 | Praticien en massothérapie? Parle du cours: anatomie, massage suédois, aromathérapie, éthique, lois, protocole MOST et stages."

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
    elif any(x in clean for x in ["formulaire", "inscription", "s'inscrire", "site web", "lien"]):
        offer = "Aider avec une question précise sur le formulaire, le campus ou le paiement; ne pas retransmettre le formulaire sauf demande claire." if signup_already_sent else "Transmettre le formulaire d'inscription officiel si la personne veut commencer ou réserver sa place."
    elif any(x in clean for x in ["horaire", "horaires", "prochaine date", "prochaines dates", "dates disponibles", "session", "sessions"]):
        offer = "Donner les mois généraux des prochaines sessions et expliquer que les dates exactes doivent être confirmées avec l'AMS; ne pas prétendre vérifier en temps réel."
    elif any(x in clean for x in ["conseiller", "conseillère", "suivi"]):
        offer = "Donner le contact AMS ou la page contact pour parler à un conseiller."
    elif any(x in clean for x in ["niveau 1", "4 995", "4995", "prix", "coût", "cout"]):
        offer = "Demander la ville et la préférence d'horaire, puis orienter vers le campus ou le formulaire d'inscription si la personne est prête."
    elif any(x in clean for x in ["campus", "adresse", "plus proche"]):
        offer = "Donner la prochaine information utile sur ce campus: adresse, formulaire d'inscription ou contact AMS, selon le dernier contexte."

    # Do not let generic yes after tiny greetings trigger a product answer.
    if offer and not _is_greeting(question):
        user_data["pending_offer"] = offer


def _update_conversation_state(user_data, question: str, answer: str):
    import re
    q = question.lower()
    facts = user_data.setdefault("facts", {})
    if any(x in q for x in ["je débute", "je debute", "je suis nouveau", "je suis nouvelle", "nouveau", "nouvelle", "débutant", "debutant", "je commence", "aucune formation", "pas de formation"]):
        facts["student_status"] = "new"
    if any(x in q for x in ["j'ai déjà", "jai deja", "déjà une formation", "deja une formation", "je suis massothérapeute", "je suis massotherapeute", "massotherapeute", "massothérapeute", "praticien en massage", "praticienne en massage", "niveau 1", "niveau 2", "400 heures", "400h"]):
        if facts.get("student_status") != "new" or any(x in q for x in ["niveau 1", "niveau 2", "massothérapeute", "massotherapeute", "praticien", "praticienne", "déjà", "deja", "400"]):
            facts["student_status"] = "trained"
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
        if context.user_data.get("welcomed_once"):
            await update.message.reply_text("Oui, je suis là. Quelle information AMS souhaitez-vous vérifier ?")
        else:
            context.user_data["welcomed_once"] = True
            await update.message.reply_text("Bonjour, je suis Scarlett. Je peux vous aider à trouver le bon parcours à l’AMS.")
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