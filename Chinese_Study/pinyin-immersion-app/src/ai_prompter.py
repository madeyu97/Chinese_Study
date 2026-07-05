# src/ai_prompter.py

import os
import re
import json
import random
import logging
from groq import Groq
from dotenv import load_dotenv
from pypinyin import pinyin as _pypinyin, Style as _PinyinStyle

from config import GENERATION_MODEL

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

TRUE_PARTICLES = {"啦", "咯", "咩", "咧", "啊", "嘛", "喎", "罢了", "了", "吗", "呢", "吧",
                  "哎哟", "哎呀", "哦", "喔", "唉"}

TIME_WORDS = {"今天", "昨天", "明天", "现在", "刚才", "以前", "以后", "之前", "之后",
              "早上", "晚上", "下午", "中午", "上个", "下个"}
NEGATIONS = {"不", "没", "没有", "别", "甭"}
QUANTIFIERS = {"一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
               "百", "千", "万", "几", "多", "少", "些", "都"}

SENTENCE_PUNCTUATION = "。!?，,!?;"
SYNONYM_SEPARATORS_REGEX = r'\s*(?:[/／;；]|\s或\s)\s*'


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
    # Only a quantifier if the WHOLE token is quantifier material
    # (一起, 都市, 多少钱 etc. must NOT be classified as quantifiers).
    if chinese_chars in QUANTIFIERS or all(c in QUANTIFIERS for c in chinese_chars):
        return "quantifier"
    return "content_word"


def _find_relevant_slang(chinese_text):
    return {k: v for k, v in MALAYSIAN_SLANG.items() if k in chinese_text}


def _detect_homophones(chinese_text):
    return [g for g in HOMOPHONE_GROUPS if any(ch in chinese_text for ch in g)]


TRAD_TO_SIMP = {
    "養": "养", "貓": "猫", "個": "个", "們": "们", "麼": "么", "後": "后",
    "說": "说", "話": "话", "買": "买", "賣": "卖", "兒": "儿", "對": "对",
    "點": "点", "現": "现", "時": "时", "間": "间", "問": "问", "學": "学",
    "覺": "觉", "錢": "钱", "幾": "几", "過": "过", "還": "还", "這": "这",
    "為": "为", "從": "从", "車": "车", "頭": "头", "聽": "听", "讀": "读",
    "寫": "写", "電": "电", "視": "视", "業": "业", "戰": "战", "農": "农",
    "難": "难", "馬": "马", "鳥": "鸟", "魚": "鱼", "蘋": "苹", "蔥": "葱",
    "醫": "医", "藥": "药", "體": "体", "鐵": "铁", "鋼": "钢",
}

def _force_simplified(text):
    if not text:
        return text
    result = "".join(TRAD_TO_SIMP.get(ch, ch) for ch in text)
    if result != text:
        logging.info(f"[SIMP] Converted: '{text}' -> '{result}'")
    return result


# ======================================================================
# DETERMINISTIC PINYIN — the LLM can no longer desync pinyin from hanzi.
# Pinyin is derived directly from the characters via pypinyin, with the
# app's Malaysian overrides applied (了 -> liǎo, 咩 -> meh).
# ======================================================================
_PINYIN_OVERRIDES = {"咩": "meh"}

def _is_cjk_char(ch):
    return "\u4e00" <= ch <= "\u9fff"

def _derive_pinyin(text):
    """Generate pinyin that is guaranteed to match the characters."""
    if not text:
        return ""
    syllables = []
    # Walk chars ourselves so punctuation/latin passes through in order.
    per_char = _pypinyin(list(text), style=_PinyinStyle.TONE, errors="default")
    for ch, py in zip(text, per_char):
        if _is_cjk_char(ch):
            if ch in _PINYIN_OVERRIDES:
                syllables.append(_PINYIN_OVERRIDES[ch])
            elif ch == "了":
                # Malaysian Mandarin design choice: 了 is read liǎo
                syllables.append("liǎo")
            else:
                syllables.append(py[0])
        elif ch.strip() and ch not in "，。！？；：,.!?;: ":
            syllables.append(ch)
    return " ".join(syllables)


# ======================================================================
# NUMERAL VERIFICATION — fixes the "三 glossed as 4" class of LLM errors
# deterministically, and detects sentence-level number mismatches so the
# exercise can be regenerated instead of shown wrong.
# ======================================================================
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CN_NUMERAL_CHARS = set(_CN_DIGITS) | set(_CN_UNITS)

