# src/ai_prompter.py

import os
import json
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ----------------------------------------------------------------------
# Malaysian Mandarin colloquialisms the standard LLM gets wrong by default.
# Add entries as you find more. Format: hanzi -> (standard meaning, what
# Malaysians actually use it as).
# ----------------------------------------------------------------------
MALAYSIAN_SLANG = {
    "酱": ("sauce (literal)", "colloquial contraction of 这样 — 'like this / so / that'. e.g. 酱贵 = 这样贵 = 'so expensive'"),
    "啊那": ("(none)", "contraction of 那个 — 'that one / um'"),
    "烧": ("to burn (literal)", "used for 'hot' (temperature of food/drink) instead of 热"),
    "怕输": ("(literal: afraid of losing)", "kiasu — fear of missing out / being one-upped. Cultural staple."),
    "做工": ("to do work (literal)", "to work / go to work — used where mainland speakers would say 上班"),
    "讲": ("to speak (literal)", "preferred over 说 for 'to say' in casual speech"),
    "要": ("to want (literal)", "often used for future tense 'going to' where mainland uses 会"),
    "几时": ("(uncommon in PRC)", "Malaysian for 'when' — used instead of 什么时候"),
    "罢了": ("(literary)", "casual 'only / just' — like 而已. Often paired with 啦"),
    "巴刹": ("(none)", "from Malay 'pasar' — wet market"),
    "甘榜": ("(none)", "from Malay 'kampung' — village"),
}

# ----------------------------------------------------------------------
# Homophones the listener cannot disambiguate by ear alone.
# ----------------------------------------------------------------------
HOMOPHONE_GROUPS = [
    ("他", "她", "它"),
    ("在", "再"),
    ("是", "事"),
    ("做", "作"),
    ("到", "道"),
    ("以", "已"),
    ("买", "卖"),
    ("会", "回"),
]

# ----------------------------------------------------------------------
# Target-word category detection — drives what kind of distractors to make.
# ----------------------------------------------------------------------
MALAYSIAN_PARTICLES = {"啦", "咯", "咩", "咧", "啊", "嘛", "喎", "罢了", "了", "吗", "呢", "吧"}
TIME_WORDS = {"今天", "昨天", "明天", "现在", "刚才", "以前", "以后", "早上", "晚上", "下午", "中午", "上个", "下个"}
NEGATIONS = {"不", "没", "没有", "别", "甭"}
QUANTIFIERS = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万", "几", "多", "少", "些", "都"}

def _classify_target(chinese_chars: str, english: str) -> str:
    """
    Best-effort categorisation of the target word so the AI can build
    distractors that attack the right learning axis.
    """
    if not chinese_chars:
        return "general"
    for p in MALAYSIAN_PARTICLES:
        if p == chinese_chars or (len(chinese_chars) <= 2 and p in chinese_chars):
            return "particle"
    if chinese_chars in TIME_WORDS:
        return "time"
    if chinese_chars in NEGATIONS:
        return "negation"
    if chinese_chars in QUANTIFIERS or any(c in QUANTIFIERS for c in chinese_chars):
        return "quantifier"
    # crude heuristic: single chars in this list-ish range tend to be verbs/adjectives
    return "content_word"


def _find_relevant_slang(chinese_text: str):
    """Return slang entries present in the sentence, for prompt context."""
    return {k: v for k, v in MALAYSIAN_SLANG.items() if k in chinese_text}


def _detect_homophones(chinese_text: str):
    present = []
    for group in HOMOPHONE_GROUPS:
        if any(ch in chinese_text for ch in group):
            present.append(group)
    return present


