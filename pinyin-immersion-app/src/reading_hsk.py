# src/reading_hsk.py
"""
Graded reading for the HSK track: short passages at your reading level.

Each passage is a few connected sentences - a scene, a message, a short
story - in everyday Malaysian Mandarin, built from HSK words up to your
reading level, with at most MAX_NEW words above it (declared, with pinyin
and English). It reuses grammar you've drilled, and ends with one
comprehension question in English.

Everything a passage needs on screen is worked out when it is written and
stored with it - the words (jieba, kept whole where they're HSK words),
each word's pinyin, meaning and HSK level - so reading one is instant.
Passages are written ahead (ahead.reading, tools/fill_bank.py), never
while you wait unless the stock has run out.

    analyse(text, level)         word by word: in level / new / other
    check(payload, level)        what's wrong with a draft, [] if nothing
    generate(level, ...)         write, check, review -> payload or None
"""

import logging
import re

import hsk

MAX_NEW = 3                       # words above the level, declared
MIN_COVERAGE = 0.93               # share of words at or below the level
LENGTH = {1: (50, 100), 2: (80, 140), 3: (110, 200), 4: (150, 260)}   # characters
TOPICS = ("a morning at the hawker centre", "taking the bus in town", "a weekend plan",
          "a message to a friend", "buying fruit at the market", "the weather today",
          "a visit to the doctor", "a phone call home", "a day at work", "cooking dinner",
          "a birthday", "looking for a flat", "a rainy afternoon", "a trip to Penang",
          "learning Chinese", "a new neighbour", "shopping for clothes", "a lost phone",
          "the gym", "a family dinner", "a holiday by the sea", "a café", "a train journey",
          "a festival", "a school day", "a wedding", "moving house", "a football match")

_PUNCT = "，。！？、；：“”‘’（）…—《》 \n"
# grammar words, particles and numbers: fine at any level
_FREE = set("的了吗呢吧啊呀着过地得们个一二三四五六七八九十百千万零两几么这那也都就才还又再不没很太")


def _cjk(text):
    return [c for c in text if "一" <= c <= "鿿"]


def _known(level):
    return {w["word"] for w in hsk.words_upto(level, include_erhua=True)}


def _splits(token, known, chars=frozenset()):
    """Can the token be made of known words (今天下午 = 今天 + 下午), or of
    known words and characters of the level (一杯 = 一 + 杯)?"""
    n = len(token)
    ok = [True] + [False] * n
    for i in range(n):
        if ok[i]:
            for j in range(i + 1, n + 1):
                if token[i:j] in known or (j == i + 1 and (token[i] in _FREE
                                                           or token[i] in chars)):
                    ok[j] = True
    return ok[n]


def words_of(text):
    import jieba
    out = []
    for tok in jieba.lcut(text):
        if not tok.strip():
            continue
        out.append(tok)
    return out


def analyse(text, level, declared=()):
    """[{"w", "status"}] for each word: "in" (at or below the level),
    "new" (declared above-level word), "out" (above the level, undeclared),
    "punct"."""
    known, declared = _known(level), set(declared)
    chars = frozenset(hsk.recognise_chars(level))
    out = []
    for w in words_of(text):
        if not _cjk(w):
            out.append({"w": w, "status": "punct"})
        elif w in known or all(c in _FREE for c in w) or (
                len(w) > 1 and _splits(w, known, chars if len(w) <= 3 else frozenset())):
            out.append({"w": w, "status": "in"})
        elif w in declared or any(d in w for d in declared):
            out.append({"w": w, "status": "new"})
        else:
            out.append({"w": w, "status": "out"})
    return out


def coverage(analysis):
    words = [a for a in analysis if a["status"] != "punct"]
    return sum(a["status"] == "in" for a in words) / len(words) if words else 0.0


def check(payload, level):
    """What's wrong with a drafted passage ([] if nothing)."""
    from dictionary_engine import has_erhua
    p = []
    if not isinstance(payload, dict):
        return ["not a JSON object"]
    text = str(payload.get("text") or "").strip()
    lo, hi = LENGTH[level]
    n = len(_cjk(text))
    if not (lo <= n <= hi):
        p.append(f"text is {n} characters; it must be {lo}-{hi}")
    if re.search(r"[A-Za-z0-9]", text):
        p.append("digits or Latin letters in the text - write numbers in Chinese")
    if has_erhua(text):
        p.append("uses Beijing 儿 - write it the Malaysian way (哪里, 一点, 这里)")
    if not str(payload.get("title") or "").strip() or not str(payload.get("english") or "").strip():
        p.append("needs a Chinese title and an English translation")
    new = [w for w in payload.get("new_words") or [] if isinstance(w, dict) and w.get("hanzi")]
    if len(new) > MAX_NEW:
        p.append(f"declares {len(new)} new words; at most {MAX_NEW}")
    for w in new:
        if not w.get("english"):
            p.append(f"new word {w['hanzi']} needs its English")
    a = analyse(text, level, [w["hanzi"] for w in new])
    out = sorted({x["w"] for x in a if x["status"] == "out"})
    if out:
        p.append("uses words above HSK " + str(level) + " that weren't declared: "
                 + "、".join(out) + " - replace them with easier words, or declare up to "
                 f"{MAX_NEW} in new_words")
    elif coverage(a) < MIN_COVERAGE:
        p.append("too many new words for this level")
    q = payload.get("question")
    if not (isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list)
            and len(q["options"]) == 3 and isinstance(q.get("answer"), int)
            and 0 <= q["answer"] < 3 and len({str(o) for o in q["options"]}) == 3):
        p.append("question needs: question, three different options, answer (0-2)")
    return p


