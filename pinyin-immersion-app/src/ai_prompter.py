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
    1. STRICT SYNCHRONIZATION: The Chinese characters (Hanzi) and the Pinyin MUST perfectly match. 
    2. You MUST write actual Chinese Characters (Hanzi) in all "hanzi" fields. DO NOT leave them empty.
    3. NO HALLUCINATED CONTEXT (CRITICAL): Your English translations (both correct and distractors) MUST strictly translate ONLY the words present in the Chinese sentence. Do NOT invent random names (e.g., "David", "Tom"), places, or extra backstory that are not explicitly written in the Hanzi. If the Chinese sentence omits the subject, use generic pronouns in English (it, he, she, someone).
    
    GRAMMAR AND PARTICLES (CRITICAL):
    You must provide TWO distinct teaching notes:
    1. 'grammar_point': Focus ONLY on the structural syntax of the sentence (e.g., '是...的' emphasis, '把' structure, measure words). 
    2. 'particle_note': SCAN the Chinese sentence. If it contains ANY Malaysian particle (e.g., 啦, 咯, 咩, 咧, 啊, 嘛, 喎, 哎哟, 哎呀, 了), you ABSOLUTELY MUST fill out this field explaining the specific emotional tone it adds. Do NOT skip this if a particle is present. ONLY return null if the sentence is 100% free of discourse particles.
    
    REFERENCE LIBRARY - MALAYSIAN PARTICLES:
    - lah (啦): emphasis, softening tone, friendliness
    - lor / loh (咯): resignation, "obviously", casual conclusion
    - meh (咩): doubt, questioning tone, disbelief
    - leh (咧): mild contradiction or suggestion
    - ah (啊): question marker or soft emphasis
    - ma (嘛): obviousness / "as you know"
    - wor (喎): surprise or new information
    - aiyo / aiyah (哎哟 / 哎呀): frustration or complaint
    - liao (了): written as 了 but pronounced "liào" locally. Indicates completion or change of state.
    - Combo particles: lah lor, meh lah, lor lah, etc.
    
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
            "explanation": "Used to negate past actions. Unlike '不' which negates present/future or habits, '没有' specifically states that an action did not happen."
        }},
        "particle_note": {{
            "particle": "咩 (meh)",
            "explanation": "Placed at the end of the sentence to express mild surprise or skepticism. It turns a standard statement into a question of disbelief."
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
