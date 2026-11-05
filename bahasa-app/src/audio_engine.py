import asyncio
import edge_tts
import hashlib
import logging
import os
import random
import re
from config import DATA_DIR

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ==========================================================================
# AUDIO FILES ARE NOW UNIQUE PER SENTENCE.
#
# The old design wrote every generation to ONE file (current_audio.mp3).
# Because main_app stores per-card audio paths in audio_history, every
# history entry pointed at the same file — whose contents were whatever was
# generated most recently. After an Undo, a card edit/regeneration, or a
# session restored from cache, the audio played a COMPLETELY DIFFERENT
# sentence than the one displayed on screen.
#
# Now each (sentence, voice) pair gets its own file, so history entries stay
# valid forever within the retention window.
# ==========================================================================
AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
MAX_AUDIO_FILES = 120  # keep the most recent N files


def _prune_old_audio():
    try:
        files = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
        for stale in files[MAX_AUDIO_FILES:]:
            stale.unlink(missing_ok=True)
    except Exception as e:
        logging.warning(f"Audio prune failed (non-fatal): {e}")


# ==========================================
# THE VOICE CAST
# ==========================================
# Microsoft Edge TTS has two Malaysian Malay voices. Both read in a
# standard, newsreader style; colloquial forms (tak, nak, dah) come out
# understandable but formal. Google Cloud's ms-MY voices are the paid
# fallback if that matters (see the plan's risk table).
VOICE_CAST = [
    "ms-MY-YasminNeural",   # female
    "ms-MY-OsmanNeural",    # male
]
FALLBACK_VOICE = "ms-MY-YasminNeural"

# Voices that error get benched for the rest of the process, so a broken
# voice costs one failed call ever, not one per card.
_DEAD_VOICES = set()

async def _generate_audio_async(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def _saved_ok(path) -> bool:
    """edge-tts can leave a zero-byte file behind on failure."""
    try:
        return os.path.exists(path) and os.path.getsize(path) > 1024
    except OSError:
        return False


def create_audio_file(text: str, voice: str = None):
    """An mp3 of `text` read by a Malaysian voice; the file path, or None."""
    if not text or len(text.strip()) == 0:
        logging.error("Audio Engine received empty text.")
        return None

    # 1. Keep letters (accented ones too, for loanwords), digits, hyphens and
    #    sentence punctuation, which carries the pauses and question tone.
    clean_text = re.sub(r"[^A-Za-zÀ-ÿ0-9\s,.!?;:'\-]", "", text)
    if len(clean_text.strip()) == 0:
        logging.warning("Filter stripped all text! Falling back to raw text.")
        clean_text = text
    tts_text = clean_text.strip()

    # 3. Select Voice (skipping any that have already failed this session)
    if voice:
        selected_voice = voice
    else:
        alive = [v for v in VOICE_CAST if v not in _DEAD_VOICES]
        selected_voice = random.choice(alive if alive else VOICE_CAST)

    # 4. Unique output path per (text, voice) so history never goes stale
    digest = hashlib.md5(f"{tts_text}|{selected_voice}".encode("utf-8")).hexdigest()[:16]
    output_path = AUDIO_DIR / f"tts_{digest}.mp3"

    if _saved_ok(output_path):
        logging.info(f"Audio cache hit for: '{tts_text}'")
        return str(output_path)

    logging.info(f"Attempting audio for: '{tts_text}' using {selected_voice}")

    # 5. Generate Audio
    try:
        asyncio.run(_generate_audio_async(tts_text, selected_voice, str(output_path)))
        if not _saved_ok(output_path):
            raise RuntimeError("TTS produced an empty file")
        _prune_old_audio()
        return str(output_path)

    except Exception:
        _DEAD_VOICES.add(selected_voice)
        logging.warning(f"Voice {selected_voice} failed — benched for this "
                        f"session. Trying fallback...")
        try:
            fallback_digest = hashlib.md5(
                f"{tts_text}|{FALLBACK_VOICE}".encode("utf-8")).hexdigest()[:16]
            fallback_path = AUDIO_DIR / f"tts_{fallback_digest}.mp3"
            asyncio.run(_generate_audio_async(tts_text, FALLBACK_VOICE, str(fallback_path)))
            if not _saved_ok(fallback_path):
                raise RuntimeError("Fallback TTS produced an empty file")
            _prune_old_audio()
            return str(fallback_path)
        except Exception as e_final:
            logging.error(f"Total Audio Failure: {e_final}")
            return None
