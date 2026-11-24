# src/reading_hsk.py
"""
Graded reading for the HSK track: short passages at your reading level.

Each passage is a few connected sentences - a scene, a message, a short
story - in everyday Mandarin (Malaysia as the setting), built from HSK words up to your
reading level, with at most MAX_NEW words above it (declared, with pinyin
and English). It reuses grammar you've drilled, and ends with one
comprehension question in Chinese (with its English).

Everything a passage needs on screen is worked out when it is written and
stored with it - the words (jieba, kept whole where they're HSK words),
each word's pinyin, meaning and HSK level - so reading one is instant.
Passages are written ahead (ahead.reading, tools/fill_bank.py), never
while you wait unless the stock has run out.

    analyse(text, level)         word by word: in level / new / other
    check(payload, level)        what's wrong with a draft, [] if nothing
    generate(level, ...)         write, check, review -> payload or None
"""

import json
import logging
import re

import hsk

MAX_NEW = 3                       # words above the level, declared
# share of words at or below the level: a short HSK 1 passage of ~30 words
# with its 3 allowed new words is at 90%, so the bar is lower there
MIN_COVERAGE = {1: 0.88, 2: 0.9, 3: 0.92, 4: 0.93}
LENGTH = {1: (45, 100), 2: (70, 140), 3: (100, 200), 4: (140, 260)}   # characters
SENTENCES = {1: "6-8 short", 2: "6-8", 3: "5-8", 4: "5-8"}
# HSK 1-2 has a few hundred words: topics they can carry
EASY_TOPICS = ("my family", "what I eat in a day", "the weather today", "going to the shop",
               "my friend", "a day at school", "what time I get up", "buying fruit",
               "my room", "a phone call home", "a weekend at home", "my new phone",
               "going to the doctor", "a cup of tea with a friend", "taking the bus")
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


def auto_declare(payload, level):
    """Declare the draft's few above-level words itself (with pinyin and a
    meaning), when that keeps it within MAX_NEW: the live runs failed again
    and again on one or two words (等, 送) the writer hadn't listed."""
    if not isinstance(payload, dict):
        return payload
    from dictionary_engine import cedict_gloss
    from pinyin_hsk import sentence_pinyin
    new = [w for w in payload.get("new_words") or [] if isinstance(w, dict) and w.get("hanzi")]
    q = payload.get("question") if isinstance(payload.get("question"), dict) else {}
    text = str(payload.get("text") or "") + "。" + str(q.get("question") or "") + "。" + \
        "。".join(map(str, q.get("options") or []))
    out = list(dict.fromkeys(x["w"] for x in analyse(text, level, [w["hanzi"] for w in new])
                             if x["status"] == "out"))
    if not out or len(new) + len(out) > MAX_NEW:
        return payload
    for w in out:
        info = hsk.word(w)
        english = (info or {}).get("english") or (cedict_gloss(w)[0] or "").split(" / ")[0] \
            or _parts_gloss(w, {})
        new.append({"hanzi": w, "pinyin": sentence_pinyin(w), "english": english, "auto": True})
    payload["new_words"] = new
    return payload


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
    elif coverage(a) < MIN_COVERAGE[level]:
        p.append("too many new words for this level")
    q = payload.get("question")
    if not (isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list)
            and len(q["options"]) == 3 and isinstance(q.get("answer"), int)
            and 0 <= q["answer"] < 3 and len({str(o) for o in q["options"]}) == 3):
        p.append("question needs: question, three different options, answer (0-2)")
    elif not (q.get("question_english") and isinstance(q.get("options_english"), list)
              and len(q["options_english"]) == 3):
        p.append("question needs question_english and three options_english")
    else:
        # the question is in Chinese, like the exam's: it must be at the level too
        qa = analyse(q["question"] + "。" + "。".join(map(str, q["options"])), level,
                     [w["hanzi"] for w in new])
        hard = sorted({x["w"] for x in qa if x["status"] == "out"})
        if hard:
            p.append("the question uses words above HSK " + str(level) + ": " + "、".join(hard))
    return p


