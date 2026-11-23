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
import json
import re
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
                     "pos": r["pos"], "english": r["english"], "erhua": r["erhua"] == "1",
                     "measure": [m for m in r.get("measure", "").split("、") if m]})
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
def write_order():
    """The 400 characters to write in teaching order: band 2 (HSK 1-2), then
    3, then 4; within a band, parts before the characters built from them
    (女 before 好), commonest first. Each: char, band, order, strokes, the HSK
    word that cues it (cue_word / cue_pinyin / cue_english) and builds_on,
    the earlier characters it is made from."""
    return [{"char": r["char"], "band": int(r["band"]), "order": int(r["order"]),
             "strokes": int(r["strokes"]) if r["strokes"] else None,
             "cue_word": r["cue_word"], "cue_pinyin": r["cue_pinyin"],
             "cue_english": r["cue_english"], "builds_on": r["builds_on"]}
            for r in _read("write_order.csv")]


@functools.lru_cache(maxsize=1)
def _write_info():
    return {r["char"]: r for r in write_order()}


def write_info(ch):
    return _write_info().get(ch)


BAND_NAMES = {2: "HSK 1–2", 3: "HSK 3", 4: "HSK 4"}


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


def known_words(username, hsk_levels):
    """The words grammar drills may build from, on top of words studied in
    the app. On the HSK track vocabulary is learnt in Anki, not here, so it
    is the syllabus: every HSK word up to the level studied by ear (HSK 1
    until a level is set). Off the track: none."""
    from config import HSK_TRACK_USERS
    if not username or username.lower() not in HSK_TRACK_USERS:
        return []
    if isinstance(hsk_levels, str):
        hsk_levels = json.loads(hsk_levels)
    level = (hsk_levels or {}).get("listen") or 1
    return [w["word"] for w in words_upto(level) if re.fullmatch(r"[\u4e00-\u9fff]+", w["word"])]


def grammar_upto(hsk_levels):
    """The highest HSK level grammar drills go up to: the grammar level from
    the level test, or the listening level before grammar was tested
    (HSK 1 until anything is set)."""
    if isinstance(hsk_levels, str):
        hsk_levels = json.loads(hsk_levels)
    lv = hsk_levels or {}
    return lv.get("grammar") or lv.get("listen") or 1


@functools.lru_cache(maxsize=1)
def _lookalike():
    return {r["char"]: (int(r["level"]), r["similar"].split("、")) for r in _read("lookalike.csv")}


def lookalikes(ch):
    """Recognition characters easily taken for ch (请: 清 情 晴 ...), closest
    first; [] if none."""
    return list(_lookalike().get(ch, (0, []))[1])


def lookalike_chars(upto=4):
    """Characters up to a level that have at least three look-alikes."""
    return [c for c, (lv, sim) in _lookalike().items() if lv <= upto and len(sim) >= 3]
