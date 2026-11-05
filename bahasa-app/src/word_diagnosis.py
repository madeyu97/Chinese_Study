# src/word_diagnosis.py
"""
Why does a word keep slipping? Diagnose first, then remedy - mnemonics only
when nothing more specific explains it.

A word is TROUBLED when it has lapsed twice after being learned, or has been
missed three times in its last ten scored checks (learning-step and retry
misses don't count: those are part of learning, not evidence of trouble).

The cause is read from the recorded attempts, each piece of evidence
weighted:
  affix          right root, wrong form when typing or speaking; picking
                 another word from the same root (makan / makanan)
  spelling       one or two letters off when typing; misses when reading
                 that don't happen when listening; picking a word spelled
                 almost the same when reading
  sound          misses when listening that don't happen when reading;
                 picking a sound-alike when listening (bawa / bawah)
  confusion      repeatedly picking or saying one particular other word,
                 taking the Indonesian sense (senang = happy), or writing
                 the Indonesian form (bisa for boleh)
  production_gap recognised reliably but not produced
  usage          produced, but with the wrong partner word, grammar or sense
  memory         missed everywhere with no pattern - the only case that gets
                 a mnemonic

Each cause has a remedy: an affix ladder (pick the right form for a gap,
then build it from root + affix), spelling choices and dictation, a
listening contrast against sound-alikes, a contrast drill against the
confused word, a production ladder, chunk practice - or, for memory, a
mnemonic built from the word's sound and its real root.
"""

import logging
import random
import re

import llm
import word_content as wc
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from malay import known as kn, morphology, normalise

