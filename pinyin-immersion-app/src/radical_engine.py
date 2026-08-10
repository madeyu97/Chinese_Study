"""
Radical / component decomposition, with an eye to Chinese medicine.

Herb names are unusually learnable through their components, because the
semantic radical very often tells you what KIND of substance it is:

    艹  grass      a plant - most of the materia medica
    木  tree       woody: bark, twig, heartwood
    竹  bamboo     bamboo-derived
    米  rice       grain or seed
    虫  insect     insect-derived
    鱼 贝 骨 角     animal-derived
    石 金          mineral
    疒  sickness   names describing what it treats

So 茯苓 splits as 艹+伏 and 艹+令 - both marked as plants - while 龙骨 keeps
骨 "bone" and 石膏 keeps 石 "stone", telling you at a glance that they are
not herbs at all. The remaining component is usually phonetic and often
hints at the pronunciation.

Decomposition data comes from hanzipy, which is already a dependency.
"""

import logging
import threading

_decomposer = None
_dec_lock = threading.Lock()
_cache = {}


def _get_decomposer():
    global _decomposer
    if _decomposer is None:
        with _dec_lock:
            if _decomposer is None:
                from hanzipy.decomposer import HanziDecomposer
                # hanzipy chatters at DEBUG while compiling its tables
                logging.getLogger().setLevel(logging.INFO)
                _decomposer = HanziDecomposer()
    return _decomposer


# What a semantic radical implies about a medicinal substance.
SUBSTANCE_HINTS = {
    "艹": ("plant", "a plant - leaf, flower, stem or whole herb"),
    "艸": ("plant", "a plant"),
    "木": ("wood", "woody - bark, twig or heartwood"),
    "竹": ("plant", "bamboo-derived"),
    "米": ("seed", "a grain or seed"),
    "禾": ("seed", "a cereal or grain"),
    "虫": ("animal", "insect or worm-derived"),
    "鱼": ("animal", "fish-derived"),
    "贝": ("animal", "shell-derived"),
    "骨": ("animal", "bone-derived"),
    "角": ("animal", "horn-derived"),
    "肉": ("animal", "flesh-derived"),
    # 月 is deliberately ABSENT: it is "moon" in some characters and the
    # "meat" radical in others, so it mislabels minerals as animal parts
    # (石膏 gypsum and 龙骨 fossil bone were both wrongly tagged).
    "石": ("mineral", "a mineral or stone"),
    "金": ("mineral", "a metal or mineral"),
    # 土 is also absent: too often structural rather than semantic
    # (牡 in 牡蛎 contains it but the substance is shell).
    "疒": ("indication", "illness - the name describes what it treats"),
    "皮": ("part", "skin or peel"),
    "根": ("part", "root"),
    "子": ("part", "seed or fruit"),
    "花": ("plant", "a flower"),
    "叶": ("plant", "a leaf"),
    "草": ("plant", "a herb"),
    "骨": ("animal", "bone-derived"),
    "壳": ("animal", "shell-derived"),
    "参": ("plant", "a root herb (ginseng family)"),
}

NO_GLYPH = "No glyph available"


def decompose(ch):
    """Component breakdown of one character.

    Returns {'character', 'components': [{'component','meaning','hint'}],
             'substance': str|None, 'substance_note': str|None}

    `components` uses the single-level ("once") split, which is what a
    learner actually sees - 芪 as 艹 + 氏, not as six strokes.
    """
    if ch in _cache:
        return _cache[ch]

    result = {"character": ch, "components": [],
              "substance": None, "substance_note": None}

    # A character may BE a semantic radical (石 stone, 骨 bone, 木 tree).
    # Decomposing past it loses the very signal we want, so check first.
    if ch in SUBSTANCE_HINTS:
        result["substance"], result["substance_note"] = SUBSTANCE_HINTS[ch]

    try:
        dec = _get_decomposer()
        raw = dec.decompose(ch)
        parts = [p for p in (raw.get("once") or []) if p and p != NO_GLYPH]
        if not parts:
            parts = [p for p in (raw.get("radical") or [])
                     if p and p != NO_GLYPH]
        seen = set()
        for p in parts:
            if p in seen or p == ch:
                continue
            seen.add(p)
            try:
                meaning = dec.get_radical_meaning(p)
            except Exception:
                meaning = None
            hint = SUBSTANCE_HINTS.get(p)
            result["components"].append({
                "component": p,
                "meaning": meaning or "",
                "hint": hint[1] if hint else "",
            })
            if hint and not result["substance"]:
                result["substance"], result["substance_note"] = hint
    except Exception as e:
        logging.warning(f"[RADICAL] decompose failed for {ch}: {e}")

    _cache[ch] = result
    return result


def describe_word(word):
    """Decompose every character of a herb name, and summarise what the
    radicals collectively suggest about the substance."""
    chars = [c for c in word if "\u4e00" <= c <= "\u9fff"]
    per_char = [decompose(c) for c in chars]
    # Chinese compounds are HEAD-FINAL: the last character names the thing,
    # earlier ones modify it. 金银花 is a flower (not gold), 桂枝 a twig,
    # 陈皮 a peel. So read the signal from the right, falling back leftward
    # when the final character carries none (石膏: 膏 is uninformative, 石
    # tells you it's a mineral).
    signalled = [d for d in reversed(per_char) if d["substance"]]
    summary = ""
    if signalled:
        kinds = {d["substance"] for d in signalled}
        note = signalled[0]["substance_note"]
        if len(kinds) == 1 and len(signalled) > 1:
            summary = f"Both characters point to {note}."
        elif len(kinds) == 1:
            summary = f"The radical marks this as {note}."
        else:
            # Mixed signals: lead with the first character, which carries
            # the head noun in almost every herb name.
            others = ", ".join(sorted(k for k in kinds
                                      if k != signalled[0]["substance"]))
            summary = (f"The final character marks {note} "
                       f"(earlier characters suggest {others}).")
    return {"word": word, "characters": per_char, "summary": summary}


def shares_component(ch, component):
    """Other characters built from the same component, for spotting
    families like 茯 苓 芍 荆 - all 艹, all plants."""
    try:
        found = _get_decomposer().get_characters_with_component(component)
        return [c for c in (found or []) if c != ch][:12]
    except Exception:
        return []


def warm_up():
    """Preload the decomposition tables in the background (they take a
    couple of seconds to compile)."""
    def _load():
        try:
            _get_decomposer()
        except Exception as e:
            logging.warning(f"[RADICAL] preload skipped: {e}")
    threading.Thread(target=_load, daemon=True, name="radical-warmup").start()
