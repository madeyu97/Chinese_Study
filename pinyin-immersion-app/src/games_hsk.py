# src/games_hsk.py
"""
Play on the HSK track: quick games over the HSK 1-4 syllabus, each aimed at
something Anki and the study pages don't cover.

  listen     hear a word, tap its characters - the other options sound
             close (shì / shí / sì), so the ear has to separate them
  meaning    see a word in characters, tap its meaning
  lookalike  ＿天 jīn tiān 'today': 今 or 令 or 会? characters that look
             nearly the same
  measure    一＿书 'a book': 本, not 张 or 条
  scramble   an official HSK example sentence, its words shuffled
  memory     turn over cards, match characters to meanings

Words come from the syllabus up to the level the level test set: listening
games by the listening level, the rest by reading, the scramble by grammar.

The herb game is separate (HERB_GAMES): name the herb from its characters,
find its characters from the name, or write herb names on the Write page.

Pure: the page (games_hsk_page.py) keeps the state and draws the cards.
Every round is {"prompt": card | None, "audio": text | None, "options":
[cards], "answer": index, "reveal": {zh, py, en}, "notes": [(zh, py, en)]}
where a card is {"kind": "word"|"text", "zh", "py", "en"}.
"""

import csv
import functools
import random
import re
from pathlib import Path

from pypinyin import Style, lazy_pinyin, pinyin as _pinyin

import hsk
import placement

GAMES = {
    "listen": ("🎧", "Hear it, find it", "Hear a word, tap its characters. The others sound close."),
    "meaning": ("🔤", "Read it", "See a word in characters, tap what it means."),
    "lookalike": ("👀", "Look-alikes", "Tap the right character from ones that look nearly the same."),
    "measure": ("📏", "Measure words", "一＿书 'a book': which measure word fits?"),
    "scramble": ("🧩", "Sentence scramble", "Put an HSK example sentence back in order."),
    "memory": ("🃏", "Memory match", "Turn over two cards at a time; match characters to meanings."),
    "pictures": ("🖼️", "Picture games", "Picture ↔ word games, HSK words only."),
}
HERB_GAMES = {
    "herb_name": ("🌿", "Name the herb", "See the herb's characters, tap its name."),
    "herb_find": ("🔍", "Find the herb", "See the name, tap its characters — the others share a character or a category."),
    "herb_write": ("✍️", "Write herb names", "Herb names on the Write page, tier-1 herbs first."),
}
SKILL = {"listen": "listen", "meaning": "read", "lookalike": "read", "measure": "read",
         "memory": "read", "pictures": "read", "scramble": "grammar"}
ROUNDS = 10
SCRAMBLE_ROUNDS = 6
MEMORY_PAIRS = 6
OPTIONS = 4

# what each common measure word counts - shown after the answer
MEASURES = {
    "个": "general", "本": "books, bound volumes", "条": "long thin things; rivers, roads, fish",
    "张": "flat things: tables, paper, tickets", "只": "animals; one of a pair",
    "位": "people (polite)", "家": "businesses: shops, firms", "件": "clothes on top; matters",
    "辆": "vehicles", "台": "machines", "座": "mountains, buildings, bridges", "双": "pairs",
    "杯": "a cup / glass of", "块": "lumps, pieces; money", "把": "things with a handle",
    "片": "slices, flat pieces; stretches", "种": "kinds", "次": "times, occurrences",
    "顿": "meals; a bout of", "场": "events: games, films, rain", "部": "films, phones, works",
    "间": "rooms", "门": "school subjects, courses", "套": "sets; flats", "份": "portions, copies, jobs",
    "项": "items, tasks", "道": "dishes; questions; lines", "名": "people (formal)",
    "所": "schools, hospitals", "棵": "trees", "封": "letters", "支": "pens; songs; teams",
    "头": "cattle, pigs", "颗": "small round things", "篇": "essays, articles", "首": "songs, poems",
    "架": "planes, pianos", "节": "class periods; sections", "层": "floors, layers",
    "朵": "flowers, clouds", "盘": "a plate of", "碗": "a bowl of", "瓶": "a bottle of",
    "盒": "a box of", "包": "a packet of", "段": "sections, periods", "幅": "pictures, paintings",
    "条儿": "long thin things", "辈子": "a lifetime", "口": "family members; mouthfuls",
}
MEASURES.pop("条儿")
MEASURES.pop("辈子")

_CJK_ONLY = re.compile(r"[一-鿿]+")


def _plain(rows):
    return [w for w in rows if _CJK_ONLY.fullmatch(w["word"])]