def build_prompt(level, grammar=(), topic="", avoid=(), feedback=""):
    lo, hi = LENGTH[level]
    vocab = "、".join(w["word"] for w in hsk.words_upto(level))
    gram = "\n".join(f"  - {g.name}: {g.pattern}" for g in grammar) or "  (any at this level)"
    return f"""
You write graded reading for an adult learning MALAYSIAN Mandarin (everyday,
natural, the way Chinese Malaysians speak and write messages).

LEVEL: HSK {level}. Use ONLY words from this list (plus names of places and
particles); at most {MAX_NEW} words from outside it, each declared in
"new_words" with pinyin and English:
{vocab}

Write ONE short passage, {lo}-{hi} Chinese characters, 3-6 sentences that
connect: a little scene, a message, a short story - with a point, not a list
of facts. Topic: {topic or "anything from everyday life in Malaysia"}.
Work in a few of these structures the learner has studied, naturally:
{gram}

Rules: simplified characters; Chinese numerals, never digits; no Latin
letters; no Beijing 儿 (哪里, 一点, 这里); no names of real people - use roles or
common given names. Malaysian words are welcome (巴刹, 巴士, 冷气).
{("Don't repeat these earlier titles: " + "、".join(avoid)) if avoid else ""}

Then ONE comprehension question in English about the passage, with three
English options, exactly one right - answerable only by understanding the
passage, not by guessing.
{("YOUR LAST DRAFT WAS REJECTED. Fix:\n" + feedback) if feedback else ""}
Return ONLY JSON:
{{"title": "<short Chinese title>", "text": "<the passage>", "english": "<translation>",
 "new_words": [{{"hanzi": "…", "pinyin": "…", "english": "…"}}],
 "question": {{"question": "…", "options": ["…", "…", "…"], "answer": 0}}}}
""".strip()


def _review(payload, level):
    from config import REVIEW_MODEL, GRADING_MODEL
    from grammar_drills import _chat_json
    prompt = f"""
You are a strict native-speaker reviewer of Malaysian Mandarin reading material
for an HSK {level} learner.

TITLE: {payload['title']}
TEXT: {payload['text']}
ENGLISH: {payload['english']}
QUESTION: {payload['question']['question']} | options: {payload['question']['options']}
| key: {payload['question']['answer']}

Check: the Chinese is natural and correct; the sentences connect into a
passage; the English matches; exactly one option is right, the key points to
it, and it can't be answered without understanding the text.
Return ONLY JSON: {{"acceptable": true/false, "problems": ["…"]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = _chat_json(model, prompt, 0)
            probs = [str(x) for x in v.get("problems") or [] if str(x).strip()]
            return bool(v.get("acceptable")) and not probs, probs, True
        except Exception as e:
            logging.warning(f"[READ HSK] review {model} failed: {e}")
    return True, [], False


def _parts_gloss(w, declared=None):
    """A meaning for a word made of HSK words (买菜 → buy + vegetables, 一杯 →
    one + cup), from the longest known part at each step."""
    from dictionary_engine import cedict_gloss
    declared = declared or {}
    parts, i = [], 0
    while i < len(w):
        for j in range(len(w), i, -1):
            piece = w[i:j]
            english = ((declared.get(piece) or {}).get("english")
                       or (hsk.word(piece) or {}).get("english") or "")
            if not english and j == i + 1:
                english = (cedict_gloss(piece)[0] or "?").split(" / ")[0]
            if english:
                parts.append(english.split(" / ")[0])
                i = j
                break
    return " + ".join(parts)


def annotate(payload, level):
    """The words as shown: each with pinyin, meaning and HSK level, worked out
    once when the passage is stored."""
    from dictionary_engine import cedict_gloss
    from hsk_grammar import sentence_pinyin
    declared = {w["hanzi"]: w for w in payload.get("new_words") or []}
    out = []
    for a in analyse(payload["text"], level, declared):
        w = a["w"]
        if a["status"] == "punct":
            out.append({"w": w, "punct": True})
            continue
        info = hsk.word(w)
        english = (declared.get(w) or {}).get("english") or (info or {}).get("english") \
            or (cedict_gloss(w)[0] or "").split(" / ")[0] or _parts_gloss(w, declared)
        out.append({"w": w, "py": (declared.get(w) or {}).get("pinyin") or sentence_pinyin(w),
                    "en": english, "hsk": (info or {}).get("level"),
                    "new": a["status"] != "in"})
    return out


def generate(level, grammar=(), topic="", avoid=(), attempts=3):
    """Write, check and review a passage. Returns the payload (with "words"
    annotated) or None."""
    from config import GENERATION_MODEL
    from grammar_drills import _chat_json
    feedback = ""
    for attempt in range(1, attempts + 1):
        try:
            draft = _chat_json(GENERATION_MODEL,
                               build_prompt(level, grammar, topic, avoid, feedback), 0.8)
        except Exception as e:
            logging.warning(f"[READ HSK] attempt {attempt}: {e}")
            feedback = "- the reply was not valid JSON"
            continue
        problems = check(draft, level)
        if not problems:
            ok, review_problems, reviewed = _review(draft, level)
            if ok:
                draft["level"], draft["reviewed"] = level, reviewed
                draft["grammar"] = [g.id for g in grammar]
                draft["words"] = annotate(draft, level)
                return draft
            problems = review_problems
        feedback = "\n".join(f"- {x}" for x in problems[:10])
        logging.warning(f"[READ HSK] HSK {level} attempt {attempt}: {feedback}")
    return None