_EN_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000,
}
_INT_TO_EN = {v: k for k, v in _EN_NUMBER_WORDS.items()}

def _parse_cn_numeral(s):
    """Parse a run of Chinese numeral characters into an int. Returns None
    if it isn't a well-formed numeral."""
    if not s or any(ch not in _CN_NUMERAL_CHARS for ch in s):
        return None
    total, section, current = 0, 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        else:
            unit = _CN_UNITS[ch]
            if unit == 10000:  # 万 closes the whole section
                block = section + current
                total += (block if block else 1) * unit
                section, current = 0, 0
            else:
                if current == 0:
                    current = 1  # e.g. 十二 = 12, 百 = 100
                section += current * unit
                current = 0
    return total + section + current

def _numbers_in_hanzi(text):
    """All integers expressed as numeral runs inside a Chinese sentence."""
    nums = set()
    for match in re.finditer(
            "[" + "".join(_CN_NUMERAL_CHARS) + "]+", text or ""):
        val = _parse_cn_numeral(match.group())
        if val is not None:
            nums.add(val)
    return nums

def _numbers_in_english(text):
    """All integers mentioned in an English sentence (digits or words)."""
    nums = set()
    for match in re.finditer(r"\d+", text or ""):
        nums.add(int(match.group()))
    for word in re.findall(r"[A-Za-z]+", (text or "").lower()):
        if word in _EN_NUMBER_WORDS:
            nums.add(_EN_NUMBER_WORDS[word])
    return nums

def _has_number_mismatch(hanzi, english):
    """True when the English mentions numbers, the Chinese contains numerals,
    and NONE of them agree — e.g. 三 rendered as 'four'."""
    han = _numbers_in_hanzi(hanzi)
    eng = _numbers_in_english(english)
    if not han or not eng:
        return False
    return han.isdisjoint(eng)

def _fix_numeral_gloss(item_hanzi, item_english):
    """If a breakdown item is (or starts with) a numeral and its English
    gloss names the wrong number, rewrite it deterministically."""
    numeral_run = ""
    for ch in item_hanzi:
        if ch in _CN_NUMERAL_CHARS:
            numeral_run += ch
        else:
            break
    if not numeral_run:
        return item_english
    value = _parse_cn_numeral(numeral_run)
    if value is None:
        return item_english
    glossed = _numbers_in_english(item_english)
    if glossed and value not in glossed:
        word = _INT_TO_EN.get(value, str(value))
        if numeral_run == item_hanzi:
            corrected = f"{word} ({value})"
        else:
            rest = item_hanzi[len(numeral_run):]
            corrected = f"{word} ({value}) + measure/word '{rest}'"
        logging.warning(
            f"[NUMFIX] '{item_hanzi}' glossed as '{item_english}' "
            f"-> corrected to '{corrected}'")
        return corrected
    return item_english

def _verify_breakdown(word_breakdown, sentence):
    """Drop confabulated breakdown entries, re-derive their pinyin, and fix
    numeral glosses. Every surviving entry is guaranteed to (a) appear in
    the sentence, (b) have pinyin matching its own characters."""
    verified = []
    for item in word_breakdown:
        hz = item.get("chinese", "")
        if not hz:
            continue
        if all(_is_cjk_char(c) for c in hz) and hz not in sentence:
            logging.warning(f"[BREAKDOWN] Dropping '{hz}' — not in sentence.")
            continue
        item["pinyin"] = _derive_pinyin(hz)
        item["english"] = _fix_numeral_gloss(hz, item.get("english", ""))
        verified.append(item)
    return verified