# ----------------------------------------------------------------------
# Per-category distractor rules — INJECTED into the prompt based on
# what kind of target word you're being tested on.
# ----------------------------------------------------------------------
DISTRACTOR_PLAYBOOKS = {
    "particle": """
    TARGET CATEGORY: PARTICLE — this card exists to train ear for particle nuance.

    Distractors MUST vary the SENTENCE TYPE / EMOTIONAL FORCE that different
    particles produce. The propositional content of all four options should be
    nearly identical; what changes is the speech act / mood.

    Required distractor axes (use 3 of these, one per distractor):
      - Statement (no particle / 了 finality) vs question (吗/咩) — was the
        sentence asking or telling?
      - Exclamation/surprise (啊/喔) vs confirmation-seeking (吧/咩) vs
        casual assertion (啦/罢了)
      - Mild surprise/skepticism (咩) vs assertive (啦) vs reluctant (咯)
      - Polite/softening (吧, 嘛) vs blunt (no particle)

    Example structure for sentence 有酱好吃咩？("Is it really that delicious?"):
      Correct:     "Is it really that delicious?" (咩 = skeptical question)
      Distractor:  "It is really that delicious!" (statement, no particle)
      Distractor:  "Is it that delicious?" (neutral 吗 question, no skepticism)
      Distractor:  "It's so delicious!" (啦 — casual exclamation)

    DO NOT make distractors that change the content nouns (don't swap food
    items, places, or sauce-for-water). The particle is what's being tested.
    """,

    "time": """
    TARGET CATEGORY: TIME WORD — distractors should vary the time reference.
    Each distractor changes the time word to a phonetically/semantically
    nearby alternative (yesterday/today/tomorrow, morning/evening, before/after,
    last week/next week). Keep everything else identical. Do NOT change verbs
    or nouns.
    """,

    "negation": """
    TARGET CATEGORY: NEGATION — distractors should vary on negation presence
    and type. Options should include: the affirmative version, a 不 version
    where 没 was correct (or vice versa), and a different scope of negation.
    Do not change other content words.
    """,

    "quantifier": """
    TARGET CATEGORY: QUANTIFIER/NUMBER — distractors should change ONLY the
    number or quantifier (three vs thirteen vs thirty, a few vs many vs all,
    some vs none). Keep everything else identical.
    """,

    "content_word": """
    TARGET CATEGORY: CONTENT WORD (noun/verb/adjective) — distractors should
    swap the TARGET word for a phonetically similar OR semantically adjacent
    alternative (buy/sell, tea/water, cold/hot, walk/run). Change one other
    feature on the remaining two distractors (negation, time, or quantifier).
    """,

    "general": """
    TARGET CATEGORY: general — vary one specific feature per distractor: the
    aspect/tense marker, negation, a single key noun/verb, or the quantifier.
    """,
}


