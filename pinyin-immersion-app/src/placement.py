# src/placement.py
"""
Level test: which HSK level to study at, by ear and by eye.

Three short tests, each run level by level from HSK 1:

  listen   hear a word, pick its meaning   (what you know as spoken Mandarin)
  read     see a word, pick its meaning    (what you know in characters)
  grammar  put an official HSK example sentence back in order, from its
           words as tiles with pinyin, its English given (what you can build)

Each level asks up to ITEMS words drawn from the words NEW at that level
(HSK 3's 500, not HSK 1-3's 1,000), four meanings to choose from plus "I
don't know". A level is passed at PASS of ITEMS right; the level stops early
as soon as the result is settled either way, and the test stops at the
first level not passed. So a beginner answers about ten questions and
someone at HSK 4 about forty.

The result is the highest level passed (0-4); the level to study is the
one after it (at most 4). The skills are kept apart because they drive
different parts of the app: grammar drills go up to the grammar level and
build from the words of the listening level; reading and games go by
reading. Grammar asks fewer questions (GRAMMAR_ITEMS, pass at
GRAMMAR_PASS): each takes longer.

Pure: the page (views/11_Level_test.py) keeps the state and plays audio.
"""

import random
import re

import hsk

ITEMS = 10
PASS = 8
GRAMMAR_ITEMS = 6
GRAMMAR_PASS = 5
OPTIONS = 4
SKILLS = {
    "listen": ("🎧", "Listening", "Hear a word, pick what it means."),
    "read": ("👁️", "Reading", "See a word in characters, pick what it means."),
    "grammar": ("🧩", "Grammar", "Put the words in order to say the English."),
}


def size(skill):
    """(questions per level, right answers to pass it)"""
    return (GRAMMAR_ITEMS, GRAMMAR_PASS) if skill == "grammar" else (ITEMS, PASS)


_STOP = {"to", "the", "an", "of", "and", "or", "for", "in", "on", "at", "sb", "sth", "etc",
         "one", "be", "is", "it", "with", "as", "by", "used", "word", "measure", "malaysia",
         "prc", "fig", "me", "my", "up", "out", "off", "into", "from", "that", "this"}


_CJK = re.compile(r"[\u4e00-\u9fff]")


def show(english):
    """A meaning as shown: plain English, at most two senses. No Chinese -
    the house list notes Malaysian words and examples in it ('to drive a
    car (Malaysia: 驾车)', 'from: 离我家不远 = ...') - and no dictionary
    cross-references or essay-length senses."""
    text = re.sub(r"\([^)]*[\u4e00-\u9fff][^)]*\)", "", english)
    senses = []
    for sense in re.split(r"[/;]", text):
        sense = sense.strip()
        if ":" in sense and _CJK.search(sense.split(":", 1)[1]):
            sense = sense.split(":", 1)[0].strip()
        m = _CJK.search(sense)
        if m:                          # '(marks the object) 把书放好 = ...': keep what's before
            sense = sense[:m.start()].strip(" =,")
        if (not sense or _CJK.search(sense) or len(sense) > 45
                or re.match(r"see\b|variant\b|\(malaysian", sense, re.I)):
            continue
        senses.append(sense)
    return " / ".join(senses[:2])


def _tokens(item):
    """Content words of the meaning - all of it, not just the senses shown,
    so a clash in a sense left off the button still counts."""
    text = re.sub(r"[\u4e00-\u9fff].*?(?=[/;]|$)", "", item["english"])
    return {t for t in re.findall(r"[a-z]+", text.lower())
            if len(t) > 1 and t not in _STOP}


def _clash(a, b):
    """Two meanings too close to tell apart fairly (有些 'some / somewhat'
    and 一些 'some / a few'): any content word in common."""
    return bool(_tokens(a) & _tokens(b))


def _pool(level):
    return [w for w in hsk.words(level) if _tokens(w)]


def make_item(target, pool, rng):
    """One question: the target and OPTIONS-1 other meanings, none that could
    also be right. Only one shares the target's part of speech: words of
    the same kind are where near-synonyms hide (好看 'good-looking' and
    漂亮 'pretty') that no word-overlap check can catch."""
    others = [w for w in pool if w["word"] != target["word"] and not _clash(w, target)]
    pos = set(target["pos"].split("、"))
    same = [w for w in others if pos & set(w["pos"].split("、"))]
    rest = [w for w in others if w not in same]
    rng.shuffle(same)
    rng.shuffle(rest)
    picked = []
    for w in same[:1] + rest + same[1:]:
        if len(picked) == OPTIONS - 1:
            break
        if all(not _clash(w, p) for p in picked):
            picked.append(w)
    options = [show(target["english"])] + [show(w["english"]) for w in picked]
    rng.shuffle(options)
    return {"word": target["word"], "pinyin": target["pinyin"], "level": target["level"],
            "english": show(target["english"]), "options": options,
            "answer": show(target["english"])}


