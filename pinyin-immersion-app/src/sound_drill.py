# src/sound_drill.py
"""
Sound & Pairing drills, built only from vocabulary already introduced, so
they grow as the learner's vocabulary does.

TONE DRILL - characters are grouped by syllable across the learner's words:
xiang -> 香 (香味) xiāng · 想 (想要) xiǎng · 像 (好像) xiàng. Every option shows
the character AND a real word it appears in, never bare pinyin, because many
characters share a sound. Two directions:
  tone_hear  hear it, pick which character/word/meaning it was
  tone_pick  see the character in its word, pick its tone (then say it and
             compare with the model)
Only groups where the learner knows at least two different tones are used,
most frequent first.

PAIRING DRILL - for characters that form several of the learner's words, drill
the words rather than the character's dictionary senses:
  想 -> 想要 (want) · 想法 (idea) · 想念 (miss)
  pair_meaning   which 想-word means "idea"?
  pair_complete  想 + ? = idea
  pair_word      what does 想念 mean?
Families grow as new words are introduced.

Listening items only use characters the speech engine will say in the right
tone: anything with 了 (read 'liào' by the app's TTS, except in 了解) is
excluded, and a character whose default reading differs from the one being
drilled is played inside its word instead.
"""

import random
import re
import unicodedata

from pypinyin import lazy_pinyin, pinyin as _pinyin, Style

import word_content as wc

TONE_MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
MAX_GROUPS_NEW = 3        # new groups / families per session
GROUPS_PER_SESSION = 5
ITEMS_PER_GROUP = 2


# ======================================================================
# Readings
# ======================================================================
def _toned(syl):
    return wc._toned(syl)[0] if wc._toned(syl) else (syl, 5)


def char_readings(word):
    """[(char, syllable)] for a word whose pinyin has one syllable per
    character (the lists' house style); [] otherwise."""
    zh = word.get("chinese") or ""
    syl = (word.get("pinyin") or "").split()
    if not re.fullmatch(r"[\u4e00-\u9fff]+", zh) or len(syl) != len(zh):
        return []
    return list(zip(zh, syl))


def tts_safe(text, pinyin):
    """Will the app's speech engine say `text` with this pinyin? Rejects 了
    (substituted with 料) and characters whose default reading differs."""
    if "了" in text and "了解" not in text:
        return False
    if len(text) == 1 and len(set(_pinyin(text, style=Style.TONE, heteronym=True)[0])) > 1:
        return False    # several readings: only its word can say which one is meant
    default = lazy_pinyin(text, style=Style.TONE)
    want = pinyin.split()
    if len(default) != len(want):
        return False
    for ch, d, w in zip(text, default, want):
        if ch in "一不":
            continue                            # tone sandhi: read correctly in context
        wb, wt = _toned(w)
        db_, dt = _toned(d)
        if wb != db_ or (wt != 5 and dt != wt):
            return False
    return True


def with_tone(base, tone):
    """'xiang', 3 -> 'xiǎng' (standard placement rules)."""
    if tone == 5:
        return base
    for v in "ae":
        if v in base:
            return base.replace(v, TONE_MARKS[v][tone - 1], 1)
    if "ou" in base:
        return base.replace("o", TONE_MARKS["o"][tone - 1], 1)
    for i in range(len(base) - 1, -1, -1):
        if base[i] in "iouü":
            return base[:i] + TONE_MARKS[base[i]][tone - 1] + base[i + 1:]
    return base


# ======================================================================
# Tone groups
# ======================================================================
def tone_groups(words):
    """Group the learner's characters by syllable. words: introduced word
    dicts (chinese, pinyin, english, freq_rank). Returns groups, most useful
    first: {key, patterns: [{tone, pinyin, entries: [{char, word, …}]}]}."""
    by_reading = {}
    for w in sorted(words, key=lambda w: (w.get("freq_rank") or 10 ** 6, len(w["chinese"]))):
        for ch, syl in char_readings(w):
            base, tone = _toned(syl)
            if tone == 5 or ch in "一不":
                continue    # neutral tone, and 一/不 whose tone changes by context
            key = (ch, base, tone)
            e = by_reading.setdefault(key, {"char": ch, "base": base, "tone": tone,
                                            "pinyin": syl, "words": [], "rank": 10 ** 6})
            if w["chinese"] not in [x["chinese"] for x in e["words"]]:
                e["words"].append(w)
                e["rank"] = min(e["rank"], w.get("freq_rank") or 10 ** 6)
    groups = {}
    for e in by_reading.values():
        g = groups.setdefault(e["base"], {})
        g.setdefault(e["tone"], []).append(e)
    out = []
    for base, tones in groups.items():
        if len(tones) < 2:
            continue
        patterns = []
        for tone in sorted(tones):
            entries = sorted(tones[tone], key=lambda e: e["rank"])
            patterns.append({"tone": tone, "pinyin": with_tone(base, tone), "entries": entries})
        rank = min(e["rank"] for es in tones.values() for e in es)
        out.append({"key": base, "patterns": patterns, "rank": rank})
    out.sort(key=lambda g: (g["rank"], -len(g["patterns"])))
    return out


