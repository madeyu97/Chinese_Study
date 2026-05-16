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

# Discourse particles ONLY — adverbs like 很, 都, 也 are NOT particles.
TRUE_PARTICLES = {"啦", "咯", "咩", "咧", "啊", "嘛", "喎", "罢了", "了", "吗", "呢", "吧",
                  "哎哟", "哎呀", "哦", "喔", "唉"}

TIME_WORDS = {"今天", "昨天", "明天", "现在", "刚才", "以前", "以后", "之前", "之后",
              "早上", "晚上", "下午", "中午", "上个", "下个"}
NEGATIONS = {"不", "没", "没有", "别", "甭"}
QUANTIFIERS = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
               "百", "千", "万", "几", "多", "少", "些", "都"}

SENTENCE_PUNCTUATION = "。！？，,!?;"
SYNONYM_SEPARATORS_REGEX = r'\s*(?:[/／;；]|\s或\s)\s*'


# ======================================================================
# Synonym splitter
# ======================================================================
def _split_synonyms(chinese_chars, pinyin, english):
    if not chinese_chars:
        return chinese_chars, pinyin, english
    if any(p in chinese_chars for p in SENTENCE_PUNCTUATION):
        return chinese_chars, pinyin, english

    chinese_variants = [c.strip() for c in re.split(SYNONYM_SEPARATORS_REGEX, chinese_chars) if c.strip()]
    if len(chinese_variants) < 2:
        return chinese_chars, pinyin, english

    pinyin_variants = [p.strip() for p in re.split(SYNONYM_SEPARATORS_REGEX, pinyin or '') if p.strip()]
    english_variants = [e.strip() for e in re.split(SYNONYM_SEPARATORS_REGEX, english or '') if e.strip()]

    idx = random.randint(0, len(chinese_variants) - 1)
    chosen_chinese = chinese_variants[idx]
    chosen_pinyin = pinyin_variants[idx] if len(pinyin_variants) == len(chinese_variants) else (pinyin_variants[0] if pinyin_variants else pinyin)
    chosen_english = english_variants[idx] if len(english_variants) == len(chinese_variants) else (english_variants[0] if english_variants else english)

    logging.info(f"[SPLIT] '{chinese_chars}' -> '{chosen_chinese}' ({idx+1}/{len(chinese_variants)})")
    return chosen_chinese, chosen_pinyin, chosen_english


def _is_locked_sentence(chinese_chars):
    """Real sentences contain sentence punctuation. Words don't."""
    return any(p in chinese_chars for p in SENTENCE_PUNCTUATION)


def _classify_target(chinese_chars, english):
    if not chinese_chars:
        return "general"
    for p in TRUE_PARTICLES:
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


# ----------------------------------------------------------------------
# Traditional → simplified character map for the common drift cases.
# Not exhaustive — covers the chars most likely to slip through.
# ----------------------------------------------------------------------
TRAD_TO_SIMP = {
    "養": "养", "貓": "猫", "個": "个", "們": "们", "麼": "么", "後": "后",
    "說": "说", "話": "话", "買": "买", "賣": "卖", "兒": "儿", "對": "对",
    "點": "点", "現": "现", "時": "时", "間": "间", "問": "问", "學": "学",
    "覺": "觉", "錢": "钱", "幾": "几", "過": "过", "還": "还", "這": "这",
    "為": "为", "從": "从", "車": "车", "頭": "头", "聽": "听", "讀": "读",
    "寫": "写", "電": "电", "視": "视", "業": "业", "戰": "战", "農": "农",
    "難": "难", "馬": "马", "鳥": "鸟", "魚": "鱼", "蘋": "苹", "蔥": "葱",
    "醫": "医", "藥": "药", "體": "体", "頭": "头", "鐵": "铁", "鋼": "钢",
}

def _force_simplified(text):
    if not text:
        return text
    result = "".join(TRAD_TO_SIMP.get(ch, ch) for ch in text)
    if result != text:
        logging.info(f"[SIMP] Converted traditional chars: '{text}' -> '{result}'")
    return result


DISTRACTOR_PLAYBOOKS = {
    "particle": """
    TARGET CATEGORY: PARTICLE — train ear for particle nuance.
    Distractors MUST vary the SENTENCE TYPE / EMOTIONAL FORCE, not content.
    """,
    "time": "TARGET: TIME WORD — vary time reference only.",
    "negation": "TARGET: NEGATION — vary negation presence/type.",
    "quantifier": "TARGET: QUANTIFIER — change only the number/quantifier.",
    "content_word": "TARGET: CONTENT WORD — swap target for similar alternatives.",
    "general": "Vary one specific feature per distractor.",
}


