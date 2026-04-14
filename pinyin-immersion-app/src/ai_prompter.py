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
    
    # Try to grab the actual Chinese characters from your CSV dictionary
    chinese_chars = target_word_dict.get('chinese', target_word_dict.get('hanzi', target_word_dict.get('characters', '')))
    
    # ==========================================
    # THE SMART SWITCH
    # ==========================================
    if len(chinese_chars) > 3:
        # If it's a long phrase/sentence, force the AI to use it verbatim
        behavior_prompt = f"""
        The user has provided a complete phrase/sentence: '{chinese_chars}' ({pinyin} - {english}).
        CRITICAL: DO NOT invent a new scenario. You MUST use EXACTLY '{chinese_chars}' as the main "hanzi" field. 
        Your job is ONLY to generate the distractors, dictionary breakdown, and grammar point for this exact sentence.
        """
    else:
        # If it's a short word (or empty), tell it to be creative
        display_word = chinese_chars if chinese_chars else pinyin
        behavior_prompt = f"""
        Create a FULL 1-sentence scenario (between 5 and 10 words long) using the target word '{display_word}' ({pinyin} - {english}).
        """

    prompt = f"""
    You are an expert Malaysian Mandarin tutor. 
    
    {behavior_prompt}
    
    GENERAL INSTRUCTIONS:
    1. STRICT SYNCHRONIZATION: The Chinese characters (Hanzi) and the Pinyin MUST perfectly match. If you use a local word in Pinyin (e.g., 'lǐ bài'), you MUST write the exact local characters ('礼拜').
    2. You MUST write actual Chinese Characters (Hanzi) in all "hanzi" fields. DO NOT leave them empty.
    3. Use local Malaysian phrasing, and provide standard Pinyin with tone marks.
    
    Output a raw JSON object EXACTLY like this example format:
    {{
        "hanzi": "本地人喜欢吃椰浆饭。",
        "pinyin": "běn dì rén xǐ huan chī yē jiāng fàn.",
        "english_correct": "Local people like to eat Nasi Lemak.",
        "english_distractors": ["Local people like to eat chicken rice.", "Foreigners like to eat Nasi Lemak.", "Tourists like to eat spicy food.", "My friend likes to eat noodles."],
        "word_breakdown": [
            {{"hanzi": "本地人", "pinyin": "běn dì rén", "english": "local people"}},
            {{"hanzi": "喜欢", "pinyin": "xǐ huan", "english": "like"}},
            {{"hanzi": "吃", "pinyin": "chī", "english": "eat"}},
            {{"hanzi": "椰浆饭", "pinyin": "yē jiāng fàn", "english": "Nasi Lemak"}}
        ],
        "grammar_point": {{
            "structure": "Subject + 喜欢 (xǐ huan) + Verb",
            "explanation": "Used to express that someone likes doing a specific action."
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
        logging.info(f"Raw Groq Output:\n{raw_json_str}")
        
        raw_data = json.loads(raw_json_str)
        
        final_chinese_text = raw_data.get("hanzi", raw_data.get("chinese", ""))
        
        if not final_chinese_text or final_chinese_text.strip() == "":
            raise ValueError("Groq returned an empty Chinese string.")

        word_breakdown = []
        for item in raw_data.get("word_breakdown", []):
            word_breakdown.append({
                "chinese": item.get("hanzi", item.get("chinese", "")),
                "pinyin": item.get("pinyin", ""),
                "english": item.get("english", "")
            })

        exercise_data = {
            "chinese": final_chinese_text,
            "pinyin": raw_data.get("pinyin", ""),
            "english_correct": raw_data.get("english_correct", ""),
            "english_distractors": raw_data.get("english_distractors", []),
            "target_pinyin": pinyin,
            "word_breakdown": word_breakdown,
            "grammar_point": raw_data.get("grammar_point", {"structure": "Syntax", "explanation": "Standard phrasing."})
        }
        
        logging.info(f"Successfully generated exercise via Groq for: {pinyin}")
        return exercise_data
        
    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None