def _example(entry):
    """The character's most frequent word, preferring a real compound so the
    character is always seen in a word."""
    compounds = [w for w in entry["words"] if len(w["chinese"]) > 1]
    return (compounds or entry["words"])[0]


def _meaning_in(entry, word):
    return wc.short_meaning(word["english"])


def tone_hear_item(group, rng):
    """Play one character (or its word, if the character alone isn't safe to
    play) and ask which it was. One option per tone, so every option sounds
    different."""
    options = []
    for p in group["patterns"]:
        for e in p["entries"]:
            ex = _example(e)
            if tts_safe(e["char"], e["pinyin"]) or tts_safe(ex["chinese"], ex["pinyin"]):
                options.append((p, e, ex))
                break
    if len(options) < 2:
        return None
    options = options[:4]
    p, e, ex = rng.choice(options)
    play = e["char"] if tts_safe(e["char"], e["pinyin"]) else ex["chinese"]
    return {"type": "tone_hear", "key": group["key"], "play": play,
            "question": "Which did you hear?" if play == e["char"] else "Which word did you hear?",
            "options": [{"value": f"{o[1]['char']}|{o[2]['chinese']}",
                         "label": f"{o[1]['char']}　({o[2]['chinese']}) — {_meaning_in(o[1], o[2])}"}
                        for o in options],
            "answer": f"{e['char']}|{ex['chinese']}", "word": ex,
            "reveal": [f"{o[1]['char']} {o[0]['pinyin']} — as in {o[2]['chinese']} "
                       f"{o[2]['pinyin']} ({_meaning_in(o[1], o[2])})" for o in options]}


def tone_pick_item(group, rng):
    """Show a character inside its word and its meaning; pick its tone."""
    p = rng.choice(group["patterns"])
    e = rng.choice(p["entries"][:2])
    ex = _example(e)
    tones = [with_tone(group["key"], t) for t in (1, 2, 3, 4)]
    return {"type": "tone_pick", "key": group["key"], "play": ex["chinese"]
            if tts_safe(ex["chinese"], ex["pinyin"]) else None,
            "char": e["char"], "show_word": ex["chinese"],
            "question": f"How is {e['char']} said in {ex['chinese']} ({_meaning_in(e, ex)})?",
            "options": [{"value": t, "label": t} for t in tones],
            "answer": p["pinyin"], "word": ex,
            "reveal": [f"{x['char']} {pp['pinyin']} — as in {_example(x)['chinese']}"
                       for pp in group["patterns"] for x in pp["entries"][:2]]}


# ======================================================================
# Character families (pairing)
# ======================================================================
def families(words, char_words=None):
    """char -> {char, char_word, words}: the learner's multi-character words
    that contain the character. Only characters in at least two such words.
    char_words: optional {char: single-character vocab entry} for its own
    meaning. Most useful first."""
    char_words = char_words or {}
    fam = {}
    for w in sorted(words, key=lambda w: w.get("freq_rank") or 10 ** 6):
        zh = w["chinese"]
        if len(zh) < 2 or not re.fullmatch(r"[\u4e00-\u9fff]+", zh):
            continue
        for ch in set(zh):
            f = fam.setdefault(ch, {"char": ch, "words": [], "rank": 10 ** 6})
            if zh not in [x["chinese"] for x in f["words"]]:
                f["words"].append(w)
    out = []
    for ch, f in fam.items():
        meanings = {wc.short_meaning(w["english"]).lower() for w in f["words"]}
        if len(f["words"]) < 2 or len(meanings) < 2:
            continue
        cw = char_words.get(ch)
        f["char_word"] = cw
        senses = len(re.split(r"\s*/\s*", cw["english"])) if cw else 1
        f["score"] = len(f["words"]) * 2 + min(senses, 3) - \
            (cw.get("freq_rank") or 20000) / 20000 if cw else len(f["words"]) * 2
        out.append(f)
    out.sort(key=lambda f: -f["score"])
    return out


