# src/ai_prompter.py

import os
import re
import json
import random
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ----------------------------------------------------------------------
# Malaysian Mandarin colloquialisms
# ----------------------------------------------------------------------
MALAYSIAN_SLANG = {
    "酱": ("sauce (literal)", "colloquial contraction of 这样 — 'like this / so / that'"),
    "啊那": ("(none)", "contraction of 那个 — 'that one / um'"),
    "烧": ("to burn (literal)", "used for 'hot' (temperature) instead of 热"),
    "怕输": ("(literal: afraid of losing)", "kiasu — fear of missing out"),
    "做工": ("to do work (literal)", "to work / go to work — used where mainland says 上班"),
    "讲": ("to speak (literal)", "preferred over 说 in casual speech"),
    "要": ("to want (literal)", "often future tense 'going to' where mainland uses 会"),
    "几时": ("(uncommon in PRC)", "Malaysian for 'when' — instead of 什么时候"),
    "罢了": ("(literary)", "casual 'only / just' — like 而已"),
    "巴刹": ("(none)", "from Malay 'pasar' — wet market"),
    "甘榜": ("(none)", "from Malay 'kampung' — village"),
}

HOMOPHONE_GROUPS = [
    ("他", "她", "它"), ("在", "再"), ("是", "事"), ("做", "作"),
    ("到", "道"), ("以", "已"), ("买", "卖"), ("会", "回"),
]

MALAYSIAN_PARTICLES = {"啦", "咯", "咩", "咧", "啊", "嘛", "喎", "罢了", "了", "吗", "呢", "吧"}
TIME_WORDS = {"今天", "昨天", "明天", "现在", "刚才", "以前", "以后", "之前", "之后",
              "早上", "晚上", "下午", "中午", "上个", "下个"}
NEGATIONS = {"不", "没", "没有", "别", "甭"}
QUANTIFIERS = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
               "百", "千", "万", "几", "多", "少", "些", "都"}

# Sentence-level punctuation — presence of these means it's a real sentence,
# not a synonym list.
SENTENCE_PUNCTUATION = "。！？，,!?;"

# Synonym separators we treat as "this row contains multiple variants"
SYNONYM_SEPARATORS_REGEX = r'\s*(?:[/／;；]|\s或\s)\s*'


# ======================================================================
# LAYER 1: Aggressive synonym splitter
# ======================================================================
def _split_synonyms(chinese_chars, pinyin, english):
    """
    CSV entries packing synonyms into one row (e.g. '之前 / 以前') need to be
    split into individual variants. We pick ONE variant at random and use it
    for this exercise. Original CSV row is untouched.
    """
    if not chinese_chars:
        return chinese_chars, pinyin, english

    # Sanity: if the string contains sentence punctuation, it's a real
    # sentence, not a synonym list — leave it alone.
    if any(p in chinese_chars for p in SENTENCE_PUNCTUATION):
        return chinese_chars, pinyin, english

    chinese_variants = [c.strip() for c in re.split(SYNONYM_SEPARATORS_REGEX, chinese_chars) if c.strip()]

    if len(chinese_variants) < 2:
        return chinese_chars, pinyin, english  # No real separator found

    pinyin_variants = [p.strip() for p in re.split(SYNONYM_SEPARATORS_REGEX, pinyin or '') if p.strip()]
    english_variants = [e.strip() for e in re.split(SYNONYM_SEPARATORS_REGEX, english or '') if e.strip()]

    idx = random.randint(0, len(chinese_variants) - 1)
    chosen_chinese = chinese_variants[idx]

    if len(pinyin_variants) == len(chinese_variants):
        chosen_pinyin = pinyin_variants[idx]
    elif pinyin_variants:
        chosen_pinyin = pinyin_variants[0]
    else:
        chosen_pinyin = pinyin

    if len(english_variants) == len(chinese_variants):
        chosen_english = english_variants[idx]
    elif english_variants:
        chosen_english = english_variants[0]
    else:
        chosen_english = english

    logging.info(
        f"[SPLIT] Multi-variant entry '{chinese_chars}' -> using '{chosen_chinese}' "
        f"(variant {idx+1}/{len(chinese_variants)})"
    )
    return chosen_chinese, chosen_pinyin, chosen_english


# ======================================================================
# LAYER 2: Better lock detection — based on punctuation, NOT length
# ======================================================================
def _is_locked_sentence(chinese_chars):
    """
    A 'locked sentence' means the CSV row contains an actual sentence the AI
    must not rewrite (used for grammar drills, idioms, etc.). The old check
    `len > 3` was wrong — a 4-character idiom is a word, and "之前 / 以前" is
    a synonym pair, neither is a sentence.

    Real sentences contain sentence-ending or clausal punctuation.
    """
    return any(p in chinese_chars for p in SENTENCE_PUNCTUATION)


