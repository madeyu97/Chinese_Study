# src/word_diagnosis.py
"""
Why does a word keep slipping? Diagnose first, then remedy - mnemonics only
when nothing more specific explains it.

A word is TROUBLED when it has lapsed twice after being learned, or has been
missed three times in its last ten scored checks (learning-step and retry
misses don't count: those are part of learning, not evidence of trouble).

The cause is read from the recorded attempts, each piece of evidence
weighted:
  tone           wrong tones when typing; picking the tone-neighbour when
                 listening (买 heard as 卖)
  sound          misses when listening that don't happen when reading
  character      misses when reading that don't happen when listening;
                 picking look-alikes (冷/领); same-sound wrong characters
  confusion      repeatedly picking, or saying, one particular other word
  production_gap recognised reliably but not produced
  usage          produced, but with the wrong partner word, grammar or sense
  memory         missed everywhere with no pattern - the only case that gets
                 a mnemonic

Each cause has a remedy: listening contrasts, tone choices, a look-alike
comparison with components, a contrast drill against the confused word, a
production ladder, chunk practice - or, for memory, a mnemonic built from the
word's real components.
"""

import logging
import random
import re
import unicodedata

import ai_prompter as ap
import grammar_drills as gd
import word_content as wc
from config import GENERATION_MODEL, REVIEW_MODEL, GRADING_MODEL

SCORED_KINDS = ("review", "unlock", "step2")
CAUSES = ("tone", "sound", "character", "confusion", "production_gap", "usage", "memory")
CAUSE_TITLES = {
    "tone": "The tones",
    "sound": "Hearing it",
    "character": "Reading the characters",
    "confusion": "Mixing it up with another word",
    "production_gap": "Recalling it yourself",
    "usage": "Using it naturally",
    "memory": "Making it stick",
}
PREFERRED_MODE = {   # how later checks lean for a diagnosed word
    ("tone", "recognition"): "audio_to_meaning", ("tone", "production"): "cloze",
    ("sound", "recognition"): "audio_to_meaning", ("sound", "production"): "meaning_to_zh",
    ("character", "recognition"): "zh_to_meaning", ("character", "production"): "cloze",
    ("confusion", "recognition"): "zh_to_meaning", ("confusion", "production"): "cloze",
    ("production_gap", "production"): "cloze", ("usage", "production"): "spoken",
}
MIN_SCORE = 3.0


# ======================================================================
# Trouble detection and diagnosis
# ======================================================================
def _scored(attempts):
    return [a for a in attempts
            if (a.get("detail") or {}).get("kind", "review") in SCORED_KINDS
            and not str(a.get("mode", "")).startswith(("remedy", "game"))
            and a.get("result") != "ungraded"]


def is_troubled(track, attempts):
    """attempts: newest first, for one word and skill."""
    if (track or {}).get("lapses", 0) >= 2:
        return True
    recent = _scored(attempts)[:10]
    return sum(a["result"] == "wrong" for a in recent) >= 3