def _word_card(zh, py="", en=""):
    return {"kind": "word", "zh": zh, "py": py, "en": en}


def _text_card(en):
    return {"kind": "text", "zh": "", "py": "", "en": en}


def _round(prompt, options, answer_n, reveal, audio=None, notes=None):
    return {"prompt": prompt, "audio": audio, "options": options, "answer": answer_n,
            "reveal": reveal, "notes": notes or []}


def _place(target, others, rng):
    """target among others, shuffled: (options, index of target)."""
    opts = others + [target]
    rng.shuffle(opts)
    return opts, opts.index(target)


def level_for(game, levels):
    """The HSK level a game draws from (1 until the level test sets one)."""
    levels = levels or {}
    if game == "scramble":
        return hsk.grammar_upto(levels)
    return levels.get(SKILL.get(game, "read")) or 1


# ----------------------------------------------------------------------
# listen: similar-sounding words
# ----------------------------------------------------------------------
def _sound(word):
    return {"bare": lazy_pinyin(word),
            "tone": lazy_pinyin(word, style=Style.TONE3, neutral_tone_with_five=True),
            "init": lazy_pinyin(word, style=Style.INITIALS, strict=False)}


def sound_distance(a, b):
    """How alike two words sound (higher = closer), same length only."""
    if len(a) != len(b):
        return -1
    sa, sb = _sound(a), _sound(b)
    if sa["tone"] == sb["tone"]:
        return -1                                  # a homophone: can't be told apart by ear
    score = 0
    for i in range(len(a)):
        if sa["bare"][i] == sb["bare"][i]:
            score += 3                             # same syllable, maybe another tone
        elif sa["init"][i] and sa["init"][i] == sb["init"][i]:
            score += 1
        if sa["bare"][i][len(sa["init"][i]):] == sb["bare"][i][len(sb["init"][i]):]:
            score += 1                             # same final (shì / zhì)
    return score


def listen_rounds(level, n=ROUNDS, rng=None):
    rng = rng or random.Random()
    pool = _plain(hsk.words_upto(level))
    near = _plain(hsk.words_upto(min(4, level + 1)))
    rounds = []
    for t in rng.sample(pool, min(n, len(pool))):
        cands = [(sound_distance(t["word"], w["word"]), rng.random(), w) for w in near
                 if w["word"] != t["word"]]
        cands = sorted((c for c in cands if c[0] > 0), key=lambda c: (-c[0], c[1]))
        picked = []
        for _, _, w in cands:
            if len(picked) == OPTIONS - 1:
                break
            if all(w["word"] != p["word"] for p in picked):
                picked.append(w)
        if len(picked) < OPTIONS - 1:
            continue
        opts, ans = _place(t, picked, rng)
        rounds.append(_round(
            None, [_word_card(o["word"]) for o in opts], ans,
            {"zh": t["word"], "py": t["pinyin"], "en": placement.show(t["english"])},
            audio=t["word"],
            notes=[(o["word"], o["pinyin"], placement.show(o["english"])) for o in opts
                   if o is not t]))
    return rounds


# ----------------------------------------------------------------------
# meaning: characters -> English
# ----------------------------------------------------------------------
def meaning_rounds(level, n=ROUNDS, rng=None):
    rng = rng or random.Random()
    pool = [w for w in _plain(hsk.words_upto(level)) if placement._tokens(w)
            and placement.show(w["english"])]
    rounds = []
    for t in rng.sample(pool, min(n, len(pool))):
        item = placement.make_item(t, pool, rng)
        rounds.append(_round(
            _word_card(t["word"]), [_text_card(o) for o in item["options"]],
            item["options"].index(item["answer"]),
            {"zh": t["word"], "py": t["pinyin"], "en": item["answer"]}))
    return rounds


# ----------------------------------------------------------------------
# look-alike characters
# ----------------------------------------------------------------------
def _char_py(ch):
    return _pinyin(ch)[0][0]


def cue_word(ch, level):
    """The HSK word (up to level) that best shows ch: two or three
    characters, lowest level first, the character itself if nothing else."""
    words = [w for w in _plain(hsk.words_upto(level)) if ch in w["word"]]
    if not words:
        words = [w for w in _plain(hsk.words_upto(4)) if ch in w["word"]]
    multi = [w for w in words if 2 <= len(w["word"]) <= 3]
    pick = sorted(multi or words, key=lambda w: (w["level"], len(w["word"])))
    return pick[0] if pick else None