def build_prompt(level, grammar=(), topic="", avoid=(), feedback=""):
    lo, hi = LENGTH[level]
    vocab = "、".join(w["word"] for w in hsk.words_upto(level))
    gram = "\n".join(f"  - {g.name}: {g.pattern}" for g in grammar) or "  (any at this level)"
    return f"""
You write graded reading for an adult preparing for the HSK exams who lives
in Malaysia: everyday, natural Mandarin in standard HSK vocabulary.

LEVEL: HSK {level}. Use ONLY words from this list (plus names of places and
particles); at most {MAX_NEW} words from outside it, each declared in
"new_words" with pinyin and English:
{vocab}

Write ONE short passage: {SENTENCES[level]} sentences, {lo}-{hi} Chinese characters
in all (count them - fewer than {lo} is rejected), that connect: a little scene, a message, a short story - with a point, not a list
of facts. Topic: {topic or "anything from everyday life in Malaysia"}.
Work in a few of these structures the learner has studied, naturally:
{gram}

Rules: simplified characters; Chinese numerals, never digits; no Latin
letters; no Beijing 儿 (哪里, 一点, 这里); no names of real people - use roles or
common given names. Standard HSK vocabulary (出租车 not 德士); Malaysia is a
fine setting.
{("Don't repeat these earlier titles: " + "、".join(avoid)) if avoid else ""}

Then ONE comprehension question about the passage, in Chinese like the HSK
exam's, using only words from the list, with three short Chinese options,
exactly one right - answerable only by understanding the passage, not by
guessing. Give the English of the question and of each option too.
{("YOUR LAST DRAFT WAS REJECTED. Fix:\n" + feedback) if feedback else ""}
Return ONLY JSON:
{{"title": "<short Chinese title>", "text": "<the passage>", "english": "<translation>",
 "new_words": [{{"hanzi": "…", "pinyin": "…", "english": "…"}}],
 "question": {{"question": "<in Chinese>", "options": ["…", "…", "…"], "answer": 0,
              "question_english": "…", "options_english": ["…", "…", "…"]}}}}
""".strip()


def _review(payload, level):
    from config import REVIEW_MODEL, GRADING_MODEL
    from grammar_drills import _chat_json
    prompt = f"""
You are a strict native-speaker reviewer of Mandarin reading material for an
HSK {level} learner.

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
    from pinyin_hsk import word_pinyin
    declared = {w["hanzi"]: w for w in payload.get("new_words") or []}
    out = []
    parts = analyse(payload["text"], level, declared)
    # read in the sentence, so 地 in 高兴地说 is de and 得 in 今天得去 is děi
    readings = word_pinyin([a["w"] for a in parts])
    for a, reading in zip(parts, readings):
        w = a["w"]
        if a["status"] == "punct":
            out.append({"w": w, "punct": True})
            continue
        info = hsk.word(w)
        english = (declared.get(w) or {}).get("english") or (info or {}).get("english") \
            or (cedict_gloss(w)[0] or "").split(" / ")[0] or _parts_gloss(w, declared)
        out.append({"w": w, "py": (declared.get(w) or {}).get("pinyin") or reading,
                    "en": english, "hsk": (info or {}).get("level"),
                    "new": a["status"] != "in"})
    return out


def _revise(draft, problems):
    """Feedback that keeps the draft: the model revises what it wrote instead
    of starting again (a fresh start fixed one problem and made another -
    the first live run's HSK 1 passages got shorter each time)."""
    text = json.dumps({k: draft.get(k) for k in ("title", "text", "english", "new_words",
                                                 "question")}, ensure_ascii=False) \
        if isinstance(draft, dict) else ""
    return ("\n".join(f"- {x}" for x in problems[:10])
            + (f"\nYOUR DRAFT (revise it - keep what works, fix only the problems above):\n{text}"
               if text else ""))


def topic_for(level, rng=None):
    import random
    return (rng or random).choice(EASY_TOPICS if level <= 2 else TOPICS)


def generate(level, grammar=(), topic="", avoid=(), attempts=None):
    """Write, check and review a passage. Returns the payload (with "words"
    annotated) or None. HSK 1-2 get more drafts: with a few hundred words,
    natural writing that the reviewer passes takes more revising."""
    attempts = attempts or (5 if level <= 2 else 3)
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
        problems = check(auto_declare(draft, level), level)
        if not problems:
            ok, review_problems, reviewed = _review(draft, level)
            if ok:
                draft["level"], draft["reviewed"] = level, reviewed
                draft["grammar"] = [g.id for g in grammar]
                draft["words"] = annotate(draft, level)
                return draft
            problems = review_problems
        feedback = _revise(draft, problems)
        logging.warning(f"[READ HSK] HSK {level} attempt {attempt}: " + "; ".join(problems[:10]))
    return None


