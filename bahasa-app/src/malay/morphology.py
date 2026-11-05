"""Malay word analysis: root, prefixes, suffix, clitics.

Lookup order:
  1. overrides.csv  - hand fixes for words the rules get wrong
  2. the glossed word list (data/malay_words.csv) - root and affixes were
     written by hand for all 5,000 words
  3. rules - for anything else (lesson words, words in generated sentences)

The rules enumerate every way to peel the word (proclitic, up to two
prefixes with meN-/peN- sound changes undone, one suffix, enclitics) and
keep the reading whose root is best attested:
    a root on the glossed list  >  a word in the Malaya lexicon  >  nothing
then a valid prefix/suffix pairing, then the more frequent root.

Affix labels follow the gloss files: 'meN-', '-kan', 'meN-…-kan', '+nya',
'ke-…-an+nya', 'R' for reduplication.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WORDLIST = HERE.parent.parent / "data" / "malay_words.csv"

ENCLITICS = ("nyalah", "nyakah", "nyapun", "nya", "kulah", "mulah", "lah", "kah",
             "pun", "tah", "ku", "mu")
PROCLITICS = ("kau", "ku")
SUFFIXES = ("kan", "i", "an")
VOWELS = set("aeiou")

# prefix-set -> suffixes it combines with ('' = no suffix)
_CONFIX = {
    (): {"", "kan", "i", "an"},
    ("meN",): {"", "kan", "i"},
    ("di",): {"", "kan", "i"},
    ("ter",): {"", "kan", "i"},
    ("memper",): {"", "kan", "i"},
    ("diper",): {"", "kan", "i"},
    ("ber",): {"", "an", "kan"},
    ("ke",): {"", "an", "i"},
    ("peN",): {"", "an"},
    ("per",): {"", "an", "kan", "i"},
    ("se",): {"", "an"},
    ("ber", "ke"): {"an"},
    ("ber", "peN"): {"", "an"},
    ("ber", "se"): {""},
    ("ke", "se"): {"an"},
    ("per", "se"): {"an"},
    ("meN", "ber"): {"kan"},   # memberhentikan
    ("di", "ber"): {"kan"},    # diberhentikan
}
SHORT_ROOTS = {"ia"}
# parts of speech that do not take derivational affixes
_CLOSED = {"conjunction", "particle", "preposition", "pronoun", "determiner",
           "auxiliary", "question word", "interjection"}
_VERBAL = ("meN", "di", "ter", "memper", "diper")


@dataclass(frozen=True)
class Analysis:
    word: str
    root: str
    prefixes: tuple = ()
    suffix: str = ""
    clitics: tuple = ()          # enclitics in order, proclitic first if any
    reduplicated: bool = False
    source: str = "rules"        # override | list | rules | unknown

    @property
    def affix_label(self) -> str:
        return make_label(self.prefixes, self.suffix, self.clitics, self.reduplicated)

    @property
    def voice_key(self):
        """meN-, di- and the bare form of one root+suffix are one verb in
        two voices: makan / memakan / dimakan."""
        pre = tuple(p for p in self.prefixes if p not in ("meN", "di"))
        return (self.root, pre, self.suffix, self.reduplicated)


def make_label(prefixes=(), suffix="", clitics=(), reduplicated=False):
    pro = [c for c in clitics if c.endswith("=")]
    enc = [c for c in clitics if not c.endswith("=")]
    pre = "".join(f"{p}-" for p in prefixes)
    if pre and suffix:
        label = f"{pre}…-{suffix}"
    elif pre and suffix == "" and enc[:1] == ["nya"] and prefixes == ("se",):
        label, enc = "se-…-nya", enc[1:]
    else:
        label = pre + (f"-{suffix}" if suffix else "")
    if reduplicated:
        label = f"{label}+R" if label else "R"
    label += "".join(f"+{c}" for c in enc)
    label = "".join(f"{c[:-1]}+" for c in pro) + label
    return label


def parse_label(label):
    """'meN-…-kan+nya' -> (('meN',), 'kan', ('nya',), False)."""
    label = (label or "").replace(" ", "")
    redup = "+R" in label or label == "R"
    label = label.replace("+R", "").replace("R", "") if redup else label
    clitics = tuple(re.findall(r"\+([a-z]+)", label))
    core = re.sub(r"\+[a-z]+", "", label)
    if core == "se-…-nya":
        return ("se",), "", ("nya",) + clitics, redup
    if "…" in core:
        left, right = core.split("…", 1)
    elif core.startswith("-"):
        left, right = "", core
    else:
        left, right = core, ""
    prefixes = tuple(p for p in left.split("-") if p)
    suffix = right.strip("-")
    return prefixes, suffix, clitics, redup


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def lexicon():
    path = DATA / "lexicon.txt"
    return frozenset(path.read_text(encoding="utf-8").split()) if path.exists() else frozenset()


def _read_list(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Model:
    """Roots, ranks and known analyses. Built from the glossed list; the
    evaluation builds one from part of the list only."""

    def __init__(self, rows=(), overrides=()):
        self.known = {}      # word -> (root, label)
        self.roots = {}      # root -> best rank in its family
        self.pos = {}        # root word -> part of speech
        self.indo = set()    # roots that are Indonesian forms
        for i, r in enumerate(rows, 1):
            w = (r.get("malay") or "").strip().lower()
            if not w:
                continue
            rank = int(r["rank"]) if str(r.get("rank", "")).isdigit() else i
            root = (r.get("root") or "").strip().lower() or w
            label = (r.get("affixes") or "").replace(" ", "")
            self.known.setdefault(w, (root, label))
            if not label:
                self.pos.setdefault(w, (r.get("pos") or "").strip())
                if r.get("tag") == "Indonesian":
                    self.indo.add(w)
            for k in {root} | ({w} if not label else set()):
                if " " not in k:
                    self.roots[k] = min(self.roots.get(k, rank), rank)
        for r in overrides:
            w = r["word"].strip().lower()
            root = r["root"].strip().lower() or w
            self.known[w] = (root, (r.get("affixes") or "").replace(" ", ""))
            self.roots.setdefault(root, 99_999)
        self.lex = lexicon()

    def rank(self, root):
        return self.roots.get(root, 100_000)

    def tier(self, root):
        if len(root) < 3 and root not in SHORT_ROOTS:
            return 0
        if root in self.roots:
            return 2
        if root in self.lex:
            return 1
        return 0


@lru_cache(maxsize=1)
def default_model():
    over = _read_list(DATA / "overrides.csv")
    return Model(_read_list(WORDLIST), over)


# ----------------------------------------------------------------------
# Rules
# ----------------------------------------------------------------------
def _nasal(stem, pre):
    """Undo meN-/peN- (pre = 'me' or 'pe'). Yields root candidates."""
    if not stem.startswith(pre):
        return
    s = stem[len(pre):]
    if s.startswith("nge") and len(s) <= 7:          # mengecat, pengebom
        yield s[3:]
    if s.startswith("ny"):
        if s[2:3] in VOWELS:
            yield "s" + s[2:]                       # menyapu -> sapu
        yield s                                     # menyanyi -> nyanyi
    if s.startswith("ng"):
        r = s[2:]
        if r[:1] in VOWELS:
            yield r                                 # mengambil -> ambil
            yield "k" + r                           # mengira -> kira
            yield s                                 # mengerikan -> ngeri
        elif r[:1] in ("g", "h", "k"):
            yield r                                 # menggali, menghantar, mengkaji
    elif s.startswith("m"):
        r = s[1:]
        if r[:1] in VOWELS:
            yield "p" + r                           # memukul -> pukul
            yield "f" + r                           # memikirkan -> fikir
        elif r[:1] in ("b", "f", "v", "p"):
            yield r                                 # membawa, mempunyai
        if r[:1] == "m" or (r[:1] in VOWELS):
            yield s                                 # memasak? -> masak (via me + m)
    elif s.startswith("n"):
        r = s[1:]
        if r[:1] in VOWELS:
            yield "t" + r                           # menulis -> tulis
        elif r[:1] in ("c", "d", "j", "z", "t") or r.startswith("sy"):
            yield r                                 # mencari, menjual, mendengar
        if r[:1] == "n" or r[:1] in VOWELS:
            yield s                                 # menanti -> nanti
    if s[:1] in ("l", "r", "w", "y"):
        yield s                                     # melihat, merasa, mewah
    if pre == "pe" and s[:1] and s[:1] not in VOWELS and not s.startswith(("m", "n")):
        yield s                                     # pedagang, pekerja, pelukis


def _prefix_peels(w):
    """(prefix label, remainder) for one prefix layer."""
    out = []
    if w.startswith("memper"):
        out.append(("memper", w[6:]))
    if w.startswith("diper"):
        out.append(("diper", w[5:]))
    if w.startswith("me"):
        out += [("meN", r) for r in _nasal(w, "me")]
    if w.startswith("pe"):
        out += [("peN", r) for r in _nasal(w, "pe")]
        if w.startswith("per"):
            out.append(("per", w[3:]))
        if w.startswith("pel"):
            out.append(("peN", w[3:]))              # pelajar (pel + ajar)
    if w.startswith("ber"):
        out.append(("ber", w[3:]))
    if w.startswith("be") and len(w) > 4:
        out.append(("ber", w[2:]))                  # bekerja, berehat (be + rehat)
        if w.startswith("bel"):
            out.append(("ber", w[3:]))              # belajar
    if w.startswith("ter"):
        out.append(("ter", w[3:]))
    if w.startswith("te") and w[2:3] == "r":
        out.append(("ter", w[2:]))                  # terasa (ter + rasa)
    for p in ("di", "ke", "se"):
        if w.startswith(p):
            out.append((p, w[len(p):]))
    return [(p, r) for p, r in out if len(r) >= 2]


def _candidates(word):
    """Every (proclitic, prefixes, root, suffix, enclitics) reading."""
    seen = set()
    procs = [("", word)] + [(p, word[len(p):]) for p in PROCLITICS
                            if word.startswith(p) and len(word) - len(p) >= 3]
    for proc, w0 in procs:
        encs = [((), w0)]
        for e in ENCLITICS:
            if w0.endswith(e) and len(w0) - len(e) >= 3:
                parts = (e[:-3], e[-3:]) if len(e) > 3 and e[-3:] in ("lah", "kah", "pun") \
                    else (e,)
                encs.append((parts, w0[: -len(e)]))
        for enc, w1 in encs:
            sufs = [("", w1)] + [(s, w1[: -len(s)]) for s in SUFFIXES
                                 if w1.endswith(s) and len(w1) - len(s) >= 2]
            if w1.endswith("pan"):
                sufs.append(("an", w1[:-3] + "b"))    # jawapan <- jawab + -an
            for suf, w2 in sufs:
                layers = [((), w2)]
                for p1, r1 in _prefix_peels(w2):
                    layers.append(((p1,), r1))
                    if p1 in ("ber", "ke", "per", "meN", "di"):
                        for p2, r2 in _prefix_peels(r1):
                            if p2 in ("ke", "se", "peN", "per", "ber"):
                                layers.append(((p1, p2), r2))
                for pre, root in layers:
                    key = (proc, pre, root, suf, enc)
                    if key not in seen:
                        seen.add(key)
                        yield key


def _score(c, model, word):
    """Higher is better. In order: how well the root is attested, whether
    the prefixes and suffix go together, no affixes on a function word, a
    verb root under a verbal prefix, a single prefix layer, the root not
    being split off from a longer listed root (kes+an vs kesan), Malaysian
    over Indonesian roots, the more frequent root, then affix count."""
    proc, pre, root, suf, enc = c
    tier = model.tier(root)
    confix = suf in _CONFIX.get(pre, set())
    pos = model.pos.get(root, "")
    closed = bool(pre or suf) and pos in _CLOSED
    verbal = not (pre[:1] and pre[0] in _VERBAL and pos and pos != "verb")
    split = bool(suf) and (root + suf) in model.roots
    if suf == "an" and root.endswith("p") and model.tier(root[:-1] + "b") == 2:
        split = True                                 # jawapan -> jawab, not jawap
    n = len(pre) + bool(suf) + len(enc) + bool(proc)
    return (tier, confix, not closed, verbal, len(pre) < 2, not split,
            root not in model.indo, -model.rank(root),
            # the lexicon holds derived forms too, so among lexicon-only
            # roots the more fully peeled reading is the likelier root
            n if tier == 1 else -n)


def _rules(word, model):
    best, best_score = None, None
    for c in _candidates(word):
        s = _score(c, model, word)
        if best is None or s > best_score:
            best, best_score = c, s
    proc, pre, root, suf, enc = best
    if best_score[1] == 0:
        # nothing attested: report the word as its own root
        return Analysis(word, word, source="unknown")
    clitics = ((proc + "=",) if proc else ()) + tuple(enc)
    return Analysis(word, root, tuple(pre), suf, clitics, source="rules")


def _from_label(word, root, label, source):
    pre, suf, clitics, redup = parse_label(label)
    return Analysis(word, root, pre, suf, clitics, redup, source)


def analyse(word, model=None, use_list=True):
    """Analysis of one word. `use_list=False` skips the hand-glossed lookup
    (used to measure the rules on their own)."""
    model = model or default_model()
    w = (word or "").strip().lower()
    w = re.sub(r"(\w+)2$", r"\1-\1", w)               # kanak2 -> kanak-kanak
    if not w:
        return Analysis("", "", source="unknown")
    if use_list and w in model.known:
        root, label = model.known[w]
        return _from_label(w, root, label, "list")
    if "-" in w:
        return _reduplicated(w, model, use_list)
    if w in model.roots:
        return Analysis(w, w, source="list" if use_list else "rules")
    return _rules(w, model)


def _reduplicated(w, model, use_list):
    a, _, b = w.partition("-")
    left = analyse(a, model, use_list)
    right = analyse(b, model, use_list)
    if a == b:                                        # rumah-rumah, kanak-kanak
        return Analysis(w, left.root, left.prefixes, left.suffix, left.clitics, True,
                        left.source)
    if right.root == left.root or b == left.root or a == right.root:
        # bermain-main, tolong-menolong, sayur-sayuran
        rich = right if len(right.prefixes) + bool(right.suffix) > \
            len(left.prefixes) + bool(left.suffix) else left
        return Analysis(w, left.root if b == left.root else right.root, rich.prefixes,
                        rich.suffix, rich.clitics + left.clitics if rich is right else
                        rich.clitics, True, rich.source)
    return Analysis(w, w, source="unknown")           # a compound: treat as one root


def root_of(word):
    return analyse(word).root


def same_root(a, b):
    return bool(a and b) and root_of(a) == root_of(b)


# ----------------------------------------------------------------------
# Building words: root + affixes -> surface form
# ----------------------------------------------------------------------
# Standard forms the sound rules don't predict.
_IRREGULAR = {
    ("tahu", "meN"): "mengetahu", ("tahu", "peN"): "pengetahu", ("tahu", "di"): "diketahu",
    ("kaji", "meN"): "mengkaji", ("kaji", "peN"): "pengkaji",
    ("fikir", "meN"): "memikir", ("fikir", "peN"): "pemikir",
    ("faham", "meN"): "memaham", ("faham", "peN"): "pemaham",
    ("percaya", "meN"): "mempercaya", ("pengaruh", "meN"): "mempengaruh",
    ("ajar", "memper"): "mempelajar", ("ajar", "per"): "pelajar",
    ("punya", "meN"): "mempunya",
}


def _monosyllable(root):
    return len(re.findall(r"[aeiou]", root)) == 1


def _nasal_form(root, pre):
    """meN- / peN- (pre = 'me' / 'pe') joined to a root, with the sound
    changes: tulis -> menulis, pukul -> memukul, sapu -> menyapu,
    kira -> mengira, cat -> mengecat."""
    r0, r1 = root[:1], root[1:2]
    cluster = bool(r1) and r1 not in VOWELS
    if _monosyllable(root):
        return pre + "nge" + root
    if r0 in VOWELS or r0 in ("g", "h") or root.startswith("kh"):
        return pre + "ng" + root
    if r0 == "k":
        return pre + "ng" + (root if cluster else root[1:])
    if r0 in ("b", "f", "v"):
        return pre + "m" + root
    if r0 == "p":
        return pre + "m" + (root if cluster else root[1:])
    if root.startswith("sy") or r0 in ("c", "d", "j", "z"):
        return pre + "n" + root
    if r0 == "t":
        return pre + "n" + (root if cluster else root[1:])
    if r0 == "s":
        return pre + "ny" + (root if cluster else root[1:])
    return pre + root                                  # l m n r w y ng ny


def _prefix_form(root, p):
    if (root, p) in _IRREGULAR:
        return _IRREGULAR[(root, p)]
    if p == "meN":
        return _nasal_form(root, "me")
    if p == "peN":
        return _nasal_form(root, "pe")
    if p == "ber":
        if root == "ajar":
            return "belajar"
        if root.startswith("r") or re.match(r"[^aeiou]er[^aeiou]", root):
            return "be" + root                         # berehat, bekerja
        return "ber" + root
    if p in ("ter", "per"):
        return (p[:2] if root.startswith("r") else p) + root
    if p == "memper":
        return ("mempe" if root.startswith("r") else "memper") + root
    if p == "diper":
        return ("dipe" if root.startswith("r") else "diper") + root
    return p + root                                    # di ke se pe be


def attach(root, prefixes=(), suffix="", clitics=()):
    """Surface form of root + affixes. Prefixes are listed outermost first,
    as in the labels ('meN-ber-…-kan' = meN- on berhenti)."""
    w = root
    if suffix == "an" and w in ("jawab", "sebab"):
        w = w[:-1] + "p"                               # jawapan
    for p in reversed(tuple(prefixes)):
        w = _prefix_form(w, p)
    w += suffix
    pro = [c[:-1] for c in clitics if c.endswith("=")]
    enc = [c for c in clitics if not c.endswith("=")]
    return "".join(pro) + w + "".join(enc)


def build(root, label):
    """attach() from a label string: build('ajar', 'meN-…-kan') -> 'mengajarkan'."""
    pre, suf, clitics, _redup = parse_label(label)
    return attach(root, pre, suf, clitics)