def generate_dictation_exercise(target_word_dict, mode='listen'):
    """
    mode: 'listen' generates a rich, idiomatic sentence with MCQ distractors.
          'recall' generates a STRAIGHTFORWARD sentence where the English
                   maps predictably onto the Chinese — no extra vocab beyond
                   what the English implies.
    """
    pinyin = target_word_dict.get('pinyin', '')
    english = target_word_dict.get('english', '')
    chinese_chars = target_word_dict.get(
        'chinese', target_word_dict.get('hanzi', target_word_dict.get('characters', ''))
    )

    logging.info(f"[GEN] mode={mode} CSV: chinese='{chinese_chars}' pinyin='{pinyin}' english='{english}'")

    chinese_chars, pinyin, english = _split_synonyms(chinese_chars, pinyin, english)

    for bad_sep in ("/", "／"):
        if bad_sep in chinese_chars:
            logging.warning(f"[SAFETY] Slash survived in '{chinese_chars}'")
            chinese_chars = chinese_chars.split(bad_sep)[0].strip()
            if pinyin and bad_sep in pinyin:
                pinyin = pinyin.split(bad_sep)[0].strip()
            if english and bad_sep in english:
                english = english.split(bad_sep)[0].strip()

    is_locked = _is_locked_sentence(chinese_chars)
    target_category = _classify_target(chinese_chars, english)
    playbook = DISTRACTOR_PLAYBOOKS[target_category]

    # ──────────────────────────────────────────────────────────────────
    # MODE-SPECIFIC SENTENCE INSTRUCTION
    # ──────────────────────────────────────────────────────────────────
    if is_locked:
        sentence_instruction = f"""
        LOCKED SENTENCE: '{chinese_chars}'. Use EXACTLY this — do not alter.
        Meaning: '{english}'
        """
    elif mode == 'recall':
        sentence_instruction = f"""
        RECALL MODE — CRITICAL CONSTRAINTS:

        The user will be shown ONLY the English translation and asked to speak
        the Chinese from memory. They cannot see your Chinese sentence in
        advance. Therefore your sentence MUST be PREDICTABLE — a learner who
        reads your English should be able to mentally translate to your Chinese
        without guessing extra vocabulary you decided to add.

        STRICT RULES:
        1. Use the target word '{chinese_chars}' ({pinyin}, "{english}") in a
           SHORT, SIMPLE sentence (4-8 words).
        2. The Chinese sentence must contain ONLY vocabulary explicitly implied
           by the English. Do NOT add idiomatic flair, extra verbs, or culturally
           natural-but-not-required words.
        3. The English translation must be a LITERAL, predictable rendering.
        4. BAD EXAMPLE: English "Her cat is very cute" → Chinese "她养的猫很可爱"
           (adds 养 "raises" which isn't in the English — the learner cannot
           predict this addition).
        5. GOOD EXAMPLE: English "Her cat is very cute" → Chinese "她的猫很可爱"
           (every word in the Chinese maps to a word/concept in the English).
        6. If using '了', transcribe pinyin as 'liǎo'. If using '咩', as 'meh'.
        """
    else:
        sentence_instruction = f"""
        Create a FULL 1-sentence scenario (5-10 words) using the target word
        '{chinese_chars}' ({pinyin} - {english}).
        If you use '了', transcribe as 'liǎo'.
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

    # Distractor section only matters for listening
    if mode == 'listen':
        distractor_section = f"""
    ═══════════════════════════════════════════════════════════════════
    TARGET-AWARE DISTRACTOR DESIGN
    ═══════════════════════════════════════════════════════════════════

    Target: '{chinese_chars}' Category: {target_category.upper()}

    {playbook}

    UNIVERSAL RULES:
    1. Distractors attack the TARGET's learning axis.
    2. NO trivial distractors (no opposite polarity, no synonym-only swaps).
    3. All four options grammatical English, within 3 words of each other.
    4. Plausibility test: could an ~80% listener genuinely pick this?
    """
    else:
        # In recall mode the distractors aren't used by the UI, but we still
        # generate them cheaply so the data shape stays consistent.
        distractor_section = """
    For RECALL mode the distractors aren't shown to the user, but include 3
    minimal placeholder distractors that differ from the correct English by
    one word each.
    """

    prompt = f"""
    You are an expert Malaysian Mandarin tutor.

    {sentence_instruction}

    {slang_section}

    {full_slang_reference}

    GLOBAL RULES:
    1. STRICT SYNCHRONIZATION: Characters and Pinyin must match exactly.
    2. SIMPLIFIED CHINESE ONLY. Never use traditional characters. Use 养 not 養,
       猫 not 貓, 们 not 們, 个 not 個, 时 not 時, etc.
    3. NO INVENTED NAMES. Use pronouns.
    4. Arabic numerals → Chinese characters.
    5. The 'hanzi' field MUST NEVER contain '/' or '／' or ';'.

    {distractor_section}

    HOMOPHONES:
    For 他/她/它, 在/再, 是/事, etc., the correct English answer must reflect
    the ambiguity ("He/She"). Distractors must NOT differ only on a homophone.

    PARTICLE NOTE RULES (CRITICAL — read carefully):
    The 'particle_note' field is ONLY for genuine Mandarin/Malaysian DISCOURSE
    PARTICLES. The valid particle list is EXACTLY:
        啦, 咯, 咩, 咧, 啊, 嘛, 喎, 罢了, 了, 吗, 呢, 吧, 哎哟, 哎呁, 哦, 喔, 唉

    Words that are NOT particles (do NOT fill in particle_note for these):
        很 (adverb of degree — "very")
        都 (adverb — "all/already")
        也 (adverb — "also")
        就 (adverb — "then/just")
        还 (adverb — "still")
        Any verb, noun, adjective, classifier, or measure word.

    If the sentence contains NO particles from the valid list above, return
    particle_note as null. Do NOT confabulate by labelling an adverb as a
    particle.

    Output a raw JSON object EXACTLY:
    {{
        "hanzi": "<sentence — simplified chars only, no slashes>",
        "pinyin": "<matching pinyin>",
        "english_correct": "<accurate translation>",
        "english_distractors": ["<d1>", "<d2>", "<d3>"],
        "word_breakdown": [{{"hanzi": "字", "pinyin": "zì", "english": "meaning"}}],
        "grammar_point": {{"structure": "...", "explanation": "..."}},
        "particle_note": null OR {{"particle": "...", "explanation": "..."}}
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

        # Scrub any leftover slashes
        for bad_sep in ("/", "／"):
            if bad_sep in final_chinese:
                logging.error(f"[GUARDRAIL] Slash in final_chinese — scrubbing")
                final_chinese = final_chinese.split(bad_sep)[0].strip()
            if bad_sep in final_pinyin:
                final_pinyin = final_pinyin.split(bad_sep)[0].strip()

        # Force simplified Chinese across all character-bearing fields
        final_chinese = _force_simplified(final_chinese)

        word_breakdown = []
        for item in raw_data.get("word_breakdown", []):
            word_breakdown.append({
                "chinese": _force_simplified(item.get("hanzi", item.get("chinese", ""))),
                "pinyin": item.get("pinyin", ""),
                "english": item.get("english", "")
            })

        english_correct = raw_data.get("english_correct", "")
        english_distractors = raw_data.get("english_distractors", [])

        # Homophone post-processing for 他/她/它
        if any("他" in g for g in _detect_homophones(final_chinese)):
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

        # Post-process particle_note: drop it if AI labelled a non-particle
        particle_note = raw_data.get("particle_note")
        if particle_note and isinstance(particle_note, dict):
            particle_field = particle_note.get("particle", "")
            # Strip any pinyin/parenthetical, get the actual character(s)
            particle_char = re.sub(r'[（(].*?[)）]|\s*\(.*?\)', '', particle_field).strip()
            particle_char = particle_char.split()[0] if particle_char else ""
            # If the claimed "particle" isn't in our valid list, discard
            if particle_char and not any(p in particle_char for p in TRUE_PARTICLES):
                logging.info(f"[PARTICLE] Discarding fake particle_note for '{particle_char}'")
                particle_note = None

        exercise_data = {
            "chinese": final_chinese,
            "pinyin": final_pinyin,
            "english_correct": english_correct,
            "english_distractors": english_distractors,
            "target_pinyin": pinyin,
            "word_breakdown": word_breakdown,
            "grammar_point": raw_data.get("grammar_point", {}),
            "particle_note": particle_note,
            "target_category": target_category,
            "generation_mode": mode,
        }

        logging.info(f"[GEN] FINAL ({mode}): '{final_chinese}' / '{english_correct}'")

        if mode == 'listen' and len(exercise_data["english_distractors"]) < 3:
            logging.warning(f"Only {len(exercise_data['english_distractors'])} distractors for: {final_chinese}")

        return exercise_data

    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
