"""
Dictionary-grounded word breakdown.

The Dictionary Breakdown is no longer trusted to the LLM. Sentences are
segmented deterministically with jieba and glossed from CC-CEDICT (bundled
with hanzipy). The LLM's gloss for a token is used ONLY when the dictionary
corroborates it (it usually picks the context-appropriate sense better);
otherwise the dictionary wins. This permanently removes the entire class of
"三 glossed as four" errors, independent of how much vocab is loaded.
"""

import logging
import re

from pypinyin import pinyin as _pypinyin, Style as _PinyinStyle

import jieba

jieba.setLogLevel(logging.WARNING)

_dictionary = None


def _get_dictionary():
    global _dictionary
    if _dictionary is None:
        from hanzipy.dictionary import HanziDictionary
        _dictionary = HanziDictionary()
        # hanzipy turns on root DEBUG logging when it loads — undo that.
        logging.getLogger().setLevel(logging.INFO)
    return _dictionary


def is_cjk_char(ch):
    return "\u4e00" <= ch <= "\u9fff"


# ======================================================================
# CHINESE NUMERALS (single source of truth — ai_prompter imports these)
# ======================================================================
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
CN_NUMERAL_CHARS = set(CN_DIGITS) | set(CN_UNITS)


def parse_cn_numeral(s):
    """Parse a run of Chinese numeral characters into an int, or None."""
    if not s or any(ch not in CN_NUMERAL_CHARS for ch in s):
        return None
    total, section, current = 0, 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        else:
            unit = CN_UNITS[ch]
            if unit == 10000:  # 万 closes the whole section
                block = section + current
                total += (block if block else 1) * unit
                section, current = 0, 0
            else:
                if current == 0:
                    current = 1  # 十二 = 12, 百 = 100
                section += current * unit
                current = 0
    return total + section + current


# ======================================================================
# PINYIN (single source of truth — ai_prompter imports derive_pinyin)
# ======================================================================
_PINYIN_OVERRIDES = {"咩": "meh"}


def _char_pinyin_list(text):
    """Context-aware per-character pinyin for a whole sentence, with the
    app's Malaysian conventions (了 -> liǎo, 咩 -> meh)."""
    per_char = _pypinyin(text, style=_PinyinStyle.TONE, errors="default", strict=False)
    # pypinyin on a string returns one item per char, context-aware
    # (e.g. 只 -> zhī after a numeral, 行 -> háng/xíng by context).
    out = []
    i = 0
    for item in per_char:
        ch = text[i] if i < len(text) else ""
        py = item[0] if item else ""
        if ch in _PINYIN_OVERRIDES:
            py = _PINYIN_OVERRIDES[ch]
        elif ch == "了":
            py = "liǎo"
        out.append(py)
        i += 1
    return out


def derive_pinyin(text):
    """Generate pinyin guaranteed to match the characters, context-aware."""
    if not text:
        return ""
    pys = _char_pinyin_list(text)
    syllables = []
    for ch, py in zip(text, pys):
        if is_cjk_char(ch):
            syllables.append(py)
        elif ch.strip() and ch not in "，。！？；：,.!?;: ":
            syllables.append(ch)
    return " ".join(syllables)


# ======================================================================
# CC-CEDICT LOOKUP AND CLEANING
# ======================================================================
_SKIP_SENSE_PREFIXES = (
    "CL:", "surname ", "variant of", "old variant", "Taiwan pr.",
    "also written", "also pr.", "used in", "see ",
)
_MAX_SENSES = 3


def _clean_senses(definition):
    senses = []
    for sense in (definition or "").split("/"):
        sense = sense.strip()
        if not sense:
            continue
        if any(sense.startswith(p) for p in _SKIP_SENSE_PREFIXES):
            continue
        # strip embedded hanzi cross-references like 個|个[ge4]
        sense = re.sub(r"[\u4e00-\u9fff]+\|?[\u4e00-\u9fff]*\[[^\]]*\]", "",
                       sense).strip(" ,;")
        if sense:
            senses.append(sense)
        if len(senses) >= _MAX_SENSES:
            break
    return senses


