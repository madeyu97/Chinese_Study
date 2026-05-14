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

# Homophones the listener cannot disambiguate by ear alone.
# If any of these appear in the Chinese sentence, the MCQ correct-answer must
# accept either reading and distractors must NOT vary on the homophone alone.
HOMOPHONE_GROUPS = [
    ("他", "她", "它"),         # tā — he / she / it
    ("在", "再"),               # zài — at / again
    ("是", "事"),               # shì — to be / matter
    ("做", "作"),               # zuò — to do / to make
    ("到", "道"),               # dào — to arrive / way
    ("以", "已"),               # yǐ — by means of / already
    ("买", "卖"),               # mǎi/mài — different tone, but new learners often confuse
    ("会", "回"),               # huì/huí — different tone, often confused
]

def _detect_homophones(chinese_text: str):
    """Return a list of homophone groups present in the sentence, for prompt injection."""
    present = []
    for group in HOMOPHONE_GROUPS:
        if any(ch in chinese_text for ch in group):
            present.append(group)
    return present


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

    # ----------------------------------------------------------------------
    # NEW: distractor-quality + homophone rules
    # ----------------------------------------------------------------------
    distractor_rules = """
    DISTRACTOR QUALITY RULES (CRITICAL — this is a LISTENING exercise):

    The four English options (1 correct + 3 distractors) will be shown after the
    learner hears the Chinese audio. Distractors must train the ear, not be
    obvious throwaways. Apply ALL of the following:

    1. SINGLE-FEATURE DIFFERENCE: Each distractor must differ from the correct
       English by EXACTLY ONE specific feature the listener could plausibly
       mishear. Pick a different feature for each distractor. Allowed features:
         (a) The aspect/tense marker (了 was/wasn't heard, 过 vs no 过, 在 vs no 在)
         (b) Negation (没/不 was/wasn't heard)
         (c) A single particle's emotional force (e.g. 啊 surprise vs 吗 question vs 啦 casual)
         (d) ONE specific noun or verb swapped for a phonetically similar /
             semantically adjacent word (e.g. "buy" vs "sell", "tea" vs "water",
             "yesterday" vs "tomorrow")
         (e) The quantifier or number (e.g. "three" vs "a few", "all" vs "some")

    2. NO TRIVIAL DISTRACTORS — BANNED:
       - Sentences with opposite polarity to the correct answer (e.g. correct
         "He came" + distractor "He didn't come"). Too easy to eliminate.
       - Sentences that are grammatically impossible or semantically absurd in
         the context.
       - Sentences using vocabulary far outside the register of the original
         (don't put formal/literary terms in a casual sentence's distractors).
       - Sentences that differ only in English word order without meaning change
         (e.g. "I gave him the book" vs "I gave the book to him").
       - Sentences whose only difference is synonym substitution that preserves
         meaning (e.g. "purchase" vs "buy"). The learner gains nothing.

    3. ALL FOUR OPTIONS MUST BE GRAMMATICAL ENGLISH and roughly the same length
       (within 3 words of each other). No 4-word stub next to a 12-word essay.

    4. PLAUSIBILITY TEST: Before finalising each distractor, ask: "Could a
       learner who heard ~80% of the audio correctly genuinely pick this?" If
       no, rewrite it.

    HOMOPHONE HANDLING (CRITICAL):

    Chinese has many same-pinyin / same-tone characters the listener CANNOT
    disambiguate by ear. The most common is 他/她/它 — all pronounced 'tā'.
    Others include 在/再 (zài), 是/事 (shì), 做/作 (zuò), 到/道 (dào), 以/已 (yǐ).

    Rules:
    (a) If the Chinese sentence contains a homophone, the CORRECT English
        answer must reflect the ambiguity. For 他/她/它, write "He/She" or
        "He/She/It" depending on context plausibility. Do NOT commit to one
        gender or thing-vs-person if the audio doesn't.
    (b) Distractors must NOT differ from the correct answer ONLY on a
        homophone (e.g. don't make "He went home" the correct and "She went
        home" a distractor — they sound identical and both are correct).
    (c) Pronoun confusion is fine ONLY if it pairs with another single-feature
        difference (e.g. correct "He/She went home" vs distractor "We went
        home" — different pronoun number, audibly different).
    """

    prompt = f"""
    You are an expert Malaysian Mandarin tutor designing a LISTENING
    comprehension multiple-choice question.

    {behavior_prompt}

    GENERAL INSTRUCTIONS:
    1. STRICT SYNCHRONIZATION: The Chinese characters (Hanzi) and the Pinyin MUST perfectly match.
    2. NO HALLUCINATED CONTEXT: Do NOT invent random names (e.g., "David"). Use generic pronouns if a subject is missing.
    3. NUMERAL CONVERSION (CRITICAL): If the target word contains Arabic numerals (e.g., '50'), you MUST write them out as actual Chinese characters (e.g., '五十') in the 'hanzi' string and provide the correct Pinyin. NEVER leave Arabic numerals in the generated Chinese sentence.
    4. MALAYSIAN PRONUNCIATION (CRITICAL):
       - If the sentence contains the particle '了', you MUST transcribe its pinyin as 'liǎo' (NOT 'le').
       - If the sentence contains the particle '咩', you MUST transcribe its pinyin as 'meh' (NOT 'miē').

    {distractor_rules}

    GRAMMAR AND PARTICLES (CRITICAL):
    You must provide TWO distinct teaching notes:
    1. 'grammar_point': Focus ONLY on the structural syntax of the sentence.
    2. 'particle_note': SCAN the Chinese sentence. If it contains ANY Malaysian particle (e.g., 啦, 咯, 咩, 咧, 啊, 嘛, 喎, 哎哟, 哎呀, 了), you ABSOLUTELY MUST fill out this field explaining the specific emotional tone it adds. Do NOT skip this if a particle is present. ONLY return null if the sentence is 100% free of discourse particles.

    Output a raw JSON object EXACTLY like this example format. Note how the
    correct answer hedges on 他 vs 她, and how each distractor changes ONE
    specific audibly-distinguishable feature:
    {{
        "hanzi": "他昨天没买茶。",
        "pinyin": "tā zuó tiān méi mǎi chá.",
        "english_correct": "He/She didn't buy tea yesterday.",
        "english_distractors": [
            "He/She didn't buy tea today.",
            "He/She didn't buy water yesterday.",
            "He/She bought tea yesterday."
        ],
        "word_breakdown": [
            {{"hanzi": "他", "pinyin": "tā", "english": "he/she"}},
            {{"hanzi": "昨天", "pinyin": "zuó tiān", "english": "yesterday"}},
            {{"hanzi": "没", "pinyin": "méi", "english": "did not"}},
            {{"hanzi": "买", "pinyin": "mǎi", "english": "buy"}},
            {{"hanzi": "茶", "pinyin": "chá", "english": "tea"}}
        ],
        "grammar_point": {{
            "structure": "Subject + Time + 没 + Verb + Object",
            "explanation": "Past-tense negation using 没."
        }},
        "particle_note": null
    }}

    In that example: distractor 1 changes time word, distractor 2 changes the
    object noun, distractor 3 removes the negation. Each is one feature, each
    is plausibly mis-heard, and the correct answer doesn't gender-commit.
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

        # ------------------------------------------------------------------
        # NEW: post-hoc safety net — if the AI ignored the homophone rule and
        # the correct answer commits to "He" or "She" while the sentence uses
        # the ambiguous 他/她/它, soft-rewrite it to "He/She".
        # This is belt-and-braces; the prompt should handle it, but LLMs slip.
        # ------------------------------------------------------------------
        present_homophones = _detect_homophones(final_chinese)
        english_correct = raw_data.get("english_correct", "")
        english_distractors = raw_data.get("english_distractors", [])

        # Handle 他/她/它 — the pronoun case
        if any(set(g) <= {"他", "她", "它"} or "他" in g for g in present_homophones):
            # Only hedge if the sentence does NOT make gender unambiguous via
            # other context. We can't be perfectly sure, so hedge unless the
            # AI already did.
            if "/" not in english_correct:
                for word in (" He ", " She ", " he ", " she "):
                    if word in f" {english_correct} ":
                        english_correct = (
                            english_correct
                            .replace(" He ", " He/She ")
                            .replace(" She ", " He/She ")
                            .replace(" he ", " he/she ")
                            .replace(" she ", " he/she ")
                        )
                        if english_correct.startswith("He ") or english_correct.startswith("She "):
                            english_correct = "He/She " + english_correct.split(" ", 1)[1]
                        break

            # Drop any distractor that differs from the correct answer ONLY on
            # the pronoun — those are not valid distractors for listening.
            def _strip_pronoun(s):
                return (s.replace("He/She", "X").replace("He", "X").replace("She", "X")
                         .replace("he/she", "x").replace("he", "x").replace("she", "x"))
            correct_normalised = _strip_pronoun(english_correct)
            english_distractors = [
                d for d in english_distractors
                if _strip_pronoun(d).strip().lower() != correct_normalised.strip().lower()
            ]

        exercise_data = {
            "chinese": final_chinese,
            "pinyin": final_pinyin,
            "english_correct": english_correct,
            "english_distractors": english_distractors,
            "target_pinyin": pinyin,
            "word_breakdown": word_breakdown,
            "grammar_point": raw_data.get("grammar_point", {}),
            "particle_note": raw_data.get("particle_note", {})
        }

        # Sanity check: if we ended up with < 3 distractors, log it so it shows
        # up in your Streamlit logs.
        if len(exercise_data["english_distractors"]) < 3:
            logging.warning(
                f"Only {len(exercise_data['english_distractors'])} distractors after homophone filtering "
                f"for sentence: {final_chinese}"
            )

        return exercise_data

    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
