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

    # 1. Clean the text but KEEP spaces (\s) and English letters (A-Za-z)
    # This is CRITICAL so the engine sees " meh " as a separate word.
    clean_text = re.sub(r'[^\u4e00-\u9fffA-Za-z，。！？、\s]', '', chinese_text)

    if len(clean_text.strip()) == 0:
        logging.warning("Filter stripped all text! Falling back to raw text.")
        clean_text = chinese_text

    # 2. Apply Malaysian Spoofer
    # Change "了" to "料" (耳 reads 'liào')
    tts_text = clean_text.replace("了", "料")
    
    # Change "咩" to " meh " (Ear reads the local particle)
    tts_text = tts_text.replace("咩", " meh ")

    # 3. Select Voice
@@ -30,7 +53,6 @@ def create_audio_file(chinese_text: str, voice: str = None):
    except Exception as e:
        logging.warning(f"Voice {selected_voice} failed. Trying fallback...")
        try:
            # Final fallback to standard Mandarin if local voices fail
            asyncio.run(_generate_audio_async(tts_text, "zh-CN-XiaoxiaoNeural", str(AUDIO_PATH)))
            return str(AUDIO_PATH)
        except Exception as e_final:
