# src/affix_drill.py
"""
Affix drills: one root, many words (main → bermain · pemain · permainan ·
mainan). Built only from words the learner has met, so families grow with
the vocabulary.

FAMILY - a root with at least MIN_FORMS forms the learner has met (the root
word itself counts). Other real forms of the root, from the word list, are
used only as wrong options, never as answers.

Four drills, each a short item:
  form_meaning  which form means "player"?            pick from the family
  form_build    peN- + main = ?                       type it (the sound
                                                       changes of meN-/peN-)
  form_gap      Dia ＿＿＿ yang bagus. - pick the form  from a real sentence
  affix_adds    main (play) → pemain (player):        pick what peN- adds
                what does peN- add?

Two forms whose meanings overlap (buat "do / make", membuat "make / do")
are never offered as rival answers. A build answer is right if it is any
real form with the same affixes (peN- + ajar + -an is pelajaran and also
pengajaran).

Each family is scheduled as one item in drill_progress (drill
"affix_family"), from the share of its items answered right.
"""

import random
import re

import word_content as wc

DRILL = "affix_family"
MIN_FORMS = 3                 # met forms of a root, the root word included
FAMILIES_PER_SESSION = 5
MAX_NEW_PER_SESSION = 3
ITEMS_PER_FAMILY = 3
KINDS = ("form_meaning", "form_build", "form_gap", "affix_adds")
KIND_SKILL = {"form_meaning": "production", "form_build": "production",
              "form_gap": "production", "affix_adds": "recognition"}
_SINGLE = re.compile(r"^[a-z]+(-[a-z]+)*$")
_LABEL = re.compile(r"(?:([A-Za-z]+)-)?…?(?:-([a-z]+))?")

# What each affix adds, by group. Options in one question come from
# different groups, and a confix with -kan or -i never competes with plain
# meN- or di- (which it also contains).
ROLES = {
    "meN-": ("active", "makes it an active verb: someone does it"),
    "di-": ("passive", "makes it passive: it is done to something"),
    "ber-": ("ber", "has it, or is doing it (no object)"),
    "ter-": ("ter", "it happened by itself or by accident; it ended up that way"),
    "ter-@adj": ("most", "the most: the -est"),
    "peN-": ("doer", "the person or thing that does it"),
    "pe-": ("doer", "the person or thing that does it"),
    "peN-…-an": ("process", "the act or process of doing it"),
    "pe-…-an": ("process", "the act or process of doing it"),
    "per-…-an": ("result", "a noun for its result, matter or place"),
    "ke-…-an": ("quality", "a noun for the quality or state: -ness, -ity"),
    "-an": ("thing", "a noun for the thing done or made"),
    "-kan": ("cause", "makes it happen, or does it for someone"),
    "meN-…-kan": ("cause", "makes it happen, or does it for someone (active)"),
    "di-…-kan": ("cause", "made to happen, or done for someone (passive)"),
    "-i": ("target", "does it to or at someone or something"),
    "meN-…-i": ("target", "does it to or at someone or something (active)"),
    "di-…-i": ("target", "done to or at someone or something (passive)"),
    "se-": ("one", "one, the same, or as … as"),
    "se-…-nya": ("adverb", "as … as possible, or an adverb"),
    "ber-…-an": ("mutual", "doing it together, or to each other"),
    "memper-…-kan": ("more", "makes it so, or more so"),
    "per-…-kan": ("more", "makes it so, or more so"),
    "memper-…-i": ("more", "makes it so, or more so"),
    "per-…-i": ("more", "makes it so, or more so"),
}
_CLASHES = {"cause": {"active", "passive"}, "target": {"active", "passive"},
            "more": {"active", "passive", "cause", "target"}}
EXAMPLES = {"active": ("baca → membaca", "tulis → menulis"), "passive": ("baca → dibaca", "buat → dibuat"),
            "ber": ("jalan → berjalan", "kerja → bekerja"), "ter": ("jatuh → terjatuh", "kenal → terkenal"),
            "most": ("baik → terbaik", "besar → terbesar"), "doer": ("main → pemain", "jual → penjual"),
            "process": ("ajar → pengajaran", "bangun → pembangunan"),
            "result": ("jalan → perjalanan", "main → permainan"),
            "quality": ("selamat → keselamatan", "sihat → kesihatan"),
            "thing": ("makan → makanan", "main → mainan"), "cause": ("besar → besarkan", "naik → naikkan"),
            "target": ("dekat → dekati", "suka → menyukai"), "one": ("besar → sebesar", "rumah → serumah"),
            "adverb": ("baik → sebaiknya", "benar → sebenarnya"),
            "mutual": ("kenal → berkenalan", "jauh → berjauhan"),
            "more": ("kenal → memperkenalkan", "baik → memperbaiki")}