def _partner(word, ch):
    """The word with everything except the family character blanked: 想象 -> 想＿."""
    return "".join(c if c == ch else "＿" for c in word["chinese"])


def pair_item(family, rng, kind=None):
    ch, words = family["char"], family["words"][:4]
    target = rng.choice(words)
    kind = kind or rng.choice(("pair_meaning", "pair_complete", "pair_word"))
    meaning = wc.short_meaning(target["english"])
    others = [w for w in words if w is not target]
    if kind == "pair_meaning":
        opts = [{"value": w["chinese"], "label": f"{w['chinese']}"} for w in words]
        q = f"Which {ch}-word means “{meaning}”?"
        answer = target["chinese"]
    elif kind == "pair_complete":
        # the rest of the word, alongside the rest of the other words
        rest = lambda w: w["chinese"].replace(ch, "", 1)
        opts = [{"value": rest(w), "label": rest(w)} for w in words]
        q = f"{_partner(target, ch)} — “{meaning}”. What goes with {ch}?"
        answer = rest(target)
    else:
        opts = [{"value": wc.short_meaning(w["english"]), "label": wc.short_meaning(w["english"])}
                for w in words]
        q = f"What does {target['chinese']} mean?"
        answer = meaning
    seen, uniq = set(), []
    for o in opts:
        if o["value"] not in seen:
            seen.add(o["value"])
            uniq.append(o)
    rng.shuffle(uniq)
    cw = family.get("char_word")
    return {"type": kind, "key": ch, "question": q, "options": uniq, "answer": answer,
            "play": target["chinese"] if tts_safe(target["chinese"], target["pinyin"]) else None,
            "show_word": target["chinese"] if kind != "pair_complete" else None,
            "char": ch, "word": target,
            "header": f"{ch}" + (f" {cw['pinyin']} — on its own: {cw['english']}" if cw else ""),
            "reveal": [f"{w['chinese']} {w['pinyin']} — {wc.short_meaning(w['english'])}"
                       for w in family["words"][:6]]}


# ======================================================================
# Session
# ======================================================================
def pick_keys(candidates, progress, today, n=GROUPS_PER_SESSION, new_cap=MAX_GROUPS_NEW):
    """Due keys first (oldest first), then new ones in usefulness order.
    candidates: keys in priority order; progress: key -> track."""
    today = today.isoformat() if hasattr(today, "isoformat") else str(today)
    due = [k for k in candidates if k in progress
           and (progress[k].get("next_review_date") or "") <= today]
    due.sort(key=lambda k: progress[k].get("next_review_date") or "")
    fresh = [k for k in candidates if k not in progress][:new_cap]
    return (due + fresh)[:n]


def build_session(drill, groups_or_families, progress, today, rng=None, new_cap=MAX_GROUPS_NEW):
    """new_cap: new groups allowed this session (the page passes what is left
    of the day's allowance)."""
    rng = rng or random.Random()
    by_key = {g["key"] if drill == "tone" else g["char"]: g for g in groups_or_families}
    keys = pick_keys(list(by_key), progress, today, new_cap=max(0, min(new_cap, MAX_GROUPS_NEW)))
    items = []
    for k in keys:
        g = by_key[k]
        if drill == "tone":
            made = [tone_hear_item(g, rng), tone_pick_item(g, rng)]
        else:
            kinds = ["pair_meaning", "pair_complete", "pair_word"]
            rng.shuffle(kinds)
            made = [pair_item(g, rng, kinds[0]), pair_item(g, rng, kinds[1])]
        items += [m for m in made if m][:ITEMS_PER_GROUP]
    # interleave groups so the same key isn't asked twice in a row
    first, second = items[0::2], items[1::2]
    rng.shuffle(second)
    out = []
    for a, b in zip(first, second):
        out += [a, b]
    out += first[len(second):] + second[len(first):]
    for i in range(1, len(out)):
        if out[i]["key"] == out[i - 1]["key"] and i + 1 < len(out):
            out[i], out[i + 1] = out[i + 1], out[i]
    return out


def group_result(results):
    """All right -> correct; mostly right -> close; else wrong."""
    if not results:
        return "ungraded"
    share = sum(results) / len(results)
    return "correct" if share == 1 else "close" if share >= 0.5 else "wrong"
