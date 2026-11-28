# src/reading_hsk.py
"""
Graded reading for the HSK track: short passages at your reading level.

Each passage is a few connected sentences - a scene, a message, a short
story - in everyday Mandarin (Malaysia as the setting), built from HSK words up to your
reading level, with at most max_new(level) words above it (declared, with pinyin
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

MAX_NEW = 3                       # words above the level, declared (HSK 3-4)
# HSK 1 has 300 words and HSK 2 another 200: a natural passage needs a few
# more from outside them (因为, 开心, 用 sank every HSK 1 draft of the live runs)
MAX_NEW_AT = {1: 5, 2: 4}


def max_new(level):
    return MAX_NEW_AT.get(level, MAX_NEW)

# share of words at or below the level: a short HSK 1 passage of ~35 words
# with its 5 allowed new words is at 86%, so the bar is lower there
MIN_COVERAGE = {1: 0.85, 2: 0.88, 3: 0.92, 4: 0.93}
# characters; HSK 1's exam passages are short too (revised drafts of 36-43
# characters sank every retry of a live run at the old minimum of 45)
LENGTH = {1: (35, 100), 2: (70, 140), 3: (100, 200), 4: (140, 260)}
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


def _pieces(token):
    """A token jieba glued together that isn't a word (我用, 很快) cut into
    HSK words and single characters, longest first - so the word above the
    level (用) is the one reported, not the pair. Real words stay whole."""
    from dictionary_engine import cedict_gloss
    if len(token) < 2 or hsk.word(token) or (cedict_gloss(token)[0] or ""):
        return [token]
    every = {w["word"] for w in hsk.words_upto(4, include_erhua=True)}
    out, i = [], 0
    while i < len(token):
        j = next(j for j in range(len(token), i, -1) if j == i + 1 or token[i:j] in every)
        out.append(token[i:j])
        i = j
    return out


def analyse(text, level, declared=()):
    """[{"w", "status"}] for each word: "in" (at or below the level),
    "new" (declared above-level word), "out" (above the level, undeclared),
    "punct"."""
    known, declared = _known(level), set(declared)
    chars = frozenset(hsk.recognise_chars(level))
    out = []
    def fine(w):
        return w in known or all(c in _FREE for c in w) or (
            len(w) > 1 and _splits(w, known, chars if len(w) <= 3 else frozenset()))

    for w in (p for tok in words_of(text) for p in (
            [tok] if not _cjk(tok) or fine(tok) or tok in declared
            or any(d in tok for d in declared) else _pieces(tok))):
        if not _cjk(w):
            out.append({"w": w, "status": "punct"})
        elif fine(w):
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
    meaning), when that keeps it within max_new: the live runs failed again
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
    if not out or len(new) + len(out) > max_new(level):
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
    if n < lo:
        p.append(f"text is {n} characters; it must be {lo}-{hi} - add a sentence or two "
                 f"(about {lo - n + 10} more characters), keeping everything else")
    elif n > hi:
        p.append(f"text is {n} characters; it must be {lo}-{hi} - cut a sentence")
    if re.search(r"[A-Za-z0-9]", text):
        p.append("digits or Latin letters in the text - write numbers in Chinese")
    if has_erhua(text):
        p.append("uses Beijing 儿 - write it the Malaysian way (哪里, 一点, 这里)")
    if not str(payload.get("title") or "").strip() or not str(payload.get("english") or "").strip():
        p.append("needs a Chinese title and an English translation")
    new = [w for w in payload.get("new_words") or [] if isinstance(w, dict) and w.get("hanzi")]
    if len(new) > max_new(level):
        p.append(f"declares {len(new)} new words; at most {max_new(level)}")
    for w in new:
        if not w.get("english"):
            p.append(f"new word {w['hanzi']} needs its English")
    a = analyse(text, level, [w["hanzi"] for w in new])
    out = sorted({x["w"] for x in a if x["status"] == "out"})
    if out:
        p.append("uses words above HSK " + str(level) + " that weren't declared: "
                 + "、".join(out) + " - replace them with easier words, or declare up to "
                 f"{max_new(level)} in new_words")
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
    elif not _quoted(q.get("answer_quote"), text):
        p.append("answer_quote must copy, character for character, the sentence of the text "
                 "that answers the question - and the question must be answered by the text")
    else:
        # the question is in Chinese, like the exam's: it must be at the level too
        qa = analyse(q["question"] + "。" + "。".join(map(str, q["options"])), level,
                     [w["hanzi"] for w in new])
        hard = sorted({x["w"] for x in qa if x["status"] == "out"})
        if hard:
            p.append("the question uses words above HSK " + str(level) + ": " + "、".join(hard))
    return p


def _bare(text):
    return re.sub(r"[\s" + re.escape(_PUNCT) + r"\"'.,!?:;]", "", str(text or ""))


def _quoted(quote, text):
    """Is the quote (punctuation aside) a real stretch of the text, of a few
    characters at least?"""
    q = _bare(quote)
    return len(q) >= 3 and q in _bare(text)


def blind_check(payload):
    """A second reading of the question with the key hidden: a model answers
    from the text alone and quotes the sentence that proves it. Problems if
    it can't (the text doesn't say), picks another option, or quotes
    something that isn't in the text - the live run's passage gave tea to
    the brother and asked what the child drank, keyed 喝茶.

    Returns (problems, ran): ran is False if no model could be asked."""
    from config import REVIEW_MODEL, GRADING_MODEL
    from grammar_drills import _chat_json
    q = payload["question"]
    opts = "\n".join(f"{n}. {o}" for n, o in enumerate(q["options"]))
    prompt = f"""