# ======================================================================
# Families
# ======================================================================
def _usable(word):
    """A single, untagged word whose affixes (if any) are derivational -
    clitics (+nya, +lah) and reduplication aren't drilled here."""
    label = word.get("affixes") or ""
    return (_SINGLE.match(word.get("malay") or "") and not word.get("tag")
            and "+" not in label and label != "R")


def root_of(word):
    return word.get("root") or word["malay"]


def families(words, siblings=None):
    """Roots with at least MIN_FORMS met forms, most useful first.
    words: the learner's introduced words (malay, english, root, affixes,
    pos, freq_rank, id). siblings: optional {root: [list rows]} with every
    form of the root in the word list, used for wrong options and the
    root's own gloss. Returns [{key, met: [rows], others: [rows], root_row}]."""
    siblings = siblings or {}
    by_root = {}
    for w in sorted(words, key=lambda w: w.get("freq_rank") or 10 ** 6):
        if not _usable(w):
            continue
        fam = by_root.setdefault(root_of(w), [])
        if w["malay"] not in [x["malay"] for x in fam]:
            fam.append(w)
    out = []
    for root, met in by_root.items():
        if len(met) < MIN_FORMS or not any(w.get("affixes") for w in met):
            continue
        met_names = {w["malay"] for w in met}
        others = [s for s in siblings.get(root, []) if _usable(s) and s["malay"] not in met_names]
        root_row = next((w for w in met + siblings.get(root, []) if w["malay"] == root), None)
        out.append({"key": root, "met": met, "others": others, "root_row": root_row,
                    "rank": min(w.get("freq_rank") or 10 ** 6 for w in met)})
    out.sort(key=lambda f: (-len(f["met"]), f["rank"]))
    return out


# ======================================================================
# Meanings and labels
# ======================================================================
def senses(word):
    """The set of a word's senses, for telling whether two forms could both
    be the answer: 'make / do' and 'do / make' overlap."""
    out = set()
    for part in re.split(r"\s*[/;,]\s*", (word.get("english") or "").lower()):
        part = re.sub(r"\([^)]*\)", "", part).strip()          # get (it) = get
        part = re.sub(r"^(to|be|a|an|the)\s+", "", part)
        if part:
            out.add(part)
    return out


def distinct(a, b):
    """Could not both be the answer: no shared sense, and no two senses
    starting with the same word (think / think about)."""
    if a["malay"] == b["malay"]:
        return False
    sa, sb = senses(a), senses(b)
    return not (sa & sb) and not ({s.split()[0] for s in sa} & {s.split()[0] for s in sb})


def meaning(word):
    return wc.short_meaning(word.get("english") or "")


def parts(label):
    """'meN-…-kan' -> ('meN', 'kan'); '-an' -> (None, 'an'); None if the
    label isn't one prefix and/or one suffix (ber-peN-, R)."""
    if not label:
        return None
    m = _LABEL.fullmatch(label)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return m.group(1), m.group(2)


def build_prompt(label, root):
    pre, suf = parts(label)
    return " + ".join(([f"{pre}-"] if pre else []) + [root] + ([f"-{suf}"] if suf else []))


def role(label, root_row=None):
    """(group, what the affix adds) or None. ter- on an adjective is 'most'."""
    if label == "ter-" and root_row and (root_row.get("pos") or "").startswith("adj"):
        return ROLES["ter-@adj"]
    return ROLES.get(label)


