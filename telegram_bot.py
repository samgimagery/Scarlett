"""
Receptionist Bot — Telegram Interface

Voice-first: sends voice replies by default, with source attribution as caption.
Use /voice off to switch to text-only mode.
Voice memos: transcribe with faster-whisper, then respond with TTS.
"""
import os
import asyncio
import tempfile
import requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from config import RAG_SERVICE_URL, RESPONSE_LANGUAGE, BOT_TOKEN
from tts import generate_voice, get_default_voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def _transcribe_audio(file_path, language="en"):
    """Transcribe audio file to text using faster-whisper."""
    model = _get_stt()
    lang_map = {"en": "en", "fr": "fr"}
    whisper_lang = lang_map.get(language, language)
    segments, _ = model.transcribe(file_path, language=whisper_lang, condition_on_previous_text=False)
    text = " ".join(s.text for s in segments).strip()
    return text

def _convert_ogg_to_wav(ogg_path, wav_path):
    """Convert OGG audio to WAV using ffmpeg."""
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-200:]}")
    return wav_path


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "🛎️ Scarlett — Vault Receptionist\n\n"
        "I answer questions from our vault. Voice replies by default.\n"
        "Send me a voice memo and I'll respond by voice!\n\n"
        "Just ask me anything!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "🛎️ Scarlett — Vault Receptionist\n\n"
        "I answer questions from our vault. Voice replies by default.\n\n"
        "Commands:\n"
        "/start — Introduction\n"
        "/help — This message\n"
        "/stats — Vault stats\n"
        "/lang en|fr — Switch language\n"
        "/voice on|off — Toggle voice replies"
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
                    f"📊 Vault Stats\n\n"
                    f"Notes: {notes}\n"
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
    """Handle /voice command to toggle voice replies."""
    if not context.args:
        current = context.user_data.get("voice", True)
        await update.message.reply_text(f"Voice replies: {'on 🔊' if current else 'off 🔇'}\nUsage: /voice on or /voice off")
        return
    
    setting = context.args[0].lower()
    if setting in ("on", "yes", "true", "1"):
        context.user_data["voice"] = True
        await update.message.reply_text("Voice replies on 🔊")
    elif setting in ("off", "no", "false", "0"):
        context.user_data["voice"] = False
        await update.message.reply_text("Voice replies off 🔇 Text only from now on.")
    else:
        await update.message.reply_text("Usage: /voice on or /voice off")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice memo messages — transcribe, then respond."""
    lang = context.user_data.get("lang", RESPONSE_LANGUAGE)
    voice_on = context.user_data.get("voice", True)
    
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
        
        # Transcribe
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        transcript = await asyncio.to_thread(_transcribe_audio, wav_path, lang)
        
        logger.info(f"Voice transcript: {transcript}")
        
        # Clean up audio files
        for p in [ogg_path, wav_path]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        ogg_path = wav_path = None
        
        if not transcript or len(transcript.strip()) < 2:
            await update.message.reply_text("I couldn't quite hear that. Could you try again?")
            return
        
        # Now process as text — same flow as handle_message
        question = transcript.strip()
        
        # Handle greetings
        greeting_words = {"hello", "hi", "hey", "bonjour", "salut", "good morning", "good evening", "howdy", "sup", "yo"}
        normalized = question.lower().rstrip("?!")
        if normalized in greeting_words or len(question) < 3:
            await update.message.reply_text("Hey! I'm Scarlett. Ask me anything about what's in the vault.")
            return
        
        # Show typing while we query RAG
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        resp = requests.post(
            f"{RAG_SERVICE_URL}/ask",
            json={"question": question, "language": lang},
            timeout=30
        )
        
        if resp.status_code != 200:
            await update.message.reply_text("Sorry, I couldn't process that right now.")
            return
        
        data = resp.json()
        answer = data.get("answer", "I couldn't process that question.")
        sources = data.get("sources", [])
        refused = data.get("refused", False)
        
        # Format text response
        message = answer
        if sources and not refused:
            source_names = [s.split('/')[-1].replace('.md', '') for s in sources]
            if len(source_names) == 1:
                message += f"\n\n📖 {source_names[0]}"
            else:
                message += f"\n\n📖 {', '.join(source_names)}"
        
        if len(message) > 4000:
            message = message[:3997] + "..."
        
        # Reply with voice (always voice reply to voice input)
        if answer and not refused:
            caption = ""
            if sources:
                source_names = [s.split('/')[-1].replace('.md', '') for s in sources]
                caption = "📖 " + ", ".join(source_names)
                if len(caption) > 200:
                    caption = caption[:197] + "..."
            
            # Show what we heard as context
            heard_text = f"🎤 \"{transcript}\"\n\n" if len(transcript) < 100 else ""
            
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
            voice_path = await asyncio.to_thread(
                generate_voice, answer, lang, get_default_voice(lang)
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
                    await update.message.reply_text(heard_text + message)
                finally:
                    try:
                        os.remove(voice_path)
                        parent = os.path.dirname(voice_path)
                        if os.path.isdir(parent) and parent.startswith(os.path.expanduser("~/Media/voices/tmp")):
                            os.rmdir(parent)
                    except:
                        pass
            else:
                await update.message.reply_text(heard_text + message)
        else:
            await update.message.reply_text(message)
    
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages — the main Q&A flow."""
    question = update.message.text.strip()
    lang = context.user_data.get("lang", RESPONSE_LANGUAGE)
    voice_on = context.user_data.get("voice", True)
    
    # Handle greetings — don't send these to the vault search
    greeting_words = {"hello", "hi", "hey", "bonjour", "salut", "good morning", "good evening", "howdy", "sup", "yo"}
    normalized = question.lower().rstrip("?!")
    if normalized in greeting_words or len(question) < 3:
        await update.message.reply_text("Hey! I'm Scarlett. Ask me anything about what's in the vault.")
        return
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        resp = requests.post(
            f"{RAG_SERVICE_URL}/ask",
            json={"question": question, "language": lang},
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            answer = data.get("answer", "I couldn't process that question.")
            sources = data.get("sources", [])
            refused = data.get("refused", False)
            
            # Format text response (used as fallback and for text mode)
            message = answer
            
            if sources and not refused:
                source_names = [s.split('/')[-1].replace('.md', '') for s in sources]
                if len(source_names) == 1:
                    message += f"\n\n📖 {source_names[0]}"
                else:
                    message += f"\n\n📖 {', '.join(source_names)}"
            
            # Telegram message limit
            if len(message) > 4000:
                message = message[:3997] + "..."
            
            # Voice mode: voice reply only, sources as caption
            # Text mode: text reply only
            if voice_on and answer and not refused:
                # Build caption with source attribution
                caption = ""
                if sources:
                    source_names = [s.split('/')[-1].replace('.md', '') for s in sources]
                    caption = "📖 " + ", ".join(source_names)
                if len(caption) > 200:
                    caption = caption[:197] + "..."
                
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
                voice_path = await asyncio.to_thread(
                    generate_voice, answer, lang, get_default_voice(lang)
                )
                if voice_path:
                    try:
                        with open(voice_path, 'rb') as audio_file:
                            await update.message.reply_voice(voice=audio_file, caption=caption or None)
                        logger.info(f"Voice sent: {voice_path}")
                    except Exception as e:
                        logger.warning(f"Failed to send voice: {e}")
                        # Voice failed, fall back to text
                        await update.message.reply_text(message)
                    finally:
                        try:
                            os.remove(voice_path)
                            parent = os.path.dirname(voice_path)
                            if os.path.isdir(parent) and parent.startswith(os.path.expanduser("~/Media/voices/tmp")):
                                os.rmdir(parent)
                        except:
                            pass
                else:
                    # Voice generation failed, send text
                    await update.message.reply_text(message)
            else:
                # Voice off or refusal — text only
                await update.message.reply_text(message)
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
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🛎️ Scarlett — Receptionist Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()