def new_test(skill, seed=None):
    """A fresh test state for one skill."""
    rng = random.Random(seed)
    return {"skill": skill, "seed": rng.randrange(1 << 30), "level": 1, "items": [],
            "answers": [], "passed": 0, "done": False, "log": []}


def grammar_pool(level):
    """Official HSK example sentences for the level's grammar points (the
    ones drilled, not the vocabulary ones) that make a fair puzzle: 4-7
    tiles (8 at HSK 4, whose examples run long), English given, no
    Beijing 儿, one sentence."""
    import hsk_grammar as hg
    import grammar_build as gb
    from dictionary_engine import has_erhua
    import grammar_curriculum as gc
    most = 8 if level == 4 else 7
    out, seen = [], set()
    for p in hsk.grammar_points(level):
        if not hg.MAP.get(p["id"]):
            continue
        markers = [m for sid in hg.MAP[p["id"]] for m in gc.get(sid).markers]
        for ex in p["examples"]:
            zh = re.sub(r"（[^）]*）", "", ex["chinese"]).strip()
            if (not ex["english"] or has_erhua(zh) or zh in seen
                    # a list (英语、汉语、法语) could go in any order: left out
                    or not re.search(r"[。？！]$", zh) or re.search(r"[，；、“”]", zh)):
                continue
            words = gb.tiles_of(zh, markers)
            # a fronted topic (火车票你买到了没有) has a second right order
            # (你买到火车票了没有): only sentences whose subject is up front
            late = [i for i, w in enumerate(words or []) if w in gb.SUBJECTS]
            if late and late[0] > 1:
                continue
            if words and 4 <= len(words) <= most:
                seen.add(zh)
                out.append({"hanzi": zh, "english": ex["english"], "answer": words,
                            "point": p["id"],
                            "pinyin": ex.get("pinyin") if zh == ex["chinese"] else ""})
    return out


def make_grammar_item(ex, rng):
    import grammar_build as gb
    import hsk_grammar as hg
    from pinyin_hsk import word_pinyin
    return {**ex, "word": ex["hanzi"], "level": int(ex["point"][1]),
            "tiles": gb._shuffled(ex["answer"], rng.random()),
            "pinyin": dict(zip(ex["answer"], word_pinyin(ex["answer"]))),
            "sentence_pinyin": ex.get("pinyin") or hg.sentence_pinyin(ex["hanzi"])}


def _level_items(state):
    """The questions for the current level, fixed by the test's seed - and
    for grammar, from as many different grammar points as possible."""
    rng = random.Random(f"{state['seed']}:{state['level']}")
    n, _need = size(state["skill"])
    if state["skill"] == "grammar":
        pool = grammar_pool(state["level"])
        rng.shuffle(pool)
        by_point, picked = set(), []
        for ex in pool + pool:              # one per point first, then any
            if len(picked) == n:
                break
            if ex in picked or (ex["point"] in by_point and len(by_point) < len(
                    {e["point"] for e in pool})):
                continue
            by_point.add(ex["point"])
            picked.append(ex)
        return [make_grammar_item(ex, rng) for ex in picked]
    pool = _pool(state["level"])
    targets = rng.sample(pool, min(n, len(pool)))
    return [make_item(t, pool, rng) for t in targets]


def current(state):
    """The question to ask now, or None when the test is over."""
    if state["done"]:
        return None
    if not state["items"]:
        state["items"] = _level_items(state)
    return state["items"][len(state["answers"])]


def settled(right, asked, items=ITEMS, need=PASS):
    """'pass', 'fail' or None (keep asking) - decided as soon as it can't change."""
    wrong = asked - right
    if right >= need:
        return "pass"
    if wrong > items - need:
        return "fail"
    return None


def answer(state, choice):
    """Record an answer - an option, the tiles in the order tapped (grammar),
    or None for "I don't know" - and move on."""
    item = current(state)
    if item is None:
        return state
    if state["skill"] == "grammar":
        import grammar_build as gb
        ok = choice is not None and gb.check(list(choice), item) == "correct"
    else:
        ok = choice == item["answer"]
    state["answers"].append(ok)
    state["log"].append({"level": state["level"], "word": item["word"], "ok": ok,
                         "dont_know": choice is None})
    right, asked = sum(state["answers"]), len(state["answers"])
    n, need = size(state["skill"])
    outcome = settled(right, asked, len(state["items"]), min(need, len(state["items"])))
    if outcome == "pass":
        state["passed"] = state["level"]
        if state["level"] == hsk.LEVELS[-1]:
            state["done"] = True
        else:
            state["level"] += 1
            state["items"], state["answers"] = [], []
    elif outcome == "fail":
        state["done"] = True
    return state


def study_level(passed):
    """Highest level passed -> the level to study."""
    return min(passed + 1, hsk.LEVELS[-1])


def score_by_level(state):
    out = {}
    for row in state["log"]:
        r, n = out.get(row["level"], (0, 0))
        out[row["level"]] = (r + row["ok"], n + 1)
    return out