def _char_note(ch):
    """(character, pinyin, meaning or a word it's in) for after the answer."""
    w = cue_word(ch, 4)
    if not w:
        return ch, _char_py(ch), ""
    if w["word"] == ch:
        return ch, w["pinyin"], placement.show(w["english"])
    return ch, _char_py(ch), f"as in {w['word']} {w['pinyin']} '{placement.show(w['english'])}'"


def lookalike_rounds(level, n=ROUNDS, rng=None):
    rng = rng or random.Random()
    words = {w["word"] for w in hsk.words_upto(4)}
    chars = hsk.lookalike_chars(level)
    rounds = []
    for ch in rng.sample(chars, len(chars)):
        if len(rounds) == n:
            break
        w = cue_word(ch, level)
        if not w:
            continue
        # no option that would make another real word in the blank (今天 / 明天)
        others = [d for d in hsk.lookalikes(ch) if w["word"].replace(ch, d) not in words]
        if len(others) < OPTIONS - 1:
            continue
        others = others[:5]
        rng.shuffle(others)
        opts, ans = _place(ch, others[:OPTIONS - 1], rng)
        blank = w["word"].replace(ch, "＿")
        rounds.append(_round(
            _word_card(blank, w["pinyin"], placement.show(w["english"])),
            [_word_card(o) for o in opts], ans,
            {"zh": w["word"], "py": w["pinyin"], "en": placement.show(w["english"])},
            notes=[_char_note(o) for o in opts if o != ch]))
    return rounds


# ----------------------------------------------------------------------
# measure words
# ----------------------------------------------------------------------
def measure_answer(word):
    """The measure word to ask for: the noun's own one before the general 个."""
    ms = [m for m in word["measure"] if m in MEASURES]
    if not ms:
        return None
    own = [m for m in ms if m != "个"]
    return own[0] if own else ms[0]