def diagnose(attempts):
    """attempts: newest first, for one word (both skills). Returns
    {cause, evidence: [str], confused_with: str|None, scores}."""
    atts = [a for a in attempts if not str(a.get("mode", "")).startswith(("remedy", "game"))
            and a.get("result") != "ungraded"][:20]
    d = lambda a: a.get("detail") or {}
    miss = [a for a in atts if a["result"] in ("wrong", "close")]
    by_mode = lambda m, r: sum(1 for a in atts if a["mode"] == m and a["result"] == r)
    audio_miss, audio_ok = by_mode("audio_to_meaning", "wrong"), by_mode("audio_to_meaning", "correct")
    read_miss, read_ok = by_mode("zh_to_meaning", "wrong"), by_mode("zh_to_meaning", "correct")
    chose = [d(a).get("chose_kind") for a in atts if a["result"] == "wrong" and d(a).get("chose_kind")]
    tone_typed = sum(1 for a in atts if d(a).get("tone_error")) + \
        sum(1 for a in atts if a["mode"] == "tone_pick" and a["result"] == "wrong")
    homophone_typed = sum(1 for a in atts if d(a).get("homophone") and not d(a).get("spoken"))
    wrong_words = [d(a).get("chose") for a in atts
                   if a["result"] == "wrong" and d(a).get("chose_kind") in ("meaning", "other", "look")]
    repeat = max(set(wrong_words), key=wrong_words.count) if wrong_words else None
    repeat_n = wrong_words.count(repeat) if repeat else 0
    spoken_err = [d(a).get("error") for a in atts if a["mode"] == "spoken" and a["result"] != "correct"]
    rec = [a for a in atts if a["skill"] == "recognition"]
    prod = [a for a in atts if a["skill"] == "production"]
    rec_acc = sum(a["result"] == "correct" for a in rec) / len(rec) if rec else 0
    prod_miss = sum(1 for a in prod if a["result"] == "wrong")

    scores = dict.fromkeys(CAUSES, 0.0)
    evidence = {c: [] for c in CAUSES}
    tone_heard = sum(1 for a in atts if a["mode"] == "audio_to_meaning" and a["result"] == "wrong"
                     and d(a).get("chose_kind") == "tone") + \
        sum(1 for a in atts if a["mode"] == "tone_hear" and a["result"] == "wrong")
    scores["tone"] = 2 * tone_typed + 2 * tone_heard
    if tone_typed:
        evidence["tone"].append(f"Right syllables but wrong tones {tone_typed}× when typing")
    if tone_heard:
        evidence["tone"].append(f"Heard it as a word with different tones {tone_heard}×")
    if audio_miss > read_miss:
        scores["sound"] = 1.5 * (audio_miss - read_miss)
        evidence["sound"].append(f"Missed {audio_miss} of {audio_miss + audio_ok} when listening, "
                                 f"{read_miss} of {read_miss + read_ok} when reading")
    if read_miss > audio_miss:
        scores["character"] += 1.5 * (read_miss - audio_miss)
        evidence["character"].append(f"Missed {read_miss} of {read_miss + read_ok} when reading, "
                                     f"{audio_miss} of {audio_miss + audio_ok} when listening")
    look = chose.count("look")
    if look:
        scores["character"] += 2 * look
        evidence["character"].append(f"Picked a look-alike {look}×")
    if homophone_typed:
        scores["character"] += 2 * homophone_typed
        evidence["character"].append(f"Wrote a same-sound character {homophone_typed}×")
    meaning_pick = chose.count("meaning")
    wrong_word = spoken_err.count("wrong_word")
    scores["confusion"] = 2 * meaning_pick + (3 * repeat_n if repeat_n >= 2 else 0) + 2 * wrong_word
    if repeat_n >= 2:
        evidence["confusion"].append(f"Chose {repeat} instead {repeat_n}×")
    elif meaning_pick:
        evidence["confusion"].append(f"Picked a similar-meaning word {meaning_pick}×")
    if wrong_word:
        evidence["confusion"].append(f"Said a different word instead {wrong_word}×")
    if prod_miss >= 2 and rec_acc >= 0.7:
        scores["production_gap"] = 1.5 * prod_miss
        evidence["production_gap"].append(f"Recognised it {round(rec_acc * 100)}% of the time "
                                          f"but missed producing it {prod_miss}×")
    usage = sum(spoken_err.count(e) for e in ("collocation", "grammar", "meaning"))
    if usage:
        scores["usage"] = 2 * usage
        evidence["usage"].append(f"Used it with the wrong partner, grammar or sense {usage}×")

    best = max(CAUSES[:-1], key=lambda c: scores[c])
    if scores[best] >= MIN_SCORE:
        cause = best
    else:
        cause = "memory"
        evidence["memory"].append(f"Missed {len(miss)} of the last {len(atts)} checks, "
                                  "with no single pattern")
    confused = repeat if cause == "confusion" and repeat_n >= 2 else None
    return {"cause": cause, "evidence": evidence[cause], "confused_with": confused,
            "scores": {k: round(v, 1) for k, v in scores.items()}}


# ======================================================================
# Local remedies - built from the word's own data, no model needed
# ======================================================================
def tone_variants(pinyin, n=3, rng=None):
    """The word's pinyin with one syllable's tone changed: gào su -> gāo su…"""
    rng = rng or random.Random()
    marks = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
    sylls = pinyin.split()
    out, tries = set(), 0
    while len(out) < n and tries < 40:
        tries += 1
        i = rng.randrange(len(sylls))
        base = unicodedata.normalize("NFD", sylls[i])
        base = unicodedata.normalize("NFC", "".join(c for c in base if c not in "\u0304\u0301\u030c\u0300"))
        vowel = next((v for v in "aeoiuü" if v in base), None)
        if vowel is None:
            continue
        if vowel in "iu" and "iu" in base:
            vowel = base[base.index("iu") + 1]
        tone = rng.randrange(4)
        new = base.replace(vowel, marks[vowel][tone], 1)
        cand = " ".join(sylls[:i] + [new] + sylls[i + 1:])
        if cand != pinyin:
            out.add(cand)
    return sorted(out)


def tone_rounds(word, pool, rng=None):
    """Hear the word, pick its tones; then hear-which-one against real
    tone-neighbour words."""
    rng = rng or random.Random()
    rounds = []
    variants = tone_variants(word["pinyin"], 3, rng)
    if variants:
        opts = variants + [word["pinyin"]]
        rng.shuffle(opts)
        rounds.append({"play": word["chinese"], "question": "Which tones did you hear?",
                       "options": opts, "answer": word["pinyin"]})
    rounds += sound_rounds(word, pool, rng, tone_only=True)
    return rounds[:4]


