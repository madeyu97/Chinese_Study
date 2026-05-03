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
    "zh-MY-XiaoxiaoNeural",  # Malaysia Female
    "zh-MY-JianNeural",      # Malaysia Male
    "zh-SG-LunaNeural",      # Singapore Female
    "zh-SG-JianNeural",      # Singapore Male
    "zh-TW-HsiaoChenNeural", # Taiwan Female
    "zh-TW-HsiaoYuNeural",   # Taiwan Female
    "zh-TW-YunJheNeural"     # Taiwan Male
]

async def _generate_audio_async(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def create_audio_file(chinese_text: str, voice: str = None):
    if not chinese_text or len(chinese_text.strip()) == 0:
        logging.error("Audio Engine received empty text.")
        return None

    # --- UPDATED REGEX ---
    # Now allows: 
    # 1. Chinese (\u4e00-\u9fff)
    # 2. Japanese Katakana (\u30a0-\u30ff) <-- Important for 'メ'
    # 3. English letters (a-zA-Z)
    # 4. Standard Punctuation
    clean_text = re.sub(r'[^\u4e00-\u9fff\u30a0-\u30ffa-zA-Z，。！？、]', '', chinese_text)

    if len(clean_text) == 0:
        logging.warning("Filter stripped all text! Falling back to raw text.")
        clean_text = chinese_text.strip()

    # ==========================================
    # THE MALAYSIAN PHONETIC SPOOFER
    # ==========================================
    # We alter the text ONLY for the ears, not the eyes.
    
    # 1. The "Liao" fix
    tts_text = clean_text.replace("了", "料")
    
    # 2. The "Meh" fix
    # We use the Japanese 'me' character for a crisp, short 'meh' sound
    tts_text = tts_text.replace("咩", "メ")

    selected_voice = voice if voice else random.choice(VOICE_CAST)
    logging.info(f"Attempting audio for: '{tts_text}' using {selected_voice}")

    try:
        asyncio.run(_generate_audio_async(tts_text, selected_voice, str(AUDIO_PATH)))
        return str(AUDIO_PATH)
        
    except Exception as e:
        logging.warning(f"Voice {selected_voice} failed. Trying fallback...")
        try:
            asyncio.run(_generate_audio_async(tts_text, "zh-CN-XiaoxiaoNeural", str(AUDIO_PATH)))
            return str(AUDIO_PATH)
        except Exception as e_final:
            logging.error(f"Total Audio Failure: {e_final}")
            return None