def measure_rounds(level, n=ROUNDS, rng=None):
    rng = rng or random.Random()
    import hsk_grammar as hg
    nouns = [w for w in _plain(hsk.words_upto(level)) if measure_answer(w)]
    special = [w for w in nouns if measure_answer(w) != "个"]
    general = [w for w in nouns if measure_answer(w) == "个"]
    # mostly nouns with a measure word of their own; 个 now and then
    k = min(len(general), max(1, n // 5))
    targets = rng.sample(special, min(n - k, len(special))) + rng.sample(general, k)
    rng.shuffle(targets)
    common = [m for m in MEASURES]
    rounds = []
    for t in targets:
        m = measure_answer(t)
        others = [x for x in common if x not in t["measure"]]
        rng.shuffle(others)
        opts, ans = _place(m, others[:OPTIONS - 1], rng)
        phrase = f"一{m}{t['word']}"
        rounds.append(_round(
            _word_card(f"一＿{t['word']}", t["pinyin"], placement.show(t["english"])),
            [_word_card(o) for o in opts], ans,
            {"zh": phrase, "py": hg.sentence_pinyin(phrase),
             "en": f"{m}: {MEASURES[m]}" + (
                 f" · also {'、'.join(x for x in t['measure'] if x != m)}"
                 if len(t["measure"]) > 1 else "")},
            notes=[(o, _char_py(o), MEASURES[o]) for o in opts if o != m]))
    return rounds


# ----------------------------------------------------------------------
# sentence scramble
# ----------------------------------------------------------------------
@functools.lru_cache(maxsize=4)
def _scramble_pool(level):
    return tuple(placement.grammar_pool(level))


def scramble_items(level, n=SCRAMBLE_ROUNDS, rng=None):
    """Official example sentences up to the grammar level, half of them from
    the level itself."""
    rng = rng or random.Random()
    now = list(_scramble_pool(level))
    before = [ex for lv in range(1, level) for ex in _scramble_pool(lv)]
    rng.shuffle(now)
    rng.shuffle(before)
    k = n if not before else max(n // 2, n - len(before))
    picked = now[:k] + before[:n - len(now[:k])]
    rng.shuffle(picked)
    return [placement.make_grammar_item(ex, rng) for ex in picked]


# ----------------------------------------------------------------------
# memory: characters <-> meanings
# ----------------------------------------------------------------------
def memory_cards(level, pairs=MEMORY_PAIRS, rng=None):
    rng = rng or random.Random()
    pool = [w for w in _plain(hsk.words_upto(level)) if placement._tokens(w)
            and placement.show(w["english"])]
    chosen = []
    for w in rng.sample(pool, len(pool)):
        if all(not placement._clash(w, c) for c in chosen):
            chosen.append(w)
        if len(chosen) == pairs:
            break
    cards = [{"pair": w["word"], "face": f, "img": "", "zh": w["word"], "py": w["pinyin"],
              "en": placement.show(w["english"])} for w in chosen for f in ("word", "text")]
    rng.shuffle(cards)
    return cards


def memory_matches(cards, reported, already=()):
    """Keep only real pairs (a word and its meaning) from what the board reports."""
    ok = set(already)
    by_pair = {}
    for n in set(reported or []):
        if isinstance(n, int) and 0 <= n < len(cards):
            by_pair.setdefault(cards[n]["pair"], []).append(n)
    for ns in by_pair.values():
        if len(ns) == 2 and cards[ns[0]]["face"] != cards[ns[1]]["face"]:
            ok.update(ns)
    return ok


# ----------------------------------------------------------------------
# herbs
# ----------------------------------------------------------------------
HERB_CSV = Path(__file__).resolve().parent.parent / "data" / "herbs.csv"


@functools.lru_cache(maxsize=1)
def herbs():
    """data/herbs.csv as {zh (simplified), trad, py, name, action, category,
    tier, latin}."""
    out = []
    if not HERB_CSV.exists():
        return out
    with open(HERB_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            trad = (r.get("Chinese") or "").strip()
            if not trad:
                continue
            name, _, action = (r.get("English") or "").partition(" - ")
            try:
                tier = int(float(r.get("Tier") or 9))
            except ValueError:
                tier = 9
            out.append({"zh": (r.get("Alt_script") or "").strip() or trad, "trad": trad,
                        "py": (r.get("Pinyin") or "").strip().lower(), "name": name.strip(),
                        "action": action.strip(), "category": (r.get("Category") or "").strip(),
                        "tier": tier, "latin": (r.get("Latin") or "").strip()})
    return out


def _herb_targets(pool, n, rng):
    """Tier-1 herbs first: most rounds from the lowest tiers there are."""
    weights = [1 / h["tier"] ** 2 for h in pool]
    picked = []
    while len(picked) < min(n, len(pool)):
        h = rng.choices(pool, weights)[0]
        if h not in picked:
            picked.append(h)
    return picked


def _herb_reveal(h):
    trad = f" ({h['trad']})" if h["trad"] != h["zh"] else ""
    return {"zh": h["zh"] + trad, "py": h["py"],
            "en": h["name"] + (f" — {h['action']}" if h["action"] else "")
                  + (f" · {h['latin']}" if h["latin"] else "")}


def herb_rounds(game, n=ROUNDS, rng=None, pool=None):
    """herb_name: characters -> name; herb_find: name -> characters, the
    wrong ones sharing a character with it where possible (白芍 / 赤芍)."""
    rng = rng or random.Random()
    pool = list(pool or herbs())
    rounds = []
    for t in _herb_targets(pool, n, rng):
        same_cat = [h for h in pool if h is not t and h["category"] == t["category"]]
        rest = [h for h in pool if h is not t and h["category"] != t["category"]]
        rng.shuffle(same_cat)
        rng.shuffle(rest)
        if game == "herb_find":
            shares = [h for h in pool if h is not t and set(h["zh"]) & set(t["zh"])]
            rng.shuffle(shares)
            order = shares[:2] + same_cat + rest
        else:
            order = same_cat + rest
        picked = []
        for h in order:
            if len(picked) == OPTIONS - 1:
                break
            if (h["name"].lower() != t["name"].lower() and h["zh"] != t["zh"]
                    and all(h["name"] != p["name"] and h["zh"] != p["zh"] for p in picked)):
                picked.append(h)
        opts, ans = _place(t, picked, rng)
        if game == "herb_find":
            prompt = _word_card("", t["py"], t["name"])
            cards = [_word_card(o["zh"]) for o in opts]
        else:
            prompt = _word_card(t["zh"])
            cards = [_text_card(o["name"]) for o in opts]
        rounds.append(_round(prompt, cards, ans, _herb_reveal(t),
                             notes=[(o["zh"], o["py"], o["name"]) for o in opts if o is not t]))
    return rounds


def rounds_for(game, levels, rng=None):
    level = level_for(game, levels)
    return {"listen": listen_rounds, "meaning": meaning_rounds, "lookalike": lookalike_rounds,
            "measure": measure_rounds}[game](level, rng=rng)


def picture_words(level):
    """HSK words (up to level) that the picture games have pictures for."""
    return {w["word"] for w in hsk.words_upto(level, include_erhua=True)}