Read this Chinese passage and answer the question using ONLY what the text
says - not what is likely, not what fits the scene. Watch who does what.

TEXT: {payload['text']}

QUESTION: {q['question']}
{opts}

If the text doesn't say, or more than one option fits, answer -1.
Return ONLY JSON: {{"answer": 0, 1, 2 or -1,
 "quote": "<the sentence of the text that gives the answer, copied exactly; empty if -1>",
 "why": "<one short sentence in English>"}}
""".strip()
    for model in (GRADING_MODEL, REVIEW_MODEL):
        try:
            v = _chat_json(model, prompt, 0)
            got = int(v.get("answer"))
        except Exception as e:
            logging.warning(f"[READ HSK] blind check {model} failed: {e}")
            continue
        why = str(v.get("why") or "").strip()
        key = q["options"][q["answer"]]
        if got == -1:
            return [f"answering from the text alone, the question can't be answered ({why}) - "
                    f"the key says {key}. Ask about something the text states, about the "
                    "right person, with exactly one option right"], True
        if got != q["answer"]:
            return [f"answering from the text alone, a reader picks "
                    f"{q['options'][got] if 0 <= got < 3 else got} ({why}), but the key says "
                    f"{key} - make exactly one option right by the text"], True
        if not _quoted(v.get("quote"), payload["text"]):
            return [f"the answer {key} isn't stated in the text - ask about something it says"], True
        return [], True
    return [], False


def build_prompt(level, grammar=(), topic="", avoid=(), feedback=""):
    lo, hi = LENGTH[level]
    vocab = "、".join(w["word"] for w in hsk.words_upto(level))
    gram = "\n".join(f"  - {g.name}: {g.pattern}" for g in grammar) or "  (any at this level)"
    return f"""
You write graded reading for an adult preparing for the HSK exams who lives
in Malaysia: everyday, natural Mandarin in standard HSK vocabulary.

LEVEL: HSK {level}. Use ONLY words from this list (plus names of places and
particles); at most {max_new(level)} words from outside it, each declared in
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
guessing. Ask about something the text states, about the right person (if
the brother drinks tea, don't ask what the child drinks). In "answer_quote"
copy, character for character, the sentence of the text that gives the
answer. Give the English of the question and of each option too.
{("YOUR LAST DRAFT WAS REJECTED. Fix:\n" + feedback) if feedback else ""}
Return ONLY JSON:
{{"title": "<short Chinese title>", "text": "<the passage>", "english": "<translation>",
 "new_words": [{{"hanzi": "…", "pinyin": "…", "english": "…"}}],
 "question": {{"question": "<in Chinese>", "options": ["…", "…", "…"], "answer": 0,
              "question_english": "…", "options_english": ["…", "…", "…"],
              "answer_quote": "<the sentence of the text that answers it>"}}}}
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
passage; the English is natural English with the right sense (小朋友 is "the
child", not "the little friend"); exactly one option is right BY THE TEXT -
check who does what (if the brother drinks tea, "what does the child drink?"
has no answer) - the key points to it, and it can't be answered without
understanding the text.
At HSK {level} the vocabulary is small on purpose: short, plain sentences, a
word used twice, and simple statements (很好, 很好看) are expected - don't
reject for those. Reject for Chinese a native speaker wouldn't say, a scene
that makes no sense (a film watched in a restaurant), a wrong translation or a
wrong key.
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
            problems, ran = blind_check(draft)
            if not ran:
                problems = ["the question couldn't be checked - no model answered"]
        if not problems:
            ok, review_problems, reviewed = _review(draft, level)
            if ok:
                draft["level"], draft["reviewed"], draft["checked"] = level, reviewed, True
                draft["grammar"] = [g.id for g in grammar]
                draft["words"] = annotate(draft, level)
                return draft
            problems = review_problems
        feedback = _revise(draft, problems)
        logging.warning(f"[READ HSK] HSK {level} attempt {attempt}: " + "; ".join(problems[:10]))
    return None