def sound_rounds(word, pool, rng=None, tone_only=False):
    """Hear one of the word and its closest-sounding neighbours; say which."""
    rng = rng or random.Random()
    target = wc._toneless(word["pinyin"])
    neigh = [w for w in pool if w["chinese"] != word["chinese"]
             and wc._toneless(w["pinyin"]) == target
             and (not tone_only or wc._toned(w["pinyin"]) != wc._toned(word["pinyin"]))
             and wc._toned(w["pinyin"]) != wc._toned(word["pinyin"])]
    if not neigh and not tone_only:
        first = target[0] if target else ""
        neigh = [w for w in pool if w["chinese"] != word["chinese"]
                 and wc._toneless(w["pinyin"])[:1] == (first,)]
    rng.shuffle(neigh)
    group, sounds = [word], {wc._toned(word["pinyin"])}
    for w in neigh:           # every option must sound different from every other
        if len(group) >= 3:
            break
        if wc._toned(w["pinyin"]) not in sounds:
            group.append(w)
            sounds.add(wc._toned(w["pinyin"]))
    if len(group) < 2:
        return []
    rounds = []
    for _ in range(3):
        played = rng.choice(group)
        opts = [f"{w['chinese']} {w['pinyin']}" for w in group]
        rng.shuffle(opts)
        rounds.append({"play": played["chinese"], "question": "Which did you hear?",
                       "options": opts, "answer": f"{played['chinese']} {played['pinyin']}"})
    return rounds


def character_card(word, pool, rng=None):
    """Components of the word, its look-alikes, and 'which one means…?'
    rounds that make the learner read the difference."""
    from radical_engine import describe_word
    rng = rng or random.Random()
    try:
        parts = describe_word(word["chinese"]).get("characters", [])
    except Exception:
        parts = []
    lines = []
    for p in parts:
        comps = [f"{c['component']}" + (f" ({c['meaning']})" if c.get("meaning") else "")
                 for c in p.get("components", [])]
        if comps:
            lines.append(f"{p['character']} = " + " + ".join(comps))
    alikes = [w for w in pool if wc._looks_alike(word["chinese"], w["chinese"])
              and wc.short_meaning(w["english"]) != wc.short_meaning(word["english"])]
    rng.shuffle(alikes)
    alikes = alikes[:3]
    rounds = []
    for w in [word] + alikes[:2]:
        opts = [x["chinese"] for x in [word] + alikes]
        rng.shuffle(opts)
        rounds.append({"show": wc.short_meaning(w["english"]),
                       "question": f"Which one means “{wc.short_meaning(w['english'])}”?",
                       "options": opts, "answer": w["chinese"]})
    compare = [f"{w['chinese']} {w['pinyin']} — {wc.short_meaning(w['english'])}" for w in alikes]
    return {"components": lines, "compare": compare, "rounds": rounds if alikes else []}


def production_ladder(word, content):
    """From heavy support to none: gap with the first character given, gap
    with nothing given, then the chunk from its meaning."""
    t = word["chinese"]
    sents = content.get("sentences") or []
    chunks = content.get("chunks") or []
    steps = []
    if sents:
        s = sents[0]
        hinted = s["hanzi"].replace(t, t[0] + "＿" * (len(t) - 1), 1) if len(t) > 1 else \
            wc.cloze(s["hanzi"], t)
        steps.append({"show": hinted, "english": s.get("english", ""),
                      "hint": f"starts with {t[0]} ({word['pinyin'].split()[0]})",
                      "answer": t, "answer_pinyin": word["pinyin"]})
    if len(sents) > 1:
        s = sents[1]
        steps.append({"show": wc.cloze(s["hanzi"], t), "english": s.get("english", ""),
                      "hint": "", "answer": t, "answer_pinyin": word["pinyin"]})
    if chunks:
        c = chunks[0]
        steps.append({"show": c.get("english", ""), "english": "Say the whole chunk.",
                      "hint": "", "answer": c["hanzi"], "answer_pinyin": c.get("pinyin", "")})
    return steps


def usage_rounds(word, content):
    """Chunks again: hear them, then produce each from its meaning."""
    return [{"show": c.get("english", ""), "english": "Say it the natural way.",
             "hint": "", "answer": c["hanzi"], "answer_pinyin": c.get("pinyin", "")}
            for c in (content.get("chunks") or [])[:3]]


def check_chunk(answer, chunk_hanzi, chunk_pinyin, target):
    """Whole chunk = correct; only the target word = close; else wrong."""
    result, detail = wc.check_answer(answer, chunk_hanzi, chunk_pinyin)
    if result == "wrong" and target in (answer or ""):
        return "close", {**detail, "partial": True}
    return result, detail


