# src/hsk.py
"""
The HSK 1-4 syllabus (2025): words, characters to recognise and to write,
grammar points. Read-only data from data/hsk/ (see SOURCES.md there).

    hsk.words(3)            new words at HSK 3
    hsk.words_upto(3)       every word for HSK 1-3
    hsk.level_of("学校")     1
    hsk.write_chars()       the 400 characters to write, band by band
    hsk.grammar_points(2)   HSK 2's grammar points, with examples

Levels are 1-4. Writing comes in three bands: 2 (the syllabus lists
HSK 1 and 2 together), 3 and 4.
"""

import csv
import functools
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "hsk"
LEVELS = (1, 2, 3, 4)
WRITE_BANDS = (2, 3, 4)


def _read(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@functools.lru_cache(maxsize=1)
def _words():
    rows = []
    for r in _read("words.csv"):
        rows.append({"word": r["word"], "level": int(r["level"]), "pinyin": r["pinyin"],
                     "pos": r["pos"], "english": r["english"], "erhua": r["erhua"] == "1"})
    return rows


@functools.lru_cache(maxsize=1)
def _by_word():
    return {r["word"]: r for r in _words()}


def words(level, include_erhua=False):
    return [r for r in _words() if r["level"] == level and (include_erhua or not r["erhua"])]


def words_upto(level, include_erhua=False):
    return [r for r in _words() if r["level"] <= level and (include_erhua or not r["erhua"])]


def word(w):
    return _by_word().get(w)


def level_of(w):
    r = _by_word().get(w)
    return r["level"] if r else None


@functools.lru_cache(maxsize=1)
def _recognise():
    return [(r["char"], int(r["level"])) for r in _read("recognise.csv")]


def recognise_chars(upto=4):
    return [c for c, lv in _recognise() if lv <= upto]


def char_level(ch):
    return next((lv for c, lv in _recognise() if c == ch), None)


@functools.lru_cache(maxsize=1)
def _write():
    return [(r["char"], int(r["band"])) for r in _read("write.csv")]


def write_chars(upto=4):
    """The characters to write by hand, band 2 (HSK 1-2) then 3 then 4,
    in the syllabus's order within each band."""
    return [c for c, band in _write() if band <= upto]


def write_band(ch):
    return next((b for c, b in _write() if c == ch), None)


@functools.lru_cache(maxsize=1)
def _grammar():
    examples = {}
    for r in _read("grammar_examples.csv"):
        examples.setdefault(r["grammar_id"], []).append(
            {"chinese": r["chinese"], "english": r["english"]})
    return [{"id": r["id"], "level": int(r["level"]), "point": r["point"], "type": r["type"],
             "category": r["category"], "detail": r["detail"],
             "examples": examples.get(r["id"], [])} for r in _read("grammar.csv")]


def grammar_points(level=None):
    return [g for g in _grammar() if level is None or g["level"] == level]


def counts():
    """Syllabus sizes, for progress bars."""
    return {"words": {lv: len(words(lv, include_erhua=True)) for lv in LEVELS},
            "recognise": {lv: sum(1 for _c, l in _recognise() if l == lv) for lv in LEVELS},
            "write": {b: sum(1 for _c, x in _write() if x == b) for b in WRITE_BANDS},
            "grammar": {lv: len(grammar_points(lv)) for lv in LEVELS}}