def generate_dictation_exercise(target_word_dict):
    pinyin = target_word_dict.get('pinyin', '')
    english = target_word_dict.get('english', '')
    chinese_chars = target_word_dict.get('chinese', target_word_dict.get('hanzi', target_word_dict.get('characters', '')))

    is_locked_phrase = len(chinese_chars) > 3

    # Identify the learning target & what playbook applies
    target_category = _classify_target(chinese_chars, english)
    playbook = DISTRACTOR_PLAYBOOKS[target_category]

    if is_locked_phrase:
        behavior_prompt = f"""
        LOCKED SENTENCE: '{chinese_chars}'
        Meaning: '{english}'

        CRITICAL RULES FOR THIS SENTENCE:
        1. DO NOT alter the Chinese characters. Analyze EXACTLY '{chinese_chars}' and NOTHING ELSE.
        2. PINYIN ACCURACY: You MUST generate Pinyin that perfectly matches these characters.
        3. THE "了" RULE: If this sentence contains '了', transcribe its pinyin as 'liǎo' (NOT 'le').
        4. DICTIONARY BREAKDOWN: Break the sentence into logical 1-to-2 character chunks.
        """
        # For locked phrases, detect slang in the locked Chinese now so we can
        # warn the model
        slang_in_play = _find_relevant_slang(chinese_chars)
    else:
        display_word = chinese_chars if chinese_chars else pinyin
        behavior_prompt = f"""
        Create a FULL 1-sentence scenario (between 5 and 10 words long) using the target word '{display_word}' ({pinyin} - {english}).
        If you use '了', transcribe its pinyin as 'liǎo'.
        """
        slang_in_play = _find_relevant_slang(chinese_chars)  # may be empty until generation

    # Build slang context if relevant
    slang_section = ""
    if slang_in_play:
        slang_lines = "\n".join(
            f"   - {char}: {meaning[1]}" for char, meaning in slang_in_play.items()
        )
        slang_section = f"""
    MALAYSIAN COLLOQUIAL CONTEXT (CRITICAL — the standard reading is WRONG here):
    The following characters in this sentence are Malaysian colloquial usage,
    NOT standard Mandarin. Translate accordingly:
{slang_lines}
    """

    # Also always include the full slang reference so the AI knows these terms
    # exist if it's generating a new sentence
    full_slang_reference = "MALAYSIAN COLLOQUIAL GLOSSARY (for reference when generating sentences):\n"
    for char, (literal, malaysian) in MALAYSIAN_SLANG.items():
        full_slang_reference += f"   {char}: literal = {literal}; Malaysian usage = {malaysian}\n"

    prompt = f"""
    You are an expert Malaysian Mandarin tutor designing a LISTENING
    comprehension multiple-choice question. The learner already speaks some
    Mandarin; this app is specifically training their ear for Malaysian
    colloquial speech and particle nuance.

    {behavior_prompt}

    {slang_section}

    {full_slang_reference}

    GENERAL INSTRUCTIONS:
    1. STRICT SYNCHRONIZATION: Chinese characters and Pinyin MUST perfectly match.
    2. NO HALLUCINATED CONTEXT: Don't invent random names. Use generic pronouns if subject is missing.
    3. NUMERAL CONVERSION: If the target contains Arabic numerals, write them as Chinese characters.
    4. MALAYSIAN PRONUNCIATION:
       - '了' → pinyin 'liǎo' (not 'le')
       - '咩' → pinyin 'meh' (not 'miē')

    ═══════════════════════════════════════════════════════════════════
    TARGET-AWARE DISTRACTOR DESIGN (THIS IS THE MOST IMPORTANT SECTION)
    ═══════════════════════════════════════════════════════════════════

    This card was scheduled to teach the target word: '{chinese_chars}' ({pinyin}, "{english}")
    Target category detected: {target_category.upper()}

    {playbook}

    UNIVERSAL DISTRACTOR RULES (apply on top of the category playbook above):

    1. ALL distractors must attack the TARGET word's learning axis, not random
       other words in the sentence. If the target is a particle, vary mood. If
       it's a time word, vary time. If it's a noun, vary that noun.

    2. NO TRIVIAL DISTRACTORS — BANNED:
       - Sentences with directly opposite polarity (e.g. "He came" vs "He didn't come")
       - Sentences that are grammatically impossible or absurd
       - Synonym-only substitutions ("purchase" vs "buy")
       - Word-order-only differences ("gave him the book" vs "gave the book to him")

    3. ALL four options must be grammatical English of roughly equal length
       (within 3 words of each other).

    4. PLAUSIBILITY TEST: Could a learner who heard ~80% of the audio correctly
       genuinely pick this distractor? If no, rewrite it.

    HOMOPHONE HANDLING:

    If the Chinese sentence contains 他/她/它 (tā), 在/再 (zài), 是/事 (shì),
    做/作 (zuò), 到/道 (dào), or 以/已 (yǐ): the correct answer must reflect
    the ambiguity (write "He/She" not "He"), and distractors must NOT differ
    from the correct answer ONLY on a homophone.

    GRAMMAR AND PARTICLES:
    Provide TWO teaching notes:
    1. 'grammar_point': Structural syntax only.
    2. 'particle_note': If the sentence contains ANY Malaysian particle
       (啦, 咯, 咩, 咧, 啊, 嘛, 喎, 哎哟, 哎呀, 了), explain the specific
       emotional tone. Return null ONLY if no discourse particles present.

    Output a raw JSON object EXACTLY in this format:
    {{
        "hanzi": "<the sentence>",
        "pinyin": "<matching pinyin>",
        "english_correct": "<accurate translation, hedging on homophones where needed>",
        "english_distractors": ["<dist1>", "<dist2>", "<dist3>"],
        "word_breakdown": [
            {{"hanzi": "字", "pinyin": "zì", "english": "meaning"}}
        ],
        "grammar_point": {{
            "structure": "<syntax pattern>",
            "explanation": "<short explanation>"
        }},
        "particle_note": {{
            "particle": "<particle (pinyin)>",
            "explanation": "<emotional/pragmatic force>"
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

        # --- SURGICAL LOCK for >3-char phrases ---
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

        # --- Homophone post-processing safety net ---
        present_homophones = _detect_homophones(final_chinese)
        english_correct = raw_data.get("english_correct", "")
        english_distractors = raw_data.get("english_distractors", [])

        if any("他" in g for g in present_homophones):
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
            "particle_note": raw_data.get("particle_note", {}),
            "target_category": target_category,  # exposed for debugging in UI
        }

        if len(exercise_data["english_distractors"]) < 3:
            logging.warning(
                f"Only {len(exercise_data['english_distractors'])} distractors after filtering "
                f"for sentence: {final_chinese}"
            )

        return exercise_data

    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