def _classify_target(chinese_chars, english):
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
    return "content_word"


def _find_relevant_slang(chinese_text):
    return {k: v for k, v in MALAYSIAN_SLANG.items() if k in chinese_text}


def _detect_homophones(chinese_text):
    return [g for g in HOMOPHONE_GROUPS if any(ch in chinese_text for ch in g)]


DISTRACTOR_PLAYBOOKS = {
    "particle": """
    TARGET CATEGORY: PARTICLE — train ear for particle nuance.
    Distractors MUST vary the SENTENCE TYPE / EMOTIONAL FORCE.
    Propositional content of all four options should be near-identical;
    what changes is the speech act / mood.

    Required axes (pick 3, one per distractor):
      - Statement vs question (吗/咩)
      - Exclamation/surprise (啊/喔) vs confirmation-seeking (吧/咩) vs assertion (啦)
      - Skepticism (咩) vs assertive (啦) vs reluctant (咯)
      - Polite/softening (吧, 嘛) vs blunt (no particle)

    DO NOT change content nouns. The particle is what's being tested.
    """,
    "time": """
    TARGET CATEGORY: TIME WORD — distractors vary the time reference.
    Keep everything else identical.
    """,
    "negation": """
    TARGET CATEGORY: NEGATION — vary negation presence/type (不 vs 没, affirmative vs negative).
    """,
    "quantifier": """
    TARGET CATEGORY: QUANTIFIER — change ONLY the number/quantifier.
    """,
    "content_word": """
    TARGET CATEGORY: CONTENT WORD — swap target for phonetically similar OR
    semantically adjacent alternatives. Vary one other feature on remaining distractors.
    """,
    "general": """
    Vary one specific feature per distractor.
    """,
}


