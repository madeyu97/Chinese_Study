# src/tatoeba.py
"""
Human-written Malay sentences from Tatoeba (data/tatoeba_ms_en.tsv, built by
tools/build_tatoeba.py; CC BY 2.0 FR, each with its Tatoeba id and author).

Listen & speak takes a word's sentence from here before asking a model to
write one. The sentence itself is never changed; the reviewer still checks
the English translation (Tatoeba has some loose ones), and only the
wrong-answer options are written by the model.
"""

import csv
from functools import lru_cache
from pathlib import Path

import ai_prompter as ap
import word_content as wc
from malay import normalise

PATH = Path(__file__).resolve().parent.parent / "data" / "tatoeba_ms_en.tsv"


@lru_cache(maxsize=1)
def pairs():
    if not PATH.exists():
        return []
    with PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def matches(word, blocked=(), limit=6):
    """Sentences containing the word, shortest and most everyday first."""
    target = word["malay"]
    blocked = set(blocked)
    found = [r for r in pairs() if r["malay"] not in blocked and wc.contains(r["malay"], target)]
    found.sort(key=lambda r: (len(ap.off_list(r["malay"])), len(normalise.tokens(r["malay"]))))
    return found[:limit]


def make_exercise(row, word, flagged_examples=None):
    """A listening exercise from a Tatoeba pair, or None if the reviewer
    rejects the translation or the model can't supply options."""
    malay, english = row["malay"], row["english"]
    verdict = ap.review_sentence(malay, english, flagged_examples)
    if not verdict["acceptable"]:
        return None
    distractors = ap.generate_distractors_for(malay, english)
    if len(distractors) < 2:
        return None
    return {"malay": malay, "english_correct": english, "english_distractors": distractors,
            "grammar_note": "", "target": word["malay"], "generation_mode": "listen",
            "source": "tatoeba", "tatoeba_id": row.get("tatoeba_id"), "author": row.get("author")}


def exercise_for(word, blocked=(), flagged_examples=None, tries=3):
    """The first Tatoeba sentence for the word that passes, or None."""
    for row in matches(word, blocked, limit=tries):
        ex = make_exercise(row, word, flagged_examples)
        if ex:
            return ex
    return None
