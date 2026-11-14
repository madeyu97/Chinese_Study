import asyncio
import edge_tts
import hashlib
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import clock
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
MAX_AUDIO_FILES = 400  # keep the most recent N files


def _prune_old_audio():
    try:
        files = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
        for stale in files[MAX_AUDIO_FILES:]:
            stale.unlink(missing_ok=True)
    except Exception as e:
        logging.warning(f"Audio prune failed (non-fatal): {e}")


# ==========================================
# THE EXPANDED VOICE CAST
# ==========================================
# NOTE: Microsoft Edge TTS has NO zh-MY or zh-SG Mandarin voices (Malaysia
# gets ms-MY Malay, Singapore gets en-SG English). The previous cast listed
# fabricated names that failed on every call and silently fell back to the
# mainland default. This cast is verified-real; Taiwan voices are the
# closest register to Southeast Asian Mandarin.
VOICE_CAST = [
    "zh-TW-HsiaoChenNeural",  # Taiwan Female
    "zh-TW-HsiaoYuNeural",    # Taiwan Female
    "zh-TW-YunJheNeural",     # Taiwan Male
    "zh-CN-XiaoxiaoNeural",   # Mainland Female
    "zh-CN-XiaoyiNeural",     # Mainland Female
    "zh-CN-YunxiNeural",      # Mainland Male
    "zh-CN-YunyangNeural",    # Mainland Male
]

# Voices that error get benched for the rest of the process, so a broken
# voice costs one failed call ever, not one per card.
_DEAD_VOICES = set()

# ==========================================================================
# SPEED: making a clip takes a second or two, and it used to happen while
# the learner waited, for every card - with the voice picked at random each
# time, so a clip made earlier was rarely the one asked for again.
#
# Now the voice for a text is fixed for the day (still varied from text to
# text and day to day), so every later request finds the first clip; and
# pages call warm() with the texts coming up, which makes them in the
# background before they are needed.
# ==========================================================================
_PATH_LOCKS, _PATH_LOCKS_GUARD = {}, threading.Lock()
_WARMER = None
_WARMING = set()


def _voice_for(tts_text):
    alive = [v for v in VOICE_CAST if v not in _DEAD_VOICES] or VOICE_CAST
    n = int(hashlib.md5(f"{tts_text}|{clock.today().isoformat()}".encode("utf-8")).hexdigest(), 16)
    return alive[n % len(alive)]


def _lock_for(path):
    with _PATH_LOCKS_GUARD:
        if len(_PATH_LOCKS) > 2000:
            _PATH_LOCKS.clear()
        return _PATH_LOCKS.setdefault(str(path), threading.Lock())


def warm(texts):
    """Make these clips in the background, ahead of when they're played.
    Never raises and never waits. (Does nothing under NO_BACKGROUND, which
    the tests set.)"""
    global _WARMER
    if os.environ.get("NO_BACKGROUND"):
        return
    try:
        with _PATH_LOCKS_GUARD:
            if _WARMER is None:
                _WARMER = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts")
            todo = [t for t in dict.fromkeys(texts or []) if t and t.strip() and t not in _WARMING]
            _WARMING.update(todo)

        def one(text):
            try:
                create_audio_file(text)
            finally:
                _WARMING.discard(text)
        for t in todo:
            _WARMER.submit(one, t)
    except Exception as e:
        logging.warning(f"Audio warm-up skipped (non-fatal): {e}")


async def _generate_audio_async(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def _saved_ok(path) -> bool:
    """edge-tts can leave a zero-byte file behind on failure."""
    try:
        return os.path.exists(path) and os.path.getsize(path) > 1024
    except OSError:
        return False


def create_audio_file(chinese_text: str, voice: str = None):
    if not chinese_text or len(chinese_text.strip()) == 0:
        logging.error("Audio Engine received empty text.")
        return None

    # 1. Clean the text but KEEP spaces, English letters, and BOTH halfwidth
    #    and fullwidth punctuation (the old regex stripped ，！？ so the TTS
    #    lost the pauses and question intonation of most Chinese sentences).
    clean_text = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9,。!?、\s，！？；：]', '', chinese_text)

    if len(clean_text.strip()) == 0:
        logging.warning("Filter stripped all text! Falling back to raw text.")
        clean_text = chinese_text

    # 2. Apply Malaysian Spoofer.
    #    了 -> 料 forces the TTS to say "liǎo/liào" instead of "le",
    #    matching the Malaysian reading shown in the pinyin. But NOT in
    #    了解 — the TTS already reads that correctly as liǎojiě, and
    #    substituting would produce the non-word 料解.
    tts_text = re.sub(r'了(?!解)', '料', clean_text)
    tts_text = tts_text.replace("咩", " meh ")

    # 3. Select Voice (skipping any that have already failed this session):
    #    the same one all day for the same text, so clips are reused
    selected_voice = voice or _voice_for(tts_text)

    # 4. Unique output path per (text, voice) so history never goes stale
    digest = hashlib.md5(f"{tts_text}|{selected_voice}".encode("utf-8")).hexdigest()[:16]
    output_path = AUDIO_DIR / f"tts_{digest}.mp3"

    if _saved_ok(output_path):
        logging.info(f"Audio cache hit for: '{tts_text}'")
        return str(output_path)

    # one maker per clip: a request for a clip already being made in the
    # background waits for that one instead of making it twice
    with _lock_for(output_path):
        if _saved_ok(output_path):
            return str(output_path)
        return _make_clip(tts_text, selected_voice, output_path)


def _make_clip(tts_text, selected_voice, output_path):
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
                f"{tts_text}|zh-CN-XiaoxiaoNeural".encode("utf-8")).hexdigest()[:16]
            fallback_path = AUDIO_DIR / f"tts_{fallback_digest}.mp3"
            asyncio.run(_generate_audio_async(tts_text, "zh-CN-XiaoxiaoNeural", str(fallback_path)))
            if not _saved_ok(fallback_path):
                raise RuntimeError("Fallback TTS produced an empty file")
            _prune_old_audio()
            return str(fallback_path)
        except Exception as e_final:
            logging.error(f"Total Audio Failure: {e_final}")
            return None
