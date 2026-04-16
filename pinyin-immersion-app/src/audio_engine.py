# src/audio_engine.py

import asyncio
import edge_tts
import logging
import random
import re

from config import DATA_DIR

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
AUDIO_PATH = DATA_DIR / "current_audio.mp3"

# ==========================================
# THE EXPANDED VOICE CAST
# ==========================================
VOICE_CAST = [
    # Malaysia (Native Local)
    "zh-MY-XiaoxiaoNeural",  # Female
    "zh-MY-JianNeural",      # Male
    
    # Singapore (Virtually identical accent to Malaysia)
    "zh-SG-LunaNeural",      # Female
    "zh-SG-JianNeural",      # Male
    
    # Taiwan (Soft, highly comprehensible, zero Beijing slang)
    "zh-TW-HsiaoChenNeural", # Female
    "zh-TW-HsiaoYuNeural",   # Female (Different tone)
    "zh-TW-YunJheNeural"     # Male
]

async def _generate_audio_async(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def create_audio_file(chinese_text: str, voice: str = None):
    if not chinese_text or len(chinese_text.strip()) == 0:
        logging.error("Audio Engine received empty text. Skipping audio generation.")
        return None

    # Clean the text: Keep only Chinese characters and standard punctuation
    clean_text = re.sub(r'[^\u4e00-\u9fff，。！？、]', '', chinese_text)

    # Safety fallback if the filter strips everything
    if len(clean_text) == 0:
        logging.warning("Filter stripped all text! Falling back to raw text.")
        clean_text = chinese_text.strip()

    # ==========================================
    # THE MALAYSIAN PRONUNCIATION HACK
    # ==========================================
    # We swap "了" for "料" behind the scenes. 
    # The user sees "了" on screen, but the TTS reads the punchy local "liào" 
    tts_text = clean_text.replace("了", "料")

    selected_voice = voice if voice else random.choice(VOICE_CAST)
    logging.info(f"Attempting audio for: '{tts_text}' using {selected_voice}")

    try:
        asyncio.run(_generate_audio_async(tts_text, selected_voice, str(AUDIO_PATH)))
        return str(AUDIO_PATH)
        
    except Exception as e:
        logging.warning(f"Voice {selected_voice} failed. Trying fallback...")
        try:
            # Fallback to the most reliable standard voice if the API glitches
            asyncio.run(_generate_audio_async(tts_text, "zh-CN-XiaoxiaoNeural", str(AUDIO_PATH)))
            return str(AUDIO_PATH)
        except Exception as e_final:
            logging.error(f"Total Audio Failure: {e_final}")
            return None
