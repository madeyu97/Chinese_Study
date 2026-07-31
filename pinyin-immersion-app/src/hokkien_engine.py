"""
Penang Hokkien romanisation engine.

Handles Tâi-lô parsing and conversion to Taiji (Timothy Tye's Penang
romanisation, which uses tone numbers instead of diacritics).

IMPORTANT HONESTY NOTE ON PROVENANCE
------------------------------------
There is no open, machine-readable Penang Hokkien lexicon. This app's deck
is built from Taiwanese Hokkien sources (ChhoeTaigi, CC-licensed) with a
Penang overlay from English Wiktionary (CC BY-SA) where Penang-tagged
readings exist. Consequently:

  * Entries tagged 'penang' carry a genuine Penang-specific reading.
  * Entries tagged 'hokkien' are Taiwanese-Hokkien readings that may or may
    not match Penang usage (e.g. Taiwan 市場 tshī-tiûnn vs Penang 巴剎 pa-sat).
  * Taiji output is DERIVED from Tâi-lô by tone-class mapping. The tone
    mapping is well documented; the orthographic letter choices are only
    partly documented, so Taiji spellings are approximations.

Nothing is presented to the learner as authoritative until they verify it.
"""

import re
import unicodedata

# ======================================================================
# TÂI-LÔ TONE CLASSES
# Diacritic -> tone number (traditional Hokkien tone class numbering)
#   1 = no mark, open syllable        (a)
#   2 = acute                          (á)
#   3 = grave                          (à)
#   4 = no mark, checked (-p/-t/-k/-h) (ah)
#   5 = circumflex                     (â)
#   7 = macron                         (ā)
#   8 = vertical line, checked         (a̍h)
# ======================================================================
COMBINING = {
    "\u0301": 2,   # ́  acute
    "\u0300": 3,   # ̀  grave
    "\u0302": 5,   # ̂  circumflex
    "\u0304": 7,   # ̄  macron
    "\u030D": 8,   # ̍  vertical line above
    "\u0306": 6,   # ̆  breve (rare: Longyan, Zhangzhou tone 6)
    "\u030B": 9,   # ̋  double acute — Tâi-lô tone 9 (high level, loanwords
                   #    and certain tone-change forms, e.g. tsha̋i)
}

CHECKED_ENDINGS = ("p", "t", "k", "h")


def _decompose(text):
    return unicodedata.normalize("NFD", text)


def _recompose(text):
    return unicodedata.normalize("NFC", text)


def strip_tone_marks(syllable):
    """'tsia̍h' -> 'tsiah', 'pn̄g' -> 'png'."""
    d = _decompose(syllable)
    return _recompose("".join(c for c in d if c not in COMBINING))


def tone_of(syllable):
    """Return the Tâi-lô tone class (1-8) of a single syllable."""
    d = _decompose(syllable)
    marked = [COMBINING[c] for c in d if c in COMBINING]
    bare = strip_tone_marks(syllable).lower()
    checked = bare.endswith(CHECKED_ENDINGS)
    if marked:
        tone = marked[0]
        # A vertical mark on a checked syllable is tone 8; on an open
        # syllable Tâi-lô doesn't use it, so fall through unchanged.
        return tone
    return 4 if checked else 1


def split_syllables(tailo_word):
    """'tsia̍h-pn̄g' -> ['tsia̍h', 'pn̄g']. Handles - and space separators."""
    if not tailo_word:
        return []
    # '--' marks a following neutral-tone syllable in Tâi-lô (lōo--lí);
    # treat it as a plain separator.
    parts = re.split(r"[-\s]+", tailo_word.strip().replace("--", "-"))
    return [p for p in parts if p]


# ======================================================================
# TÂI-LÔ  ->  TAIJI
# Tone mapping per Timothy Tye, "Transliterating Taiwanese Romanisation to
# Taiji for Penang Hokkien" (penang-traveltips.com). Tâi-lô's 7 classes
# collapse into Taiji's 4 (plus the 33 mid-level marker).
#
#   Tâi-lô 1 (open, unmarked)   -> 1
#   Tâi-lô 2 (acute á)          -> 4
#   Tâi-lô 3 (grave à)          -> 3
#   Tâi-lô 4 (checked, unmarked)-> 3     [see note below]
#   Tâi-lô 5 (circumflex â)     -> 2
#   Tâi-lô 7 (macron ā)         -> 33
#   Tâi-lô 8 (checked, vertical)-> 1
#
# NOTE on Tâi-lô 4: Tye's rule text states tone 3, while the two worked
# examples in the same paragraph print tone 1. Tone 3 is adopted here
# because it is what the rule says and because it is phonetically coherent
# — Penang's checked tone 4 is low (21), matching Taiji 3's low value,
# while checked tone 8 is high, matching Taiji 1. Mapping both 4 and 8 to 1
# would erase a distinction Penang Hokkien actually makes. Flagged in the
# UI as an approximation regardless.
# ======================================================================
TAILO_TO_TAIJI_TONE = {
    9: "1",   # tone 9 is high-level; Taiji's tone 1 is its nearest match
    1: "1",
    2: "4",
    3: "3",
    4: "3",
    5: "2",
    7: "33",
    8: "1",
    6: "4",   # rare; treated as tone 2's neighbour
}

# Documented orthographic substitutions (applied longest-first).
# Taiji deliberately avoids spellings that mislead readers who don't know
# Tâi-lô conventions.
TAIJI_SPELLING = [
    ("tsh", "ch"),
    ("ts", "c"),
    ("nn", "n"),     # nasalisation written differently in Taiji
    ("oo", "o"),
]


def _to_taiji_syllable(syllable):
    tone = tone_of(syllable)
    bare = strip_tone_marks(syllable).lower()
    for src, dst in TAIJI_SPELLING:
        bare = bare.replace(src, dst)
    # Taiji writes final -h of checked syllables as -k where Tâi-lô uses -h
    # (bah -> bak). Other finals are kept.
    if bare.endswith("h") and not bare.endswith("nh"):
        bare = bare[:-1] + "k"
    return f"{bare}{TAILO_TO_TAIJI_TONE.get(tone, '1')}"


def tailo_to_taiji(tailo_word):
    """Convert a Tâi-lô word/phrase to approximate Taiji romanisation.

    'tsia̍h-pn̄g' -> 'ciak1 png33'
    Returns "" for empty input. Never raises on odd input.
    """
    if not tailo_word:
        return ""
    try:
        return " ".join(_to_taiji_syllable(s) for s in split_syllables(tailo_word))
    except Exception:
        return ""


def tone_profile(tailo_word):
    """List of Tâi-lô tone classes, for display/drilling ('tsia̍h-pn̄g' -> [8, 7])."""
    return [tone_of(s) for s in split_syllables(tailo_word)]


# ======================================================================
# NORMALISATION HELPERS
# ======================================================================
def normalise_tailo(text):
    """Tidy a Tâi-lô string: strip stray marks, unify separators, NFC."""
    if not text:
        return ""
    text = text.strip().replace("　", " ")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    return _recompose(text)


def answers_match(user_input, expected_tailo, ignore_tones=True):
    """Compare a learner's typed romanisation with the expected Tâi-lô.

    Tone diacritics are hard to type on a phone, so by default tones are
    ignored and only the segmental spelling must match. Hyphens, spaces and
    case are always ignored.
    """
    def norm(s):
        s = (s or "").strip().lower()
        s = re.sub(r"[-\s]+", "", s)
        if ignore_tones:
            s = strip_tone_marks(s)
            s = re.sub(r"\d+", "", s)   # allow numeric-tone typing too
        return s
    return norm(user_input) == norm(expected_tailo)
