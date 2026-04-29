# src/ai_prompter.py

import os
import json
import logging
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def generate_dictation_exercise(target_word_dict):
    pinyin = target_word_dict.get('pinyin', '')
    english = target_word_dict.get('english', '')
    chinese_chars = target_word_dict.get('chinese', target_word_dict.get('hanzi', target_word_dict.get('characters', '')))
    
    is_locked_phrase = len(chinese_chars) > 3
    
    if is_locked_phrase:
        behavior_prompt = f"""
        LOCKED SENTENCE: '{chinese_chars}' 
        Meaning: '{english}'
        
        CRITICAL RULES FOR THIS SENTENCE: 
        1. DO NOT alter the Chinese characters. Analyze EXACTLY '{chinese_chars}' and NOTHING ELSE.
        2. PINYIN ACCURACY: You MUST generate Pinyin that perfectly matches these characters. Do NOT hallucinate Pinyin for words that aren't there (e.g., ensure 杯子 is 'bēi zi').
        3. THE "了" RULE: If this sentence contains the character '了', you MUST transcribe its pinyin as 'liǎo' (NOT 'le') to force the Malaysian pronunciation.
        4. DICTIONARY BREAKDOWN: Break the sentence down into logical 1-to-2 character chunks. Do NOT group large 4-character chunks together.
        """
    else:
        display_word = chinese_chars if chinese_chars else pinyin
        behavior_prompt = f"""
        Create a FULL 1-sentence scenario (between 5 and 10 words long) using the target word '{display_word}' ({pinyin} - {english}).
        If you use '了', transcribe its pinyin as 'liǎo'.
        """

    prompt = f"""
    You are an expert Malaysian Mandarin tutor. 
    
    {behavior_prompt}
    
    GENERAL INSTRUCTIONS:
    1. STRICT SYNCHRONIZATION: The Chinese characters (Hanzi) and the Pinyin MUST perfectly match.
    2. NO HALLUCINATED CONTEXT: Do NOT invent random names (e.g., "David"). Use generic pronouns if a subject is missing.
    3. NUMERAL CONVERSION (CRITICAL): If the target word contains Arabic numerals (e.g., '50'), you MUST write them out as actual Chinese characters (e.g., '五十') in the 'hanzi' string and provide the correct Pinyin. NEVER leave Arabic numerals in the generated Chinese sentence.
    
    GRAMMAR AND PARTICLES (CRITICAL):
    You must provide TWO distinct teaching notes:
    1. 'grammar_point': Focus ONLY on the structural syntax of the sentence. 
    2. 'particle_note': SCAN the Chinese sentence. If it contains ANY Malaysian particle (e.g., 啦, 咯, 咩, 咧, 啊, 嘛, 喎, 哎哟, 哎呀, 了), you ABSOLUTELY MUST fill out this field explaining the specific emotional tone it adds. Do NOT skip this if a particle is present. ONLY return null if the sentence is 100% free of discourse particles.
    
    Output a raw JSON object EXACTLY like this example format:
    {{
        "hanzi": "他没有来咩？",
        "pinyin": "tā méi yǒu lái mē?",
        "english_correct": "He didn't come?",
        "english_distractors": ["Did he come?", "Why didn't he come?", "He is coming.", "I didn't come."],
        "word_breakdown": [
            {{"hanzi": "他", "pinyin": "tā", "english": "he"}},
            {{"hanzi": "没有", "pinyin": "méi yǒu", "english": "did not"}},
            {{"hanzi": "来", "pinyin": "lái", "english": "come"}},
            {{"hanzi": "咩", "pinyin": "mē", "english": "(particle)"}}
        ],
        "grammar_point": {{
            "structure": "Subject + 没有 + Verb",
            "explanation": "Used to negate past actions."
        }},
        "particle_note": {{
            "particle": "咩 (meh)",
            "explanation": "Expresses mild surprise or skepticism."
        }}
    }}
    """
    
    try:
        response = client.chat.completions.create(
            messages=[{'role': 'user', 'content': prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        
        raw_json_str = response.choices[0].message.content
        raw_data = json.loads(raw_json_str)
        
        # --- THE SURGICAL LOCK ---
        if is_locked_phrase:
            final_chinese = chinese_chars
            final_pinyin = pinyin if pinyin else raw_data.get("pinyin", "")
            final_english = english if english else raw_data.get("english_correct", "")
        else:
            final_chinese = raw_data.get("hanzi", raw_data.get("chinese", ""))
            final_pinyin = raw_data.get("pinyin", "")
            final_english = raw_data.get("english_correct", "")

        word_breakdown = []
        for item in raw_data.get("word_breakdown", []):
            word_breakdown.append({
                "chinese": item.get("hanzi", item.get("chinese", "")),
                "pinyin": item.get("pinyin", ""),
                "english": item.get("english", "")
            })

        exercise_data = {
            "chinese": final_chinese,
            "pinyin": final_pinyin,
            "english_correct": final_english,
            "english_distractors": raw_data.get("english_distractors", []),
            "target_pinyin": pinyin,
            "word_breakdown": word_breakdown,
            "grammar_point": raw_data.get("grammar_point", {}),
            "particle_note": raw_data.get("particle_note", {})
        }
        
        return exercise_data
        
    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