SCORED_KINDS = ("review", "unlock", "step2")
CAUSES = ("affix", "spelling", "sound", "confusion", "production_gap", "usage", "memory")
CAUSE_TITLES = {
    "affix": "The affixes",
    "spelling": "The spelling",
    "sound": "Hearing it",
    "confusion": "Mixing it up with another word",
    "production_gap": "Recalling it yourself",
    "usage": "Using it naturally",
    "memory": "Making it stick",
}
PREFERRED_MODE = {   # how later checks lean for a diagnosed word
    ("affix", "recognition"): "ms_to_meaning", ("affix", "production"): "cloze",
    ("spelling", "recognition"): "ms_to_meaning", ("spelling", "production"): "meaning_to_ms",
    ("sound", "recognition"): "audio_to_meaning", ("sound", "production"): "meaning_to_ms",
    ("confusion", "recognition"): "ms_to_meaning", ("confusion", "production"): "cloze",
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

    def d(a):
        return a.get("detail") or {}

    def count(test):
        return sum(1 for a in atts if test(a))

    miss = [a for a in atts if a["result"] in ("wrong", "close")]
    audio_miss = count(lambda a: a["mode"] == "audio_to_meaning" and a["result"] == "wrong")
    audio_ok = count(lambda a: a["mode"] == "audio_to_meaning" and a["result"] == "correct")
    read_miss = count(lambda a: a["mode"] == "ms_to_meaning" and a["result"] == "wrong")
    read_ok = count(lambda a: a["mode"] == "ms_to_meaning" and a["result"] == "correct")
    picked = [(a["mode"], d(a).get("chose_kind")) for a in atts
              if a["result"] == "wrong" and d(a).get("chose_kind")]
    spoken_err = [d(a).get("error") for a in atts if a["mode"] == "spoken" and a["result"] != "correct"]
    rec = [a for a in atts if a["skill"] == "recognition"]
    prod = [a for a in atts if a["skill"] == "production"]
    rec_acc = sum(a["result"] == "correct" for a in rec) / len(rec) if rec else 0
    prod_miss = sum(1 for a in prod if a["result"] == "wrong")

    scores = dict.fromkeys(CAUSES, 0.0)
    evidence = {c: [] for c in CAUSES}

    affix_typed = count(lambda a: d(a).get("affix_error"))
    affix_picked = sum(1 for _m, k in picked if k == "root")
    affix_said = spoken_err.count("affix")
    scores["affix"] = 2 * (affix_typed + affix_picked + affix_said)
    if affix_typed:
        evidence["affix"].append(f"Right root, wrong form {affix_typed}× when typing")
    if affix_picked:
        evidence["affix"].append(f"Picked another word from the same root {affix_picked}×")
    if affix_said:
        evidence["affix"].append(f"Said it with the wrong affix {affix_said}×")

    spell_typed = count(lambda a: d(a).get("spelling_error"))
    look_picked = sum(1 for m, k in picked if k == "sound" and m == "ms_to_meaning")
    scores["spelling"] = 2 * spell_typed + 2 * look_picked
    if spell_typed:
        evidence["spelling"].append(f"Typed it a letter or two off {spell_typed}×")
    if look_picked:
        evidence["spelling"].append(f"Read it as a word spelled almost the same {look_picked}×")
    if read_miss > audio_miss:
        scores["spelling"] += 1.5 * (read_miss - audio_miss)
        evidence["spelling"].append(f"Missed {read_miss} of {read_miss + read_ok} when reading, "
                                    f"{audio_miss} of {audio_miss + audio_ok} when listening")

    heard_alike = sum(1 for m, k in picked if k == "sound" and m == "audio_to_meaning")
    scores["sound"] = 2 * heard_alike
    if heard_alike:
        evidence["sound"].append(f"Heard it as a word that sounds almost the same {heard_alike}×")
    if audio_miss > read_miss:
        scores["sound"] += 1.5 * (audio_miss - read_miss)
        evidence["sound"].append(f"Missed {audio_miss} of {audio_miss + audio_ok} when listening, "
                                 f"{read_miss} of {read_miss + read_ok} when reading")

    wrong_words = [d(a).get("chose") for a in atts
                   if a["result"] == "wrong" and d(a).get("chose_kind") in ("meaning", "other")]
    repeat = max(set(wrong_words), key=wrong_words.count) if wrong_words else None
    repeat_n = wrong_words.count(repeat) if repeat else 0
    meaning_pick = sum(1 for _m, k in picked if k == "meaning")
    false_friend = sum(1 for _m, k in picked if k == "false_friend")
    indo_forms = [d(a)["indonesian"] for a in atts if d(a).get("indonesian")]
    indo_said = spoken_err.count("indonesian")
    wrong_word = spoken_err.count("wrong_word")
    scores["confusion"] = (2 * meaning_pick + (3 * repeat_n if repeat_n >= 2 else 0)
                           + 2 * wrong_word + 2 * false_friend + 2 * len(indo_forms) + 2 * indo_said)
    if repeat_n >= 2:
        evidence["confusion"].append(f"Chose {repeat} instead {repeat_n}×")
    elif meaning_pick:
        evidence["confusion"].append(f"Picked a similar-meaning word {meaning_pick}×")
    if false_friend:
        evidence["confusion"].append(f"Took it in its Indonesian sense {false_friend}×")
    if indo_forms:
        evidence["confusion"].append(f"Wrote the Indonesian form ({indo_forms[0]}) {len(indo_forms)}×")
    if indo_said:
        evidence["confusion"].append(f"Said an Indonesian form {indo_said}×")
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
    confused = None
    if cause == "confusion":
        if repeat_n >= 2:
            confused = repeat
        elif indo_forms:
            confused = max(set(indo_forms), key=indo_forms.count)
    return {"cause": cause, "evidence": evidence[cause], "confused_with": confused,
            "scores": {k: round(v, 1) for k, v in scores.items()}}


# ======================================================================
# Local remedies - built from the word's own data, no model needed
# ======================================================================
_AFFIX_SETS = [((), ""), (("meN",), ""), (("meN",), "kan"), (("meN",), "i"), (("di",), ""),
               (("di",), "kan"), (("ber",), ""), (("ter",), ""), ((), "an"), (("peN",), ""),
               (("peN",), "an"), (("ke",), "an"), (("per",), "an")]


def family(word, pool):
    """Other real words from the word's root: from the learner's pool first,
    then built with the affix rules and kept only if the lexicon has them."""
    root = (word.get("root") or word["malay"]).lower()
    target = word["malay"]
    forms = [w["malay"] for w in pool
             if (w.get("root") or w["malay"]).lower() == root and w["malay"] != target]
    lex, listed = morphology.lexicon(), morphology.default_model().known
    built = [morphology.attach(root, pre, suf) for pre, suf in _AFFIX_SETS]
    built = [f for f in built if f != target and (f in lex or f == root)]
    # words on the frequency list before rarer dictionary forms
    built.sort(key=lambda f: f not in listed)
    return list(dict.fromkeys(forms + built))


_VERBAL = {"meN", "di"}


def _verb_variant(a, b):
    """Two forms that could both fill the same verb slot (ajar / mengajar /
    diajar / mengajari): a gap can't tell them apart, so they are never
    options against each other."""
    pa, pb = morphology.analyse(a), morphology.analyse(b)
    return (set(pa.prefixes) <= _VERBAL and set(pb.prefixes) <= _VERBAL
            and pa.suffix in ("", "kan", "i") and pb.suffix in ("", "kan", "i"))


def affix_rounds(word, pool, content, rng=None):
    """The affix ladder: pick the right form of the root for a gap, then
    build the word from its root and affixes. Options are other words from
    the root that can't fill the same slot (belajar, pelajar, ajaran for
    mengajar - never ajar or mengajari, which colloquial speech allows)."""
    rng = rng or random.Random()
    target = word["malay"]
    root = (word.get("root") or target).lower()
    label = word.get("affixes") or ""
    fam = [f for f in family(word, pool) if not _verb_variant(f, target)]
    rounds = []
    for s in (content.get("sentences") or [])[:2]:
        if not fam:
            break
        opts = [target] + rng.sample(fam[:5], min(3, len(fam[:5])))
        rng.shuffle(opts)
        rounds.append({"show": wc.cloze(s["malay"], target), "english": s.get("english", ""),
                       "question": "Which form fits?", "options": opts, "answer": target,
                       "full": s["malay"]})
    if not rounds and fam:
        opts = [target] + rng.sample(fam[:5], min(3, len(fam[:5])))
        rng.shuffle(opts)
        rounds.append({"show": wc.short_meaning(word["english"]), "question":
                       f"Which form means “{wc.short_meaning(word['english'])}”?",
                       "options": opts, "answer": target})
    if label:
        rounds.append({"show": f"{root} + {label}", "english": wc.short_meaning(word["english"]),
                       "hint": "Build the word from its root and affix.", "typed": True,
                       "answer": target})
    return rounds


def affix_card(word, pool):
    root = (word.get("root") or word["malay"]).lower()
    lines = []
    if word.get("affixes"):
        lines.append(f"{word['malay']} = {root} + {word['affixes']}")
    by_ms = {w["malay"]: w for w in pool}
    fam = [f"{f} ({wc.short_meaning(by_ms[f]['english'])})" if f in by_ms else f
           for f in family(word, pool)[:6]]
    if fam:
        lines.append("Same root: " + " · ".join(fam))
    return lines


_DIGRAPHS = ("ng", "ny", "sy", "kh", "gh")


def syllables(word):
    """sekolah -> se·ko·lah, menyanyi -> me·nya·nyi, bermain -> ber·ma·in,
    sampai -> sam·pai (a final ai / au / oi is one syllable)."""
    units, i = [], 0
    while i < len(word):
        two = word[i:i + 2]
        units.append(two if two in _DIGRAPHS else word[i])
        i += 2 if two in _DIGRAPHS else 1
    vowel = [u in "aeiou" for u in units]
    out, cur = [], ""
    for j, u in enumerate(units):
        has_vowel = any(c in "aeiou" for c in cur)
        if not vowel[j] and j + 1 < len(units) and vowel[j + 1] and has_vowel:
            out.append(cur)
            cur = ""
        elif vowel[j] and j and vowel[j - 1]:
            final_diphthong = units[j - 1] + u in ("ai", "au", "oi") and j == len(units) - 1
            if not final_diphthong:
                out.append(cur)
                cur = ""
        cur += u
    if cur:
        out.append(cur)
    return out


def misspellings(word, n=3, rng=None):
    """Plausible wrong spellings that are not real words: vowel swaps, a
    dropped final h, a doubled or dropped letter."""
    rng = rng or random.Random()
    lex = morphology.lexicon()
    cands = set()
    for i, ch in enumerate(word):
        if ch in "ae":
            cands.add(word[:i] + ("a" if ch == "e" else "e") + word[i + 1:])
        if ch in "iu":
            cands.add(word[:i] + ("e" if ch == "i" else "o") + word[i + 1:])
        if ch not in "aeiou" and 0 < i < len(word) - 1:
            cands.add(word[:i] + ch + word[i:])          # doubled consonant
    if word.endswith("h"):
        cands.add(word[:-1])
    elif word[-1] in "aeiou":
        cands.add(word + "h")
    cands.add(word.replace("sy", "sh", 1))
    cands.add(word.replace("c", "ch", 1))
    cands = [c for c in cands if c != word and c not in lex and len(c) > 1]
    rng.shuffle(cands)
    return sorted(cands[:n], key=lambda c: rng.random())


def spelling_rounds(word, rng=None):
    rng = rng or random.Random()
    target = word["malay"]
    rounds = []
    wrong = misspellings(target, 3, rng)
    if wrong:
        opts = wrong + [target]
        rng.shuffle(opts)
        rounds.append({"show": wc.short_meaning(word["english"]), "question": "Which is spelled right?",
                       "options": opts, "answer": target})
    rounds.append({"play": target, "question": "", "hint": "Listen, then type it.",
                   "typed": True, "answer": target})
    if len(wrong) > 1:
        opts = wrong[1:] + [target]
        rng.shuffle(opts)
        rounds.append({"play": target, "question": "Which did you hear?", "options": opts,
                       "answer": target})
    return rounds


def sound_rounds(word, pool, rng=None):
    """Hear one of the word and its closest-sounding neighbours; say which.
    With no neighbours to hand, hear it and type it."""
    rng = rng or random.Random()
    target = word["malay"]
    neigh = [w for w in pool if w["malay"] != target and " " not in w["malay"]
             and wc.sounds_alike(target, w["malay"])]
    rng.shuffle(neigh)
    group = [word] + neigh[:2]
    if len(group) < 2:
        return [{"play": target, "question": "", "hint": "Listen, then type what you heard.",
                 "typed": True, "answer": target}] * 2
    rounds = []
    for _ in range(3):
        played = rng.choice(group)
        opts = [w["malay"] for w in group]
        rng.shuffle(opts)
        rounds.append({"play": played["malay"], "question": "Which did you hear?",
                       "options": opts, "answer": played["malay"],
                       "note": f"{played['malay']} = {wc.short_meaning(played['english'])}"})
    return rounds


def production_ladder(word, content):
    """From heavy support to none: gap with the first letters given, gap
    with nothing given, then the chunk from its meaning."""
    t = word["malay"]
    sents = content.get("sentences") or []
    chunks = content.get("chunks") or []
    steps = []
    head = t[:2] if len(t) > 3 else t[:1]
    if sents:
        s = sents[0]
        steps.append({"show": wc.cloze(s["malay"], t).replace("＿＿＿", head + "＿＿", 1),
                      "english": s.get("english", ""), "hint": f"starts with {head}…",
                      "typed": True, "answer": t})
    if len(sents) > 1:
        s = sents[1]
        steps.append({"show": wc.cloze(s["malay"], t), "english": s.get("english", ""),
                      "hint": "", "typed": True, "answer": t})
    if chunks:
        c = chunks[0]
        steps.append({"show": c.get("english", ""), "english": "Say the whole chunk.",
                      "hint": "", "typed": True, "answer": c["malay"]})
    if not steps:
        steps.append({"show": wc.short_meaning(word["english"]), "english": "Say or type the Malay.",
                      "hint": f"starts with {head}…", "typed": True, "answer": t})
    return steps


def usage_rounds(word, content):
    """Chunks again: produce each from its meaning."""
    return [{"show": c.get("english", ""), "english": "Say it the natural way.",
             "hint": "", "typed": True, "answer": c["malay"], "chunk": True}
            for c in (content.get("chunks") or [])[:3]]


def check_chunk(answer, chunk, target, spoken=False):
    """Whole chunk = correct; only the target word = close; else wrong."""
    result, detail = wc.check_answer(answer, chunk, spoken=spoken)
    if result == "wrong" and wc.contains(answer or "", target):
        return "close", {**detail, "partial": True}
    return result, detail


def indonesian_card(word, other):
    """When the 'confused' word is the Indonesian form of this one."""
    if word["malay"] in [m.split()[0] for m in normalise.malaysian_for(other)]:
        return [f"Indonesian: {other}  →  Malaysian: {word['malay']}",
                f"In Malaysia, say {word['malay']}. {other} is what you'll hear in Indonesian films."]
    return []


# ======================================================================
# Model-written remedies: contrast with a confused word, and mnemonics
# ======================================================================
def write_contrast(word, other, known):
    """A short difference plus four gap sentences, each needing either the
    word or the one it gets confused with. Returns dict or None."""
    a, b = word["malay"], other["malay"]
    prompt = f"""
A learner of MALAYSIAN Malay keeps confusing {a} ({wc.short_meaning(word['english'])})
with {b} ({wc.short_meaning(other['english'])}).

Write:
- "difference": one or two plain-English sentences on how they differ in use.
- "items": 4 short natural Malaysian Malay sentences (4-10 words), two needing
  {a} and two needing {b}, where only that word fits. Give each sentence in
  full ("malay"), which word it needs ("answer") and its English.
Use only these known words plus the two words and common function words:
{", ".join(sorted(known)[:400])}
Malaysian Malay only, never Indonesian ({wc.INDONESIAN_EXAMPLES}). Numbers as words.

Return ONLY JSON: {{"difference": "…", "items": [{{"malay": "…", "answer": "…", "english": "…"}}]}}
""".strip()
    allowed = kn.allowed_set(known, [a, b])
    for attempt in range(llm.MAX_ATTEMPTS):
        try:
            v = llm.chat_json(GENERATION_MODEL, prompt, 0.6)
        except Exception as e:
            logging.warning(f"[CONTRAST] attempt {attempt + 1}: {e}")
            continue
        items, ok = [], True
        for it in (v.get("items") or [])[:4]:
            text = re.sub(r"\s+", " ", str(it.get("malay") or "")).strip()
            ans = str(it.get("answer") or "").strip().lower()
            if ans not in (a, b) or not wc.contains(text, ans) or re.search(r"\d", text) \
                    or normalise.indonesian_in(text) or kn.unknown_words(text, allowed):
                ok = False
                break
            items.append({"malay": text, "answer": ans, "english": it.get("english", ""),
                          "gap": wc.cloze(text, ans)})
        if ok and len(items) == 4 and {i["answer"] for i in items} == {a, b} \
                and str(v.get("difference") or "").strip():
            if _review_contrast(word, other, v["difference"], items):
                return {"difference": v["difference"], "items": items}
    return None


def _review_contrast(word, other, difference, items):
    lines = "\n".join(f"- {i['malay']} (needs {i['answer']})" for i in items)
    prompt = f"""Native reviewer of MALAYSIAN Malay. Check this contrast between
{word['malay']} and {other['malay']}. Difference given: {difference}
{lines}
Is each sentence natural Malaysian (not Indonesian) Malay, and does ONLY the
stated word fit its gap? Is the difference accurate?
Return ONLY JSON: {{"acceptable": true/false, "problems": []}}"""
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = llm.chat_json(model, prompt, 0)
            return bool(v.get("acceptable")) and not v.get("problems")
        except Exception as e:
            logging.warning(f"[CONTRAST REVIEW] {model}: {e}")
    return False     # a contrast drill that can't be checked isn't shown


def write_mnemonic(word, root_gloss=""):
    """A memory hook built from the word's sound and its REAL root. Only
    used when diagnosis finds no more specific cause."""
    target = word["malay"]
    root = (word.get("root") or target).lower()
    parts = (f"Its root is {root}" + (f" ({root_gloss})" if root_gloss else "")
             + f", with {word['affixes']}." if word.get("affixes") and root != target else
             "It is a root word, with no affixes.")
    prompt = f"""
Write a short memory hook (1-3 sentences, vivid and concrete) to help an adult
English speaker remember the Malaysian Malay word {target} ({" · ".join(syllables(target))}),
meaning "{wc.short_meaning(word['english'])}".
{parts}
Use an English sound-alike for the word or its syllables, and/or the root's
real meaning given above. Never invent a meaning for the root or any other
Malay word.
Return ONLY JSON: {{"mnemonic": "…"}}
""".strip()
    try:
        v = llm.chat_json(GENERATION_MODEL, prompt, 0.8)
        text = str(v.get("mnemonic") or "").strip()
        if text and len(text) <= 400 and (target in text.lower() or root in text.lower()):
            return text
    except Exception as e:
        logging.warning(f"[MNEMONIC] {e}")
    return None