def cedict_gloss(word, prefer_classifier=False):
    """Return (gloss, all_defs, entry_pinyin_numbered) for a word, or
    ("", "", ""). With prefer_classifier=True, senses/entries describing a
    measure word are ranked first (for tokens directly following a numeral)."""
    try:
        entries = _get_dictionary().definition_lookup(word, "simplified")
    except (KeyError, Exception):
        return "", "", ""
    if not entries:
        return "", "", ""

    def rank(e):
        definition = e.get("definition", "") or ""
        py = e.get("pinyin", "") or ""
        proper = 1 if py[:1].isupper() else 0
        classifier = 0 if ("classifier" in definition and prefer_classifier) else 1
        return (proper, classifier, -len(_clean_senses(definition)))

    entries = sorted(entries, key=rank)
    all_defs = " / ".join(e.get("definition", "") for e in entries)

    if prefer_classifier:
        for e in entries:
            definition = e.get("definition", "") or ""
            if "classifier" in definition:
                for sense in definition.split("/"):
                    sense = sense.strip()
                    if sense.startswith("classifier"):
                        return sense, all_defs, e.get("pinyin", "")
    for e in entries:
        senses = _clean_senses(e.get("definition", ""))
        if senses:
            return " / ".join(senses), all_defs, e.get("pinyin", "")
    return "", all_defs, ""


_TONE_MARKS = {
    "a": "āáǎàa", "e": "ēéěèe", "i": "īíǐìi", "o": "ōóǒòo",
    "u": "ūúǔùu", "ü": "ǖǘǚǜü", "v": "ǖǘǚǜü",
}


def _numbered_to_marks(syllable):
    """Convert CC-CEDICT numbered pinyin ('zhi1') to tone marks ('zhī')."""
    syllable = syllable.strip()
    m = re.match(r"^([A-Za-zü:vV]+)([1-5])$", syllable)
    if not m:
        return syllable
    body, tone = m.group(1).replace("u:", "ü").replace("v", "ü"), int(m.group(2))
    if tone == 5:
        return body
    lower = body.lower()
    # Tone mark placement: a/e first; ou -> o; otherwise last vowel.
    if "a" in lower:
        idx = lower.index("a")
    elif "e" in lower:
        idx = lower.index("e")
    elif "ou" in lower:
        idx = lower.index("o")
    else:
        idx = max(lower.rfind(v) for v in "iouü")
    ch = lower[idx]
    marked = _TONE_MARKS[ch][tone - 1]
    return body[:idx] + marked + body[idx + 1:]


def cedict_pinyin_marks(numbered):
    return " ".join(_numbered_to_marks(s) for s in (numbered or "").split())


_INT_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
              6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
              11: "eleven", 12: "twelve", 20: "twenty", 100: "hundred",
              1000: "thousand"}


def _numeral_gloss(numeral_run):
    value = parse_cn_numeral(numeral_run)
    if value is None:
        return ""
    word = _INT_WORDS.get(value, "")
    return f"{word} ({value})" if word else str(value)


_STOP_WORD = re.compile(
    r"^(the|a|an|to|of|in|on|is|are|be|it|its|for|and|or|with|at|that|this|"
    r"his|her|him|she|he)$", re.I)


def _gloss_supported(llm_gloss, cedict_defs):
    """Loose corroboration: does any substantive word of the LLM's gloss
    appear in the dictionary definitions? Catches wrong glosses like
    三 = 'four' while letting context-narrowed glosses like
    热 = 'hot (weather/places)' through."""
    if not llm_gloss or not cedict_defs:
        return False
    defs_lower = cedict_defs.lower()
    for word in re.findall(r"[A-Za-z]+", llm_gloss.lower()):
        if len(word) >= 3 and not _STOP_WORD.match(word) and word in defs_lower:
            return True
    return False


_registered_words = set()


def register_words(words):
    """Teach jieba domain words (Malaysian slang, the learner's vocab items)
    so segmentation aligns with the terms being studied."""
    for w in words or []:
        w = (w or "").strip()
        if w and len(w) > 1 and w not in _registered_words:
            jieba.add_word(w)
            _registered_words.add(w)


def _greedy_dict_split(token, overrides):
    """Split an out-of-dictionary token into known sub-words by greedy
    longest match (巴刹里 -> [巴刹, 里]). Returns None if no clean split."""
    pieces, i = [], 0
    while i < len(token):
        for length in range(min(4, len(token) - i), 0, -1):
            piece = token[i:i + length]
            if piece in overrides or length == 1 or cedict_gloss(piece)[0]:
                pieces.append(piece)
                i += length
                break
    return pieces if len(pieces) > 1 else None


def _split_numeral_prefix(token):
    """'三只' -> ('三', '只'); '三十五个' -> ('三十五', '个'); '猫' -> ('', '猫')."""
    i = 0
    while i < len(token) and token[i] in CN_NUMERAL_CHARS:
        i += 1
    return token[:i], token[i:]