def nasal_note(label, root, form):
    """How meN- / peN- joined the root: 'men- before t, and the t drops'."""
    if not label or not (label.startswith("meN-") or label.startswith("peN-")):
        return ""
    base = "me" if label.startswith("meN-") else "pe"
    if form.startswith(base + "nge") and form[len(base) + 3:].startswith(root):
        return f"{base}nge- before a one-syllable root: {form}"
    for nasal in ("ny", "ng", "m", "n", ""):
        p = base + nasal
        if not form.startswith(p):
            continue
        rest = form[len(p):]
        if rest.startswith(root):
            return f"{p}- before {root[0]}: {form}"
        if root[0] in "ptks" and len(root) > 1 and rest.startswith(root[1:]):
            return f"{p}- and the {root[0]} drops: {form}"
    return ""


# ======================================================================
# Items
# ======================================================================
def _options(target, pool, n=4):
    """target plus up to n-1 forms whose meanings don't overlap with it or
    with each other."""
    chosen = [target]
    for w in pool:
        if len(chosen) >= n:
            break
        if all(distinct(w, c) for c in chosen):
            chosen.append(w)
    return chosen


def _reveal(family):
    """The family as met: each form, its affixes and its full gloss."""
    met = sorted(family["met"], key=lambda w: (bool(w.get("affixes")), w.get("freq_rank") or 10 ** 6))
    return [f"{w['malay']} · {w.get('affixes') or 'root'} — {w.get('english', '')}" for w in met[:7]]


def _forms(family):
    """form -> short meaning, for every form an answer could name."""
    return {w["malay"]: meaning(w) for w in family["met"] + family["others"]}


def example(group, target):
    """An example of the affix that isn't the item itself."""
    return next((e for e in EXAMPLES.get(group, ()) if not e.endswith(" " + target)), "")


def form_meaning_item(family, target, rng):
    pool = [w for w in family["met"] if w is not target] + family["others"]
    opts = _options(target, pool)
    if len(opts) < 3:
        return None
    rng.shuffle(opts)
    return {"type": "form_meaning", "key": family["key"], "word": target,
            "question": f"Which form means “{meaning(target)}”?",
            "options": [{"value": w["malay"], "label": w["malay"]} for w in opts],
            "answer": target["malay"], "known_forms": _forms(family), "reveal": _reveal(family)}


def form_build_item(family, target, rng):
    label = target.get("affixes") or ""
    if not parts(label):
        return None
    root = family["key"]
    accepted = {w["malay"] for w in family["met"] + family["others"]
                if (w.get("affixes") or "") == label}
    return {"type": "form_build", "key": root, "word": target,
            "question": f"{build_prompt(label, root)} = ?",
            "hint": f"“{meaning(target)}”", "answer": target["malay"],
            "accepted": sorted(accepted),
            "known_forms": _forms(family),
            "note": nasal_note(label, root, target["malay"]), "reveal": _reveal(family)}


def form_gap_item(family, target, sentences, rng):
    """sentences: [{malay, english}] containing the target."""
    usable = [s for s in sentences
              if wc.contains(s["malay"], target["malay"])
              and not any(wc.contains(s["malay"], w["malay"])
                          for w in family["met"] + family["others"] if w is not target)]
    if not usable:
        return None
    s = rng.choice(usable[:3])
    pool = [w for w in family["met"] if w is not target] + family["others"]
    pool.sort(key=lambda w: (w.get("pos") or "") == (target.get("pos") or ""))   # stable
    opts = _options(target, pool)
    if len(opts) < 3:
        return None
    rng.shuffle(opts)
    return {"type": "form_gap", "key": family["key"], "word": target,
            "question": "Which form fills the gap?", "sentence": wc.cloze(s["malay"], target["malay"]),
            "full": s["malay"], "english": s.get("english", ""),
            "options": [{"value": w["malay"], "label": w["malay"]} for w in opts],
            "answer": target["malay"], "known_forms": _forms(family), "reveal": _reveal(family)}


def affix_adds_item(family, target, rng):
    label = target.get("affixes") or ""
    r = role(label, family.get("root_row"))
    root_row = family.get("root_row")
    if not r or not root_row:
        return None
    group, text = r
    banned = {group} | _CLASHES.get(group, set())
    banned |= {g for g, clashes in _CLASHES.items() if group in clashes}
    others, seen = [], set()
    pool = sorted(set(ROLES.values()))
    rng.shuffle(pool)
    for g, t in pool:
        if g not in banned and g not in seen and t != text:
            others.append(t)
            seen.add(g)
        if len(others) == 3:
            break
    opts = [text] + others
    rng.shuffle(opts)
    return {"type": "affix_adds", "key": family["key"], "word": target,
            "header": f"{root_row['malay']} ({meaning(root_row)}) → "
                      f"{target['malay']} ({meaning(target)})",
            "question": f"What does {label} add here?",
            "options": [{"value": o, "label": o} for o in opts], "answer": text,
            "known_forms": {}, "reveal": [f"{label}: {text} — e.g. {example(group, target['malay'])}"]
            + _reveal(family)}


