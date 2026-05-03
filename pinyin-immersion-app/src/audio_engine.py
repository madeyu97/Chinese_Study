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
    selected_voice = voice if voice else random.choice(VOICE_CAST)
    logging.info(f"Attempting audio for: '{tts_text}' using {selected_voice}")

    # 4. Generate Audio
    try:
        asyncio.run(_generate_audio_async(tts_text, selected_voice, str(AUDIO_PATH)))
        return str(AUDIO_PATH)
        
    except Exception as e:
        logging.warning(f"Voice {selected_voice} failed. Trying fallback...")
        try:
            # Final fallback to standard Mandarin if local voices fail
            asyncio.run(_generate_audio_async(tts_text, "zh-CN-XiaoxiaoNeural", str(AUDIO_PATH)))
            return str(AUDIO_PATH)
        except Exception as e_final:
            logging.error(f"Total Audio Failure: {e_final}")
            return None
