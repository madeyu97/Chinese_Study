# src/games.py
"""
Picture games for tired days: quick, low-effort, still linking words to
meaning through images rather than English.

  picture  see the picture, pick the word
  word     see the word, pick the picture
  listen   hear the word, pick the picture
  memory   turn over cards to match each picture with its word

Wrong options come from the same topic where possible (shoulder vs elbow, not
shoulder vs banana), so a round still takes a moment's thought.
"""

import random

import game_items as gi

GAMES = {
    "picture": ("🖼️", "Picture → word", "See the picture, pick the word."),
    "word": ("🔤", "Word → picture", "Read the word, pick the picture."),
    "listen": ("🎧", "Listen → picture", "Hear the word, pick the picture."),
    "memory": ("🃏", "Memory match", "Turn over two cards at a time; match each picture to its word."),
}
ROUNDS = 10
MEMORY_PAIRS = 6
MIN_POOL = 8


def label(item, show_pinyin):
    return f"{item['chinese']}  {item['pinyin']}" if show_pinyin else item["chinese"]


def word_pool(categories, met=None, only_met=False):
    """Items for the chosen topics. With only_met, words the learner has
    already met - topped up with new ones if there are too few to play.
    Returns (items, topped_up)."""
    items = gi.by_category(categories)
    if not only_met or met is None:
        return items, False
    known = [i for i in items if i["chinese"] in met]
    if len(known) >= MIN_POOL:
        return known, False
    extra = [i for i in items if i["chinese"] not in met]
    return known + extra[:MIN_POOL - len(known)], True


def distractors(target, pool, n=3, rng=None):
    """n other items, same topic first, all with different words, pictures
    and meanings."""
    rng = rng or random.Random()
    same = [i for i in pool if i["category"] == target["category"]]
    other = [i for i in pool if i["category"] != target["category"]]
    rng.shuffle(same)
    rng.shuffle(other)
    out, seen = [], {(target["chinese"]), target["image"], target["english"]}
    for i in same + other:
        if len(out) == n:
            break
        if i["chinese"] in seen or i["image"] in seen or i["english"] in seen:
            continue
        seen.update({i["chinese"], i["image"], i["english"]})
        out.append(i)
    return out


def quiz_rounds(pool, n=ROUNDS, rng=None):
    rng = rng or random.Random()
    targets = rng.sample(pool, min(n, len(pool)))
    rounds = []
    for t in targets:
        options = distractors(t, pool, 3, rng) + [t]
        rng.shuffle(options)
        rounds.append({"target": t, "options": options})
    return rounds


def memory_board(pool, pairs=MEMORY_PAIRS, rng=None):
    rng = rng or random.Random()
    chosen, images = [], set()
    for i in rng.sample(pool, len(pool)):
        if i["image"] not in images:
            chosen.append(i)
            images.add(i["image"])
        if len(chosen) == pairs:
            break
    cards = [{"item": i, "face": f} for i in chosen for f in ("image", "word")]
    rng.shuffle(cards)
    return cards


def is_match(a, b):
    return a["item"]["chinese"] == b["item"]["chinese"] and a["face"] != b["face"]


def accept_matches(cards, reported, already=()):
    """The board reports which cards are matched; keep only real pairs (a
    picture and its word) on top of those already accepted."""
    ok = set(already)
    by_word = {}
    for n in set(reported or []):
        if isinstance(n, int) and 0 <= n < len(cards):
            by_word.setdefault(cards[n]["item"]["chinese"], []).append(n)
    for ns in by_word.values():
        if len(ns) == 2 and is_match(cards[ns[0]], cards[ns[1]]):
            ok.update(ns)
    return ok


def points(correct, streak):
    """10 a hit, plus a streak bonus up to +10."""
    return 10 + 2 * min(streak, 5) if correct else 0


def memory_score(pairs, moves):
    """100 for a perfect game (one move per pair), less for extra turns."""
    return max(10, 100 - (moves - pairs) * 6)
