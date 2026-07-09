# src/ai_prompter.py

import os
import re
import json
import random
import logging
from groq import Groq
from dotenv import load_dotenv
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from dictionary_engine import (
    derive_pinyin as _derive_pinyin,
    parse_cn_numeral as _parse_cn_numeral,
    CN_NUMERAL_CHARS as _CN_NUMERAL_CHARS,
    is_cjk_char as _is_cjk_char,
    build_breakdown,
)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ----------------------------------------------------------------------
# Malaysian Mandarin colloquialisms
# ----------------------------------------------------------------------
MALAYSIAN_SLANG = {
    "酱": ("sauce (literal)", "colloquial contraction of 这样 — 'like this / so / that'"),
    "啊那": ("(none)", "contraction of 那个 — 'that one / um'"),
    "烧": ("to burn (literal)", "hot TO THE TOUCH only — food, drinks, objects "
           "(烧水 hot water, 咖啡很烧). NEVER for weather, rooms, or places; "
           "hot weather/places use 热 (今天很热, 巴刹很热)"),
    "怕输": ("(literal: afraid of losing)", "kiasu — fear of missing out"),
    "做工": ("to do work (literal)", "to work / go to work — used where mainland says 上班"),
    "讲": ("to speak (literal)", "preferred over 说 in casual speech"),
    "要": ("to want (literal)", "future 'going to' for INTENTIONS/plans only "
           "(我明天要去) — not for predictions or abilities, which still use 会 "
           "(明天会下雨, 他会讲华语)"),
    "几时": ("(uncommon in PRC)", "Malaysian for 'when' — instead of 什么时候"),
    "罢了": ("(literary)", "casual 'only / just' — like 而已"),
    "巴刹": ("(none)", "from Malay 'pasar' — wet market"),
    "甘榜": ("(none)", "from Malay 'kampung' — village"),
}