def generate_dictation_exercise(target_word_dict):
    pinyin = target_word_dict.get('pinyin', '')
    english = target_word_dict.get('english', '')
    chinese_chars = target_word_dict.get(
        'chinese', target_word_dict.get('hanzi', target_word_dict.get('characters', ''))
    )

    logging.info(f"[GEN] Raw CSV entry: chinese='{chinese_chars}' pinyin='{pinyin}' english='{english}'")

    # ──────────────────────────────────────────────────────────────────
    # LAYER 1: split synonyms
    # ──────────────────────────────────────────────────────────────────
    chinese_chars, pinyin, english = _split_synonyms(chinese_chars, pinyin, english)

    # ──────────────────────────────────────────────────────────────────
    # LAYER 2: last-ditch safety. If a slash STILL exists after splitting,
    # something is wrong (unusual separator, malformed CSV, etc.). Force-take
    # everything before the first slash and log a warning.
    # ──────────────────────────────────────────────────────────────────
    for bad_sep in ("/", "／"):
        if bad_sep in chinese_chars:
            logging.warning(
                f"[SAFETY] Slash survived splitting in '{chinese_chars}' — force-taking first portion"
            )
            chinese_chars = chinese_chars.split(bad_sep)[0].strip()
            if pinyin and bad_sep in pinyin:
                pinyin = pinyin.split(bad_sep)[0].strip()
            if english and bad_sep in english:
                english = english.split(bad_sep)[0].strip()

    logging.info(f"[GEN] After cleaning: chinese='{chinese_chars}' pinyin='{pinyin}' english='{english}'")

    # ──────────────────────────────────────────────────────────────────
    # LAYER 3: punctuation-based lock detection (no more len > 3 nonsense)
    # ──────────────────────────────────────────────────────────────────
    is_locked = _is_locked_sentence(chinese_chars)
    logging.info(f"[GEN] is_locked_sentence = {is_locked}")

    target_category = _classify_target(chinese_chars, english)
    playbook = DISTRACTOR_PLAYBOOKS[target_category]

    if is_locked:
        behavior_prompt = f"""
        LOCKED SENTENCE: '{chinese_chars}'
        Meaning: '{english}'

        RULES:
        1. DO NOT alter the Chinese characters. Use EXACTLY '{chinese_chars}'.
        2. Generate Pinyin that perfectly matches.
        3. If contains '了', transcribe as 'liǎo'.
        4. Break into logical 1-2 character chunks.
        """
        slang_in_play = _find_relevant_slang(chinese_chars)
    else:
        display_word = chinese_chars if chinese_chars else pinyin
        behavior_prompt = f"""
        Create a FULL 1-sentence scenario (5-10 words) using the target word
        '{display_word}' ({pinyin} - {english}). If you use '了', transcribe as 'liǎo'.
        """
        slang_in_play = _find_relevant_slang(chinese_chars)

    slang_section = ""
    if slang_in_play:
        slang_lines = "\n".join(
            f"   - {char}: {meaning[1]}" for char, meaning in slang_in_play.items()
        )
        slang_section = f"""
    MALAYSIAN COLLOQUIAL CONTEXT (CRITICAL):
{slang_lines}
    """

    full_slang_reference = "MALAYSIAN COLLOQUIAL GLOSSARY:\n"
    for char, (literal, malaysian) in MALAYSIAN_SLANG.items():
        full_slang_reference += f"   {char}: literal={literal}; Malaysian={malaysian}\n"

    prompt = f"""
    You are an expert Malaysian Mandarin tutor designing a LISTENING
    comprehension multiple-choice question.

    {behavior_prompt}

    {slang_section}

    {full_slang_reference}

    GENERAL:
    1. STRICT SYNCHRONIZATION: Characters and Pinyin must match.
    2. NO INVENTED NAMES. Use pronouns.
    3. NUMERAL CONVERSION: Arabic → Chinese characters.
    4. MALAYSIAN PRONUNCIATION: '了' → 'liǎo'; '咩' → 'meh'.
    5. THE OUTPUT 'hanzi' FIELD MUST NEVER CONTAIN '/' OR '／' OR ';'.

    ═══════════════════════════════════════════════════════════════════
    TARGET-AWARE DISTRACTOR DESIGN
    ═══════════════════════════════════════════════════════════════════

    Target: '{chinese_chars}' ({pinyin}, "{english}")
    Category: {target_category.upper()}

    {playbook}

    UNIVERSAL RULES:
    1. Distractors attack the TARGET's learning axis, not random other words.
    2. NO TRIVIAL DISTRACTORS: no opposite polarity, no synonym-only swaps,
       no word-order-only changes, no grammatically impossible options.
    3. All four options grammatical English, within 3 words of each other.
    4. Plausibility test: could an ~80% listener genuinely pick this?

    HOMOPHONES:
    For 他/她/它, 在/再, 是/事, etc., correct answer reflects ambiguity
    ("He/She"). Distractors must NOT differ ONLY on a homophone.

    Output a raw JSON object EXACTLY:
    {{
        "hanzi": "<sentence — NEVER contain / or ; characters>",
        "pinyin": "<matching pinyin>",
        "english_correct": "<accurate translation>",
        "english_distractors": ["<d1>", "<d2>", "<d3>"],
        "word_breakdown": [{{"hanzi": "字", "pinyin": "zì", "english": "meaning"}}],
        "grammar_point": {{"structure": "...", "explanation": "..."}},
        "particle_note": {{"particle": "...", "explanation": "..."}}
    }}
    """

    try:
        response = client.chat.completions.create(
            messages=[{'role': 'user', 'content': prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )

        raw_data = json.loads(response.choices[0].message.content)

        if is_locked:
            final_chinese = chinese_chars
            final_pinyin = pinyin if pinyin else raw_data.get("pinyin", "")
        else:
            final_chinese = raw_data.get("hanzi", raw_data.get("chinese", ""))
            final_pinyin = raw_data.get("pinyin", "")

        # ──────────────────────────────────────────────────────────────
        # LAYER 4: final guardrail. If for ANY reason a slash sneaks into
        # what we're about to return, scrub it. This is the last line of
        # defence against display showing "X / Y".
        # ──────────────────────────────────────────────────────────────
        for bad_sep in ("/", "／"):
            if bad_sep in final_chinese:
                logging.error(
                    f"[GUARDRAIL] Slash in final_chinese '{final_chinese}' — scrubbing"
                )
                final_chinese = final_chinese.split(bad_sep)[0].strip()
            if bad_sep in final_pinyin:
                final_pinyin = final_pinyin.split(bad_sep)[0].strip()

        word_breakdown = []
        for item in raw_data.get("word_breakdown", []):
            word_breakdown.append({
                "chinese": item.get("hanzi", item.get("chinese", "")),
                "pinyin": item.get("pinyin", ""),
                "english": item.get("english", "")
            })

        present_homophones = _detect_homophones(final_chinese)
        english_correct = raw_data.get("english_correct", "")
        english_distractors = raw_data.get("english_distractors", [])

        if any("他" in g for g in present_homophones):
            if "/" not in english_correct:
                for word in (" He ", " She ", " he ", " she "):
                    if word in f" {english_correct} ":
                        english_correct = (
                            english_correct
                            .replace(" He ", " He/She ").replace(" She ", " He/She ")
                            .replace(" he ", " he/she ").replace(" she ", " he/she ")
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
            "target_category": target_category,
        }

        logging.info(f"[GEN] FINAL: chinese='{final_chinese}' english_correct='{english_correct}'")

        if len(exercise_data["english_distractors"]) < 3:
            logging.warning(
                f"Only {len(exercise_data['english_distractors'])} distractors for: {final_chinese}"
            )

        return exercise_data

    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
