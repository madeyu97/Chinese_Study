"""Text normalisation for comparing Malay answers.

  tokens(text)        lower-case word tokens, '2' reduplication expanded
  canonical(text)     tokens with colloquial, abbreviated and synonym forms
                      mapped to one standard form: 'tak nak' -> 'tidak hendak'
  same(a, b)          two answers equal up to register
  standard_of(word)   'tak' -> 'tidak' (None if the word is already standard)
  malaysian_for(w)    Indonesian form -> its Malaysian words ('bisa' -> ['boleh'])
  clean_transcript(t) Whisper output made comparable: punctuation, digits,
                      joined 'disini' / 'kemana' split
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
WORDLIST = Path(__file__).resolve().parent.parent.parent / "data" / "malay_words.csv"

# di / ke + one of these is a preposition phrase, never a prefixed verb
PLACES = set("""sini sana situ mana atas bawah dalam luar depan hadapan belakang tepi
sebelah antara tengah tepi rumah sekolah pejabat hospital klinik kedai bilik dapur
tandas pasar bandar kampung kereta bas sana-sini""".split())


def _read(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _colloquial():
    """Multi-word forms first so 'tak ada' wins over 'tak'."""
    rows = [(r["form"].strip(), r["standard"].strip(), r["kind"].strip())
            for r in _read(DATA / "colloquial.csv")]
    return sorted(rows, key=lambda r: -len(r[0].split()))


@lru_cache(maxsize=1)
def _single():
    return {f: s for f, s, _k in _colloquial() if " " not in f}


@lru_cache(maxsize=1)
def _indonesian():
    out = {}
    for r in _read(DATA / "indonesian.csv"):
        out[r["indonesian"].strip()] = [m.strip() for m in r["malaysian"].split("/") if m.strip()]
    return out


@lru_cache(maxsize=1)
def _list_words():
    return {r["malay"]: r for r in _read(WORDLIST)}


# ----------------------------------------------------------------------
def tokens(text):
    text = (text or "").lower().replace("’", "'")
    text = re.sub(r"\b([a-z]+)2\b", r"\1-\1", text)          # budak2 -> budak-budak
    return re.findall(r"[a-z]+(?:-[a-z]+)*", text)


def canonical(text):
    """Token list with every equivalent form replaced by its standard one.
    Applied twice so chains settle ('ko' -> 'engkau', 'xde' -> 'tiada')."""
    toks = tokens(text)
    for _ in range(2):
        toks = _replace_phrases(toks)
    return toks


def _replace_phrases(toks):
    rules = _colloquial()
    out, i = [], 0
    while i < len(toks):
        for form, std, _kind in rules:
            f = form.split()
            if toks[i:i + len(f)] == f:
                out.extend(std.split())
                i += len(f)
                break
        else:
            out.append(toks[i])
            i += 1
    return out


def same(a, b):
    return canonical(a) == canonical(b)


def standard_of(word):
    return _single().get((word or "").lower())


def is_colloquial(word):
    return (word or "").lower() in _single()


def malaysian_for(word):
    return _indonesian().get((word or "").lower(), [])


def is_indonesian(word):
    return (word or "").lower() in _indonesian()


# ----------------------------------------------------------------------
_ONES = ["kosong", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "lapan", "sembilan"]


def number_words(n):
    """0..999999 in Malay words: 21 -> 'dua puluh satu'."""
    n = int(n)
    if n < 10:
        return _ONES[n]
    if n == 10:
        return "sepuluh"
    if n == 11:
        return "sebelas"
    if n < 20:
        return f"{_ONES[n - 10]} belas"
    if n < 100:
        tens, ones = divmod(n, 10)
        return f"{_ONES[tens]} puluh" + (f" {_ONES[ones]}" if ones else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        head = "seratus" if h == 1 else f"{_ONES[h]} ratus"
        return head + (f" {number_words(rest)}" if rest else "")
    if n < 1_000_000:
        t, rest = divmod(n, 1000)
        head = "seribu" if t == 1 else f"{number_words(t)} ribu"
        return head + (f" {number_words(rest)}" if rest else "")
    return str(n)


def split_joined(word):
    """'disini' -> 'di sini', 'kerumah' -> 'ke rumah'; a real prefixed word
    ('dimakan', 'keluar') is left alone."""
    w = word.lower()
    for p in ("di", "ke"):
        if not w.startswith(p) or len(w) <= len(p) + 2:
            continue
        rest = w[len(p):]
        listed = _list_words()
        if w in listed:                      # keluar, ketepi: real words
            continue
        if rest in PLACES:
            return f"{p} {rest}"
        info = listed.get(rest)
        if info and info.get("pos") == "noun":
            from malay.morphology import lexicon
            if w not in lexicon():
                return f"{p} {rest}"
    return word


def clean_transcript(text):
    """Make a Whisper transcript comparable with the expected sentence."""
    text = (text or "").lower()
    text = re.sub(r"\d+", lambda m: f" {number_words(m.group(0))} ", text)
    out = []
    for tok in tokens(text):
        out.extend(split_joined(tok).split())
    return " ".join(out)


# ----------------------------------------------------------------------
# Register pairs and Indonesian forms, for display and for checking
# generated text
# ----------------------------------------------------------------------
def colloquial_forms(word):
    """Colloquial spellings whose standard form is `word`: tidak -> [tak]."""
    w = (word or "").lower()
    return [f for f, s, kind in _colloquial()
            if s == w and " " not in f and kind == "colloquial"]


def register_pair(word, register=None):
    """One line pairing a word with its other register, or ''."""
    w = (word or "").lower()
    std = standard_of(w)
    if std and std != w:
        return f"colloquial · standard form: {std}"
    coll = colloquial_forms(w)
    if coll:
        return "in speech: " + ", ".join(coll)
    return ""


# Forms on the Indonesian list that are also everyday Malaysian words in
# some sense: a generated sentence may use them (the known-word check and
# the reviewer still apply).
SHARED_WITH_MALAYSIAN = set("""
atap badai desa detik dingin enak gedung khusus kirim lingkungan pemerintah pintar
sukses taruh ternyata ukuran korban ruangan tanggal rencana pohon polisi haus
sulit kode mulai kelompok
""".split())


def indonesian_in(text, allow=()):
    """Indonesian forms in a Malay sentence, as (form, Malaysian word).
    `allow` lists forms the sentence may contain (its own target)."""
    allow = {a.lower() for a in allow}
    found = []
    for tok in tokens(text):
        if tok in allow or tok in SHARED_WITH_MALAYSIAN:
            continue
        mal = malaysian_for(tok)
        if not mal:
            for clitic in ("nya", "lah", "kah", "ku", "mu"):
                if tok.endswith(clitic) and malaysian_for(tok[: -len(clitic)]):
                    mal = malaysian_for(tok[: -len(clitic)])
                    break
        if mal:
            found.append((tok, " / ".join(mal)))
    return found


@lru_cache(maxsize=1)
def _false_friends():
    return {r["malay"]: r["indonesian_meaning"] for r in _read(DATA / "false_friends.csv")}


def false_friend(word):
    """The meaning a Malaysian word has in Indonesian, if it misleads:
    senang -> 'happy' (Malaysian: easy)."""
    return _false_friends().get((word or "").lower())


# ----------------------------------------------------------------------
# Numbers written as words, for checking a sentence against its English
# ----------------------------------------------------------------------
_UNITS = {w: n for n, w in enumerate(_ONES)}
_UNITS.pop("kosong")
_WHOLE = {"sepuluh": 10, "sebelas": 11, "seratus": 100}
_BIG = {"ribu": 1000, "juta": 1_000_000}
_SE_BIG = {"seribu": 1000, "sejuta": 1_000_000}


def numbers_in(text):
    """The numbers a Malay sentence states in words or digits:
    'dua puluh satu orang dan seratus lima' -> {21, 105}."""
    found, total, chunk, unit, active = set(), 0, 0, 0, False

    def flush():
        nonlocal total, chunk, unit, active
        if active:
            found.add(total + chunk + unit)
        total = chunk = unit = 0
        active = False

    for tok in re.findall(r"[a-z]+|\d+", (text or "").lower()):
        if tok.isdigit():
            flush()
            found.add(int(tok))
        elif tok in _UNITS:
            if unit:
                flush()
            unit, active = _UNITS[tok], True
        elif tok in _WHOLE and (not active or unit == 0):
            chunk, active = chunk + _WHOLE[tok], True
        elif tok in _SE_BIG:
            total, active = total + _SE_BIG[tok], True
        elif active and tok == "belas":
            chunk, unit = chunk + 10 + unit, 0
        elif active and tok == "puluh":
            chunk, unit = chunk + 10 * unit, 0
        elif active and tok == "ratus":
            chunk, unit = chunk + 100 * unit, 0
        elif active and tok in _BIG:
            total, chunk, unit = total + (chunk + unit or 1) * _BIG[tok], 0, 0
        else:
            flush()
    flush()
    return found