def items_for(family, sentences, rng, n=ITEMS_PER_FAMILY):
    """Up to n items for one family, each a different drill, on different
    forms where possible. sentences: {form: [{malay, english}]}."""
    derived = [w for w in family["met"] if w.get("affixes")]
    kinds = list(KINDS)
    rng.shuffle(kinds)
    made, used = [], []
    for kind in kinds:
        if len(made) >= n:
            break
        targets = [w for w in derived if w["malay"] not in used] + \
                  [w for w in derived if w["malay"] in used]
        for target in targets:
            if kind == "form_meaning":
                it = form_meaning_item(family, target, rng)
            elif kind == "form_build":
                it = form_build_item(family, target, rng)
            elif kind == "form_gap":
                it = form_gap_item(family, target, sentences.get(target["malay"], []), rng)
            else:
                it = affix_adds_item(family, target, rng)
            if it:
                made.append(it)
                used.append(target["malay"])
                break
    return made


def check_typed(item, typed):
    """(right, message) for a form_build answer."""
    said = re.sub(r"[^a-z-]", "", (typed or "").strip().lower())
    if said in item["accepted"]:
        return True, ""
    if said in item["known_forms"]:
        return False, f"{said} is a real form — it means “{item['known_forms'][said]}”."
    return False, ""


# ======================================================================
# Session
# ======================================================================
def pick_keys(candidates, progress, today, n=FAMILIES_PER_SESSION, new_cap=MAX_NEW_PER_SESSION):
    """Due families first (oldest first), then new ones in usefulness order."""
    today = today.isoformat() if hasattr(today, "isoformat") else str(today)
    due = [k for k in candidates if k in progress
           and (progress[k].get("next_review_date") or "") <= today]
    due.sort(key=lambda k: progress[k].get("next_review_date") or "")
    fresh = [k for k in candidates if k not in progress][:max(0, new_cap)]
    return (due + fresh)[:n]


def build_session(fams, progress, today, sentences=None, rng=None, new_cap=MAX_NEW_PER_SESSION):
    """Items for today's families, interleaved so one family isn't asked
    twice in a row where that can be avoided."""
    rng = rng or random.Random()
    sentences = sentences or {}
    by_key = {f["key"]: f for f in fams}
    keys = pick_keys(list(by_key), progress, today, new_cap=min(new_cap, MAX_NEW_PER_SESSION))
    rounds = [items_for(by_key[k], sentences, rng) for k in keys]
    out = []
    for i in range(max((len(r) for r in rounds), default=0)):
        out += [r[i] for r in rounds if i < len(r)]
    for i in range(1, len(out) - 1):
        if out[i]["key"] == out[i - 1]["key"]:
            out[i], out[i + 1] = out[i + 1], out[i]
    return out


def gap_sentences(words, stored, tatoeba_rows=None, per_word=3):
    """{form: [{malay, english}]}: the learner's stored sentences first,
    then Tatoeba. stored: {form: [{malay, english}]} from the database."""
    if tatoeba_rows is None:
        try:
            import tatoeba
            tatoeba_rows = tatoeba.pairs()
        except Exception:
            tatoeba_rows = []
    out = {}
    for w in words:
        form = w["malay"]
        got = [s for s in stored.get(form, []) if wc.contains(s.get("malay", ""), form)]
        if len(got) < per_word:
            extra = [r for r in tatoeba_rows if wc.contains(r["malay"], form)]
            extra.sort(key=lambda r: len(r["malay"]))
            got += [{"malay": r["malay"], "english": r["english"]} for r in extra]
        out[form] = got[:per_word]
    return out


def family_result(results):
    """All right -> correct; at least half -> close; else wrong."""
    if not results:
        return "ungraded"
    share = sum(results) / len(results)
    return "correct" if share == 1 else "close" if share >= 0.5 else "wrong"