# ======================================================================
# Model-written remedies: contrast with a confused word, and mnemonics
# ======================================================================
def write_contrast(word, other, known):
    """A short difference plus four gap sentences, each needing either the
    word or the one it gets confused with. Returns dict or None."""
    prompt = f"""
A learner of Malaysian Mandarin keeps confusing {word['chinese']} ({word['pinyin']},
{wc.short_meaning(word['english'])}) with {other['chinese']} ({other['pinyin']},
{wc.short_meaning(other['english'])}).

Write:
- "difference": one or two plain-English sentences on how they differ in use.
- "items": 4 short natural sentences (5-12 characters), two needing
  {word['chinese']} and two needing {other['chinese']}, where only that word fits.
  Give each sentence in full ("hanzi"), which word it needs ("answer"), pinyin
  and English.
Use only these known words plus the two words, pronouns, particles and
numbers: {"、".join(sorted(known)[:400])}
No Beijing 儿, no digits or Latin letters, simplified characters.

Return ONLY JSON: {{"difference": "…", "items": [{{"hanzi": "…", "answer": "…", "pinyin": "…", "english": "…"}}]}}
""".strip()
    allowed = set(known) | gd.FUNCTION_WORDS | {word["chinese"], other["chinese"]}
    for attempt in range(gd.MAX_ATTEMPTS):
        try:
            v = gd._chat_json(GENERATION_MODEL, prompt, 0.6)
        except Exception as e:
            logging.warning(f"[CONTRAST] attempt {attempt + 1}: {e}")
            continue
        items, ok = [], True
        for it in (v.get("items") or [])[:4]:
            hz = ap._force_simplified(str(it.get("hanzi") or ""))
            ans = it.get("answer")
            if ans not in (word["chinese"], other["chinese"]) or ans not in hz \
                    or wc.has_erhua(hz) or re.search(r"[A-Za-z0-9]", hz) \
                    or gd.unknown_words(hz, allowed):
                ok = False
                break
            items.append({"hanzi": hz, "answer": ans, "english": it.get("english", ""),
                          "pinyin": gd._fix_pinyin(hz, it.get("pinyin", "")),
                          "gap": wc.cloze(hz, ans)})
        if ok and len(items) == 4 and {i["answer"] for i in items} == {word["chinese"], other["chinese"]} \
                and str(v.get("difference") or "").strip():
            verdict = _review_contrast(word, other, v["difference"], items)
            if verdict:
                return {"difference": v["difference"], "items": items}
    return None


def _review_contrast(word, other, difference, items):
    lines = "\n".join(f"- {i['hanzi']} (needs {i['answer']})" for i in items)
    prompt = f"""Native Malaysian Mandarin reviewer. Check this contrast between
{word['chinese']} and {other['chinese']}. Difference given: {difference}
{lines}
Is each sentence natural, and does ONLY the stated word fit its gap? Is the
difference accurate? Return ONLY JSON: {{"acceptable": true/false, "problems": []}}"""
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = gd._chat_json(model, prompt, 0)
            return bool(v.get("acceptable")) and not v.get("problems")
        except Exception as e:
            logging.warning(f"[CONTRAST REVIEW] {model}: {e}")
    return False     # a contrast drill that can't be checked isn't shown


def write_mnemonic(word):
    """A memory hook built from the word's REAL components and sound. Only
    used when diagnosis finds no more specific cause."""
    from radical_engine import describe_word
    try:
        parts = describe_word(word["chinese"]).get("characters", [])
    except Exception:
        parts = []
    comps = "; ".join(f"{p['character']} = " + " + ".join(
        c["component"] + (f" ({c['meaning']})" if c.get("meaning") else "")
        for c in p.get("components", [])) for p in parts) or "(no component data)"
    prompt = f"""
Write a short memory hook (1-3 sentences, vivid and concrete) to help an adult
English speaker remember the Chinese word {word['chinese']} ({word['pinyin']}),
meaning "{wc.short_meaning(word['english'])}".
Its components are: {comps}.
Use ONLY these real components (never invent meanings for them) and/or an
English sound-alike for the pinyin, including the tone where you can. Do not
include any other Chinese characters.
Return ONLY JSON: {{"mnemonic": "…"}}
""".strip()
    allowed = set(word["chinese"]) | {c["component"] for p in parts for c in p.get("components", [])}
    try:
        v = gd._chat_json(GENERATION_MODEL, prompt, 0.8)
        text = str(v.get("mnemonic") or "").strip()
        stray = [ch for ch in text if "\u4e00" <= ch <= "\u9fff" and ch not in allowed]
        if text and not stray:
            return text
    except Exception as e:
        logging.warning(f"[MNEMONIC] {e}")
    return None