# Short senses for the Dictionary Breakdown where CC-CEDICT lacks (or buries)
# the Malaysian usage. Keys not listed fall through to CEDICT normally.
SLANG_BREAKDOWN_GLOSS = {
    "酱": "like this / so (Malaysian, = 这样)",
    "啊那": "that one / um (Malaysian filler, = 那个)",
    "怕输": "kiasu — afraid of losing out",
    "做工": "to work / go to work (Malaysian, = 上班)",
    "几时": "when? (Malaysian, = 什么时候)",
    "罢了": "only / just (= 而已)",
    "巴刹": "wet market (Malay loanword: pasar)",
    "甘榜": "village (Malay loanword: kampung)",
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
# NUMERAL VERIFICATION — pinyin derivation and numeral parsing now live in
# dictionary_engine (single source of truth, shared with the breakdown).
# ======================================================================
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


# ======================================================================
# GRAMMAR REVIEW GATE
# A second, independent LLM pass that checks every generated sentence
# BEFORE it is shown to the learner. Catches ungrammatical output like
# 我想把我的成绩更好 (a 把-sentence with no verb), which the deterministic
# checks (numbers, pinyin sync) cannot see. If the sentence fails review,
# the generation loop retries with the reviewer's feedback injected.
# ======================================================================
def _format_flagged_for_review(flagged_examples):
    if not flagged_examples:
        return ""
    lines = "\n".join(f"- {s}" + (f"  ({r})" if r else "")
                      for s, r in flagged_examples[:8])
    return ("\nThe learner has previously flagged these sentences as wrong — "
            "reject anything with the same kind of mistake:\n" + lines + "\n")


def _review_grammar(sentence, english, flagged_examples=None):
    review_prompt = f"""
You are a strict native-speaker reviewer of Mandarin Chinese teaching
material. Judge ONLY whether this sentence is grammatical, natural
Mandarin (Malaysian colloquialisms like 酱/做工/罢了/咩 are acceptable
and must NOT be marked as errors), and whether the English translation
is accurate.

SENTENCE: {sentence}
CLAIMED MEANING: {english}
{_format_flagged_for_review(flagged_examples)}

Check with particular care:
- 把-construction: the object MUST be followed by a verb with a result,
  complement, or directional. "把 + object + adjective" (e.g. 把成绩更好)
  is WRONG — there is no verb.
- Resultative/degree complements used correctly (V + 得/好/完/到...).
- 更/最/很 + adjective needs a proper predicate structure (变得更好,
  让...更好), not a bare hanging adjective phrase.
- Measure words match their nouns.
- 比 comparisons formed correctly.
- WORD CHOICE must be semantically correct, not just syntactically legal.
  Reject colloquialisms shoehorned into contexts where they don't apply.
  Example: Malaysian 烧 means hot TO THE TOUCH (food/drinks/objects: 咖啡
  很烧); it can NEVER describe hot weather, rooms, or places — 烧的巴刹 is
  WRONG, a hot market is 很热的巴刹. Similarly reject any word used outside
  its real meaning even if the sentence parses.
- The sentence must describe something that makes real-world sense.
- The English translation matches the actual meaning of the sentence.

Return ONLY raw JSON:
{{
  "acceptable": true/false,
  "problems": "<empty string if acceptable, otherwise a one-line diagnosis>",
  "corrected_sentence": "<empty string if acceptable, otherwise a corrected, natural version keeping the same intended meaning>"
}}
""".strip()
    def _call_reviewer(model):
        kwargs = dict(
            messages=[{"role": "user", "content": review_prompt}],
            model=model,
            response_format={"type": "json_object"},
            temperature=0,
        )
        if "qwen" in model:
            # Qwen models on Groq emit reasoning by default; turn it off so
            # the response is pure JSON.
            kwargs["reasoning_effort"] = "none"
        resp = client.chat.completions.create(**kwargs)
        return json.loads(resp.choices[0].message.content)

    try:
        # REVIEW_MODEL is deliberately a DIFFERENT model family from the
        # generator, so an error must fool two independent models to get
        # through. If the preview model is unavailable, fall back to the
        # production model rather than skipping review.
        try:
            verdict = _call_reviewer(REVIEW_MODEL)
        except Exception as first_err:
            logging.warning(f"[REVIEW] {REVIEW_MODEL} failed ({first_err}); "
                            f"falling back to {GRADING_MODEL}")
            verdict = _call_reviewer(GRADING_MODEL)
        return {
            "acceptable": bool(verdict.get("acceptable", True)),
            "problems": str(verdict.get("problems", "") or ""),
            "corrected_sentence": str(verdict.get("corrected_sentence", "") or ""),
        }
    except Exception as e:
        # Fail open: a broken reviewer should not block study sessions.
        logging.warning(f"[REVIEW] Grammar review failed (skipping): {e}")
        return {"acceptable": True, "problems": "", "corrected_sentence": ""}


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


def generate_distractors_for(chinese, english_correct, n=3):
    """Distractors for an existing (human-written) sentence — used by the
    Tatoeba seeder. The sentence itself is never touched, so grammar risk
    is zero; only the wrong-answer options come from the LLM."""
    target_category = _classify_target("", english_correct)
    playbook = DISTRACTOR_PLAYBOOKS.get(target_category,
                                        DISTRACTOR_PLAYBOOKS["general"])
    has_ta = any("他" in g for g in _detect_homophones(chinese))
    pronoun_rule = ""
    if has_ta:
        pronoun_rule = ("The sentence contains 他/她/它 (all 'tā'): use "
                        "He/She, him/her, his/her forms, and never vary a "
                        "distractor on the pronoun alone.")
    prompt = f"""
Create exactly {n} plausible WRONG English translations (distractors) for a
listening comprehension exercise.

CHINESE SENTENCE: {chinese}
CORRECT TRANSLATION: {english_correct}

{playbook}
{pronoun_rule}

Each distractor must be clearly wrong for a listener who understood the
sentence, but tempting for one who misheard a single element (content word,
time, negation, number, or particle). Same register and similar length as
the correct translation.

Return ONLY raw JSON: {{"english_distractors": ["<d1>", "<d2>", "<d3>"]}}
""".strip()
    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GENERATION_MODEL,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        raw = [str(d) for d in data.get("english_distractors", [])
               if isinstance(d, (str, int, float)) and str(d).strip()]
    except Exception as e:
        logging.error(f"[DISTRACTORS] generation failed: {e}")
        return []

    correct = english_correct
    if has_ta:
        correct = _normalize_ta_pronouns(correct)
        raw = [_normalize_ta_pronouns(d) for d in raw]
    seen, out = set(), []
    for d in raw:
        key = d.strip().lower()
        if key and key != correct.strip().lower() and key not in seen:
            seen.add(key)
            out.append(d)
    return out[:n]


def generate_dictation_exercise(target_word_dict, mode='listen',
                                blocked_sentences=None, flagged_examples=None):
    """blocked_sentences: set of Chinese sentences the learner has flagged —
    never produce these again. flagged_examples: recent (sentence, reason)
    pairs injected into the prompts so every flag permanently strengthens
    both the generator and the reviewer."""
    blocked_sentences = blocked_sentences or set()
    flagged_examples = flagged_examples or []
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

    full_slang_reference = (
        "MALAYSIAN COLLOQUIAL GLOSSARY (for RECOGNITION and register — do NOT "
        "force these into the sentence. Only use a colloquialism when it is "
        "natural AND semantically correct for the context. When in doubt, use "
        "standard Mandarin. Respect each entry's usage constraints exactly):\n")
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

    def build_prompt(reviewer_feedback_section=""):
        flagged_section = ""
        if flagged_examples:
            lines = "\n".join(
                f"       - {s}" + (f"  ({r})" if r else "")
                for s, r in flagged_examples[:8])
            flagged_section = f"""
    SENTENCES THE LEARNER FLAGGED AS WRONG (never produce these, or
    sentences with the same kind of mistake):
{lines}
"""
        return f"""
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

    GRAMMATICALITY (CRITICAL — the sentence teaches a learner):
    a. The sentence must be fully grammatical, natural Mandarin a native
       speaker would actually say. If unsure, use a SIMPLER structure.
    b. 把-construction: 把 + object MUST be followed by a VERB plus a
       result/complement/directional. NEVER "把 + object + adjective".
       WRONG: 我想把我的成绩更好 (no verb!)
       RIGHT: 我想把我的成绩提高 / 我想让我的成绩更好
    c. 更/最 + adjective needs a proper predicate (变得更好, 让...更好),
       never left dangling after an object.
    d. Measure words must match their nouns; 比 comparisons must be
       correctly formed.
{reviewer_feedback_section}
{flagged_section}
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
    reviewer_feedback = ""

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            feedback_section = ""
            if reviewer_feedback:
                feedback_section = f"""
    YOUR PREVIOUS ATTEMPT WAS REJECTED BY A NATIVE-SPEAKER REVIEWER:
    {reviewer_feedback}
    Produce a NEW, fully grammatical sentence that fixes this.
"""
            response = client.chat.completions.create(
                messages=[{'role': 'user', 'content': build_prompt(feedback_section)}],
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
            if cand_chinese in blocked_sentences:
                problems.append("sentence previously flagged by learner")

            # ── GRAMMAR REVIEW GATE ─────────────────────────────────────
            # Independent second-pass check for grammaticality/naturalness
            # (catches e.g. verbless 把-sentences). Skipped for locked CSV
            # sentences, which are user-authored, and for candidates that
            # already failed the deterministic checks.
            review = None
            if not problems and not is_locked:
                review = _review_grammar(cand_chinese, cand_english,
                                          flagged_examples=flagged_examples)
                if not review["acceptable"]:
                    problems.append(f"grammar review: {review['problems']}")
                    reviewer_feedback = (
                        f"Sentence: {cand_chinese}\n    Problem: {review['problems']}")

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

            # Last resort on the final attempt: if the reviewer supplied a
            # corrected sentence, teach THAT instead of the broken one. The
            # breakdown verifier will drop any entries that no longer match.
            if (attempt == MAX_ATTEMPTS and review is not None
                    and review["corrected_sentence"].strip()):
                corrected = _force_simplified(review["corrected_sentence"].strip())
                logging.warning(
                    f"[REVIEW] Using reviewer's corrected sentence: "
                    f"'{final_chinese}' -> '{corrected}'")
                final_chinese = corrected

        if raw_data is None:
            return None

        # ── DETERMINISTIC PINYIN ───────────────────────────────────────
        # Pinyin is derived from the characters, never trusted from the LLM,
        # so the spoken/written/pinyin trio can no longer disagree.
        if is_locked and pinyin:
            final_pinyin = pinyin  # user-authored CSV pinyin is authoritative
        else:
            final_pinyin = _derive_pinyin(final_chinese)

        # ── DICTIONARY-GROUNDED BREAKDOWN ─────────────────────────────
        # The breakdown is built from jieba segmentation + CC-CEDICT, not
        # trusted to the LLM. LLM glosses are used only where the dictionary
        # corroborates them; Malaysian slang senses override where CEDICT
        # lacks them. Scales to any vocab size with zero added error rate.
        llm_breakdown = [item for item in raw_data.get("word_breakdown", [])
                         if isinstance(item, dict)]
        for item in llm_breakdown:
            if "hanzi" in item and "chinese" not in item:
                item["chinese"] = _force_simplified(item.get("hanzi", ""))
        slang_overrides = {
            k: SLANG_BREAKDOWN_GLOSS[k]
            for k in SLANG_BREAKDOWN_GLOSS if k in final_chinese
        }
        word_breakdown = build_breakdown(
            final_chinese, llm_breakdown=llm_breakdown,
            overrides=slang_overrides,
            ensure_words=[chinese_chars] + list(MALAYSIAN_SLANG.keys()))

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