# ======================================================================
# PRONOUN NORMALISATION — now IDEMPOTENT
# Both lookbehind and lookahead skip words that already have a slash on
# either side, so running the function multiple times produces the same
# result. Fixes the "He/He/She" bug from re-normalising AI output.
# ======================================================================
def _normalize_ta_pronouns(text):
    """Rewrite English pronouns so 'He' and 'She' both become 'He/She' etc.
    Safe to call repeatedly — won't double-normalise already-slashed text."""
    if not text:
        return text

    def cap_sub(m):  return "He/She"
    def low_sub(m):  return "he/she"
    def cap_him(m):  return "Him/Her"
    def low_him(m):  return "him/her"
    def cap_his(m):  return "His/Her"
    def low_his(m):  return "his/her"

    # Key change: (?<!/) negative lookbehind + (?!/) negative lookahead.
    # A word is normalised only if there's no '/' on EITHER side.

    # Subject pronouns (handles "He's", "She'll" etc. via word boundary)
    text = re.sub(r"(?<!/)\b(?:He|She)\b(?!/)",  cap_sub, text)
    text = re.sub(r"(?<!/)\b(?:he|she)\b(?!/)",  low_sub, text)

    # 'him' — object
    text = re.sub(r"(?<!/)\bHim\b(?!/)", cap_him, text)
    text = re.sub(r"(?<!/)\bhim\b(?!/)", low_him, text)

    # 'his' — possessive
    text = re.sub(r"(?<!/)\bHis\b(?!/)", cap_his, text)
    text = re.sub(r"(?<!/)\bhis\b(?!/)", low_his, text)

    # 'her' — possessive if followed by word, else object
    text = re.sub(r"(?<!/)\bHer\b(?=\s+\w)(?!/)", cap_his, text)
    text = re.sub(r"(?<!/)\bher\b(?=\s+\w)(?!/)", low_his, text)
    text = re.sub(r"(?<!/)\bHer\b(?!/)",          cap_him, text)
    text = re.sub(r"(?<!/)\bher\b(?!/)",          low_him, text)

    return text


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

    if is_locked:
        sentence_instruction = f"""
        LOCKED SENTENCE: '{chinese_chars}'. Use EXACTLY this — do not alter.
        Meaning: '{english}'
        """
    elif mode == 'recall':
        sentence_instruction = f"""
        RECALL MODE — CRITICAL CONSTRAINTS:

        The user will be shown ONLY the English translation and asked to speak
        the Chinese from memory. The Chinese sentence MUST be PREDICTABLE.

        STRICT RULES:
        1. Use the target word '{chinese_chars}' ({pinyin}, "{english}") in a
           SHORT, SIMPLE sentence (4-8 words).
        2. The Chinese sentence must contain ONLY vocabulary explicitly implied
           by the English. NO idiomatic additions.
        3. BAD: English "Her cat is very cute" -> Chinese "她养的猫很可爱" (adds 养)
        4. GOOD: English "Her cat is very cute" -> Chinese "她的猫很可爱"
        5. If using '了', transcribe pinyin as 'liǎo'. If '咩', as 'meh'.
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

    if mode == 'listen':
        distractor_section = f"""
    ═══════════════════════════════════════════════════════════════════
    TARGET-AWARE DISTRACTOR DESIGN
    ═══════════════════════════════════════════════════════════════════

    Target: '{chinese_chars}' Category: {target_category.upper()}

    {playbook}

    UNIVERSAL RULES:
    1. Distractors attack the TARGET's learning axis.
    2. NO trivial distractors.
    3. Roughly equal length English options.
    4. Plausibility test: could an ~80% listener genuinely pick this?
    """
    else:
        distractor_section = """
    Include 3 minimal placeholder distractors for data shape consistency.
    """

    prompt = f"""
    You are an expert Malaysian Mandarin tutor.

    {sentence_instruction}

    {slang_section}

    {full_slang_reference}

    GLOBAL RULES:
    1. STRICT SYNCHRONIZATION between characters and pinyin.
    2. SIMPLIFIED CHINESE ONLY. Use 养 not 養, 猫 not 貓, 们 not 們, etc.
    3. NO INVENTED NAMES — use pronouns.
    4. Arabic numerals -> Chinese characters.
    5. 'hanzi' field MUST NEVER contain '/' or '／' or ';'.

    {distractor_section}

    HOMOPHONES (CRITICAL):
    If the sentence contains 他/她/它 (all pronounced 'tā'), the listener
    CANNOT distinguish gender from audio. Therefore:
    - Write the correct English using "He/She" (not just "He" or "She").
      Same for "him/her" and "his/her".
    - Distractors must use the same "He/She" / "him/her" / "his/her" form
      AND must NOT vary on the pronoun alone — they must differ on a content
      word, time, negation, particle, or quantifier.

    Output a raw JSON object:
    {{
        "hanzi": "<sentence>",
        "pinyin": "<matching pinyin>",
        "english_correct": "<accurate translation>",
        "english_distractors": ["<d1>", "<d2>", "<d3>"],
        "word_breakdown": [{{"hanzi": "字", "pinyin": "zì", "english": "meaning"}}],
        "grammar_point": {{"structure": "...", "explanation": "..."}},
        "particle_note": null OR {{"particle": "...", "explanation": "..."}}
    }}
    """

    MAX_ATTEMPTS = 3
    raw_data = None
    final_chinese = ""
    english_correct = ""

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = client.chat.completions.create(
                messages=[{'role': 'user', 'content': prompt}],
                model=GENERATION_MODEL,
                response_format={"type": "json_object"}
            )
            candidate = json.loads(response.choices[0].message.content)

            if is_locked:
                cand_chinese = chinese_chars
            else:
                cand_chinese = candidate.get("hanzi", candidate.get("chinese", ""))

            for bad_sep in ("/", "／"):
                if bad_sep in cand_chinese:
                    logging.error("[GUARDRAIL] Slash in generated hanzi — scrubbing")
                    cand_chinese = cand_chinese.split(bad_sep)[0].strip()

            cand_chinese = _force_simplified(cand_chinese)
            cand_english = candidate.get("english_correct", "")

            # ── VALIDATION GATE ─────────────────────────────────────────
            # Reject and regenerate if:
            #   a) the sentence or translation came back empty
            #   b) the numbers in the English contradict the numbers in the
            #      Chinese (the "三 translated as four" bug)
            #   c) a non-locked sentence dropped the target word entirely
            problems = []
            if not cand_chinese.strip() or not cand_english.strip():
                problems.append("empty hanzi/translation")
            if _has_number_mismatch(cand_chinese, cand_english):
                problems.append(
                    f"number mismatch: hanzi has {_numbers_in_hanzi(cand_chinese)}, "
                    f"english says {_numbers_in_english(cand_english)}")
            if not is_locked and chinese_chars and chinese_chars not in cand_chinese:
                problems.append(f"target '{chinese_chars}' missing from sentence")

            if not problems:
                raw_data = candidate
                final_chinese = cand_chinese
                english_correct = cand_english
                break

            logging.warning(f"[VALIDATE] Attempt {attempt}/{MAX_ATTEMPTS} rejected: "
                            f"{'; '.join(problems)} — '{cand_chinese}' / '{cand_english}'")
            raw_data = candidate           # keep best-effort fallback
            final_chinese = cand_chinese
            english_correct = cand_english

        if raw_data is None:
            return None

        # ── DETERMINISTIC PINYIN ───────────────────────────────────────
        # Pinyin is derived from the characters, never trusted from the LLM,
        # so the spoken/written/pinyin trio can no longer disagree.
        if is_locked and pinyin:
            final_pinyin = pinyin  # user-authored CSV pinyin is authoritative
        else:
            final_pinyin = _derive_pinyin(final_chinese)

        word_breakdown = []
        for item in raw_data.get("word_breakdown", []):
            if not isinstance(item, dict):
                continue
            word_breakdown.append({
                "chinese": _force_simplified(item.get("hanzi", item.get("chinese", ""))),
                "pinyin": item.get("pinyin", ""),
                "english": str(item.get("english", ""))
            })
        # Drop confabulated entries, fix numeral glosses, re-derive pinyin
        word_breakdown = _verify_breakdown(word_breakdown, final_chinese)

        english_distractors = [str(d) for d in raw_data.get("english_distractors", [])
                               if isinstance(d, (str, int, float)) and str(d).strip()]

        # Normalise pronouns when 他/她/它 is in the sentence — idempotent
        if any("他" in g for g in _detect_homophones(final_chinese)):
            english_correct = _normalize_ta_pronouns(english_correct)
            english_distractors = [_normalize_ta_pronouns(d) for d in english_distractors]

        # ── ALWAYS dedupe distractors and remove any that equal the answer.
        # (Previously this only ran for pronoun sentences, so duplicate MCQ
        # options could appear in ordinary exercises.)
        seen = set()
        unique_distractors = []
        for d in english_distractors:
            key = d.strip().lower()
            if key and key != english_correct.strip().lower() and key not in seen:
                seen.add(key)
                unique_distractors.append(d)
        english_distractors = unique_distractors

        if len(english_distractors) < 3:
            logging.warning(
                f"[DISTRACTORS] Only {len(english_distractors)} usable distractors "
                f"for: {final_chinese}"
            )

        # Particle confabulation filter
        particle_note = raw_data.get("particle_note")
        if particle_note and isinstance(particle_note, dict):
            particle_field = particle_note.get("particle", "")
            particle_char = re.sub(r'[（(].*?[)）]|\s*\(.*?\)', '', particle_field).strip()
            particle_char = particle_char.split()[0] if particle_char else ""
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
        return exercise_data

    except Exception as e:
        logging.error(f"Generation Error via Groq: {e}")
        return None