# ======================================================================
# BREAKDOWN BUILDER
# ======================================================================
def build_breakdown(sentence, llm_breakdown=None, overrides=None,
                    ensure_words=None):
    """Segment `sentence` with jieba and gloss each token.

    Gloss priority per token:
      1. `overrides` (e.g. Malaysian slang senses like 酱 = 'like this')
      2. numeral runs -> computed value ("three (3)"), never guessed
      3. the LLM's gloss for this token, IF corroborated by CC-CEDICT
      4. cleaned CC-CEDICT senses (classifier sense preferred after numerals)
      5. per-character CC-CEDICT composition (rare multi-char misses)
      6. the LLM's gloss uncorroborated (last resort, logged)
    Pinyin is always derived from the sentence context, never trusted.
    """
    overrides = overrides or {}
    register_words(list(overrides.keys()) + list(ensure_words or []))
    llm_gloss_by_token = {}
    for item in (llm_breakdown or []):
        if isinstance(item, dict):
            key = item.get("chinese") or item.get("hanzi") or ""
            if key:
                llm_gloss_by_token[key] = str(item.get("english", "")).strip()

    # Context-aware pinyin for the whole sentence, sliced per token below.
    sentence_pinyin = _char_pinyin_list(sentence)

    # Tokenize; split mixed numeral+noun tokens (三只 -> 三, 只).
    raw_tokens = [t for t in jieba.cut(sentence) if t.strip()]
    tokens = []
    for t in raw_tokens:
        num, rest = _split_numeral_prefix(t)
        if num and rest:
            tokens.extend([num, rest])
            continue
        # Token jieba produced but the dictionary doesn't know (e.g. 巴刹里,
        # 很多): split into known sub-words rather than glossing per-char.
        if (len(t) > 1 and t not in overrides
                and all(is_cjk_char(c) for c in t)
                and not cedict_gloss(t)[0]):
            pieces = _greedy_dict_split(t, overrides)
            if pieces:
                tokens.extend(pieces)
                continue
        tokens.append(t)

    breakdown = []
    cursor = 0
    prev_was_numeral = False
    for token in tokens:
        start = sentence.find(token, cursor)
        if start < 0:
            start = cursor
        end = start + len(token)
        cursor = end

        if not any(is_cjk_char(c) for c in token):
            prev_was_numeral = False
            continue

        token_pinyin = " ".join(
            sentence_pinyin[i] for i in range(start, min(end, len(sentence)))
            if is_cjk_char(sentence[i]))

        is_numeral = all(c in CN_NUMERAL_CHARS for c in token)
        gloss, all_defs, entry_pinyin = cedict_gloss(
            token, prefer_classifier=prev_was_numeral)
        # Measure words after numerals: CC-CEDICT knows the right reading
        # (只 zhī, not zhǐ) better than context-free pypinyin.
        if (prev_was_numeral and gloss.startswith("classifier")
                and entry_pinyin and token != "了"):
            token_pinyin = cedict_pinyin_marks(entry_pinyin)
        llm_gloss = llm_gloss_by_token.get(token, "")
        english = ""

        if token in overrides:
            english = overrides[token]
        elif is_numeral and len(token) > 0:
            english = _numeral_gloss(token) or gloss
        elif llm_gloss and _gloss_supported(llm_gloss, all_defs):
            english = llm_gloss           # context-appropriate, dictionary-backed
        elif gloss:
            english = gloss               # dictionary wins over unsupported LLM gloss
            if llm_gloss:
                logging.warning(
                    f"[DICT] LLM gloss for '{token}' ('{llm_gloss}') not supported "
                    f"by CC-CEDICT — using dictionary: '{gloss}'")
        else:
            parts = []
            for ch in token:
                ch_gloss, _, _ = cedict_gloss(ch)
                if ch_gloss:
                    parts.append(f"{ch}: {ch_gloss.split(' / ')[0]}")
            if parts:
                english = " + ".join(parts)
            elif llm_gloss:
                english = llm_gloss
                logging.warning(f"[DICT] No dictionary entry for '{token}'; "
                                f"falling back to LLM gloss '{llm_gloss}'")
            else:
                prev_was_numeral = is_numeral
                continue

        breakdown.append({
            "chinese": token,
            "pinyin": token_pinyin,
            "english": english,
        })
        prev_was_numeral = is_numeral
    return breakdown
