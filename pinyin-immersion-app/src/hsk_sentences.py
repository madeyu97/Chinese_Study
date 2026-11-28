# src/hsk_sentences.py
"""
Sentence writing (HSK track): write whole sentences by hand, from their
English and pinyin.

The sentences are the official HSK 1-4 grammar examples (866 of them). You
write the characters you've learnt to write; any others are filled in for
you. A sentence qualifies when at least 60% of its characters are yours to
write, so it's mostly your writing, never a page of gaps.

It grows with your writing: how many characters a sentence asks of you
depends on how many you can write (TIERS) - two to five at first, seven
to fourteen once you can write 200. Within that, the sentences you got
wrong come back first, then ones due again, then new ones
(games_hsk.prioritise, results in game_seen under "sentence").

"Can write" = a character written at least twice and not back in learning
after a break (db.handwriting_writable).
"""

import functools
import re

import hsk

# (writable characters below this, (fewest, most) characters to write)
TIERS = ((40, (2, 5)), (100, (3, 7)), (200, (5, 10)), (10 ** 9, (7, 14)))
MIN_WRITABLE = 20          # sentences start once you can write this many
MIN_SHARE = 0.6            # of a sentence's characters, yours to write
FAMILY = "sentence"        # game_seen family


def _cjk(text):
    return [c for c in text if "一" <= c <= "鿿"]


@functools.lru_cache(maxsize=1)
def pool():
    """The official example sentences: [{"zh", "en", "py", "level", "chars"}]."""
    from dictionary_engine import has_erhua
    out, seen = [], set()
    for level in hsk.LEVELS:
        for p in hsk.grammar_points(level):
            for ex in p["examples"]:
                zh = re.sub(r"（[^）]*）", "", ex["chinese"]).strip()
                chars = _cjk(zh)
                if (not ex["english"] or zh in seen or has_erhua(zh)
                        or not re.search(r"[。？！]$", zh) or re.search(r"[A-Za-z0-9]", zh)
                        or not 3 <= len(chars) <= 20):
                    continue
                seen.add(zh)
                py = ex.get("pinyin") if zh == ex["chinese"] else ""
                if not py:
                    from pinyin_hsk import sentence_pinyin
                    py = sentence_pinyin(zh)
                out.append({"zh": zh, "en": ex["english"], "py": py, "level": level,
                            "chars": chars})
    return out


def tier(n_writable):
    return next(t for below, t in TIERS if n_writable < below)


def to_write(sentence, writable):
    """Indexes (among the sentence's characters) you write; the rest are given."""
    return [i for i, c in enumerate(sentence["chars"]) if c in writable]


def candidates(writable):
    """Sentences at your tier, fewest characters to write first. Too few at
    the tier (early on) and any sentence from two characters up to the
    tier's top will do."""
    lo, hi = tier(len(writable))

    def fits(s, lo_):
        n = len(to_write(s, writable))
        return lo_ <= n <= hi and n / len(s["chars"]) >= MIN_SHARE

    out = [s for s in pool() if fits(s, lo)]
    if len(out) < 5:
        out = [s for s in pool() if fits(s, 2)]
    out.sort(key=lambda s: (len(to_write(s, writable)), s["level"]))
    return out


def pick(writable, n=2, seen=None, today=None, rng=None):
    """n sentences for a session: missed ones first, then due, then new."""
    import games_hsk as gh
    if len(writable) < MIN_WRITABLE:
        return []
    by = {s["zh"]: s for s in candidates(writable)}
    return [by[k] for k in gh.prioritise(list(by), seen, today, n, rng=rng)[:n]]


def outcome(results):
    """A sentence is right when every character was written without a reveal
    and graded Good or Easy."""
    return bool(results) and all(int(r["grade"]) >= 2 and not r.get("revealed") for r in results)
