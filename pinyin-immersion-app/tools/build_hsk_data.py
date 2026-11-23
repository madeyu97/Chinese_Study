"""
Build data/hsk/ from the 2025 HSK syllabus (HSK 3.0, exams from 13 Dec 2026).

Run once from pinyin-immersion-app/, pointing at two checkouts:

    git clone --depth 1 https://github.com/RyanGibb/anki-hsk3   /tmp/anki-hsk3
    git clone --depth 1 https://github.com/krmanik/HSK-3.0      /tmp/HSK-3.0
    (cd /tmp && npm pack hanzi-writer-data@2.0.1 && mkdir -p hwd &&
     tar xzf hanzi-writer-data-2.0.1.tgz -C hwd)          # stroke data
    python tools/build_hsk_data.py /tmp/anki-hsk3 /tmp/HSK-3.0 /tmp/hwd/package

Writes, for levels 1-4 only:

  words.csv       word, level, pinyin, pos, english, erhua
  recognise.csv   char, level          characters to recognise (认读字)
  write.csv       char, band           characters to write by hand (手写字);
                                       band 2 = the syllabus's "HSK 1-2" list
  grammar.csv     id, level, point, type, category, detail
  grammar_examples.csv  grammar_id, chinese, english
  write_order.csv the 400 writing characters in teaching order: band by
                  band, and within a band parts before the characters built
                  from them (女 before 好 and 妈), commonest first.
                  Each with its stroke count, the HSK word that cues it and
                  the parts it builds on.

See data/hsk/SOURCES.md for where each comes from.
"""

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "src"))
import dictionary_engine as de  # noqa: E402

OUT = HERE / "data" / "hsk"
LEVELS = ("1", "2", "3", "4")


def tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def house_glosses():
    """Short English from the app's own hand-checked frequency list."""
    out = {}
    with open(HERE / "data" / "frequency_words.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["Chinese"], row["English"])
    return out


_DROP = re.compile(r"^(surname|variant of|old variant|see\b|CL:|also pr\.|abbr\. for|"
                   r"used in |\(Tw\)|\(dialect\)|\(archaic\)|\(old\))", re.I)


def short_gloss(cedict):
    """CC-CEDICT definition -> two or three plain senses."""
    senses = []
    for part in re.split(r"[/;]", cedict or ""):
        part = re.sub(r"\[[^\]]*\]", "", part).strip()      # [pin1 yin1] references
        part = re.sub(r"[一-鿿|]+", "", part).strip(" ,") if "|" in part else part
        if not part or _DROP.match(part) or part in senses:
            continue
        senses.append(part)
        if len(senses) == 3:
            break
    return " / ".join(senses)


def build_words(anki):
    house = house_glosses()
    rows, seen = [], {}
    for r in tsv(anki / "data/raw/punpuf_hsk_word_list.tsv"):
        if r["level"] not in LEVELS:
            continue
        # homographs are numbered in the syllabus (会1 can, 会2 meeting): one
        # word for the app, at its lowest level
        word, level = re.sub(r"\d+$", "", r["word"]), int(r["level"])
        if word in seen:                     # 真 at 1 (adverb) and 4 (adjective): keep the first
            seen[word]["pos"] = "、".join(dict.fromkeys(
                seen[word]["pos"].split("、") + [p for p in r["part_of_speech"].split("、") if p]))
            continue
        pinyin = de.format_pinyin(r["pinyin"])
        english = house.get(word) or short_gloss(r["definition_cc-cedict"])
        if "[" in english or re.search(r"\bsee\b", english.split("/")[0]):
            english = short_gloss(english) or short_gloss(r["definition_cc-cedict"])
        english = re.sub(r"\s*\((Taiwan|also) pr\.[^)]*\)", "", english).strip()
        row = {"word": word, "level": level, "pinyin": pinyin,
               "pos": r["part_of_speech"], "english": english,
               "erhua": int(de.has_erhua(word, pinyin) and word not in ("儿子", "女儿"))}
        seen[word] = row
        rows.append(row)
    return rows


def build_recognise(hsk3):
    rows, seen = [], set()
    for lv in LEVELS:
        path = hsk3 / "New HSK (2025)" / "HSK Hanzi" / f"HSK_Level_{lv}_hanzi.txt"
        for ch in path.read_text(encoding="utf-8").split():
            if ch not in seen:
                seen.add(ch)
                rows.append({"char": ch, "level": int(lv)})
    return rows


def build_write(anki):
    rows = []
    for r in tsv(anki / "data/raw/chelsea_hanzi_writing.tsv"):
        band = r["examLevelId"].replace("HSK", "")
        if band in ("2", "3", "4"):
            rows.append({"char": r["word"], "band": int(band)})
    return rows


def build_grammar(anki):
    fixes = {}
    with open(anki / "data/grammar-fixes.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fixes[r["wrong"]] = r["right"]
    english = {}
    with open(anki / "data/grammar-translations.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            english[r["chinese"]] = r["english"]
    points, examples = [], []
    for r in tsv(anki / "data/raw/official_grammar.tsv"):
        level = r["examLevelId"].replace("HSK", "")
        if level not in LEVELS:
            continue
        gid = f"g{level}-{sum(1 for p in points if p['level'] == int(level)) + 1:02d}"
        point = fixes.get(r["content"], r["content"])
        points.append({"id": gid, "level": int(level), "point": point,
                       "type": r["grammarType"], "category": r["categoryType"],
                       "detail": r["grammarDetail"]})
        for case in filter(None, (c.strip() for c in r["cases"].split("|"))):
            case = fixes.get(case, case)
            examples.append({"grammar_id": gid, "chinese": case,
                             "english": english.get(case, "")})
    return points, examples


def _rank(ch):
    return de.character_info(ch)["rank"] or 10 ** 6


def _cue(ch, words, band):
    """The HSK word to cue a character with: one from the lowest level that
    has it, two characters long if possible (the other character shows, the
    target is blanked), the commonest of those."""
    have = [w for w in words if ch in w["word"] and not w["erhua"]]
    if not have:
        return {"word": ch, "pinyin": de.derive_pinyin(ch), "english": ""}

    def key(w):
        size = 0 if len(w["word"]) == 2 else 1 if len(w["word"]) == 1 else 2
        return (w["level"], size, _rank(w["word"][0]) + _rank(w["word"][-1]))
    best = min(have, key=key)
    # no Chinese in the meaning: 开车's 'to drive a car (Malaysia: 驾车)' would
    # show the very character being asked for
    from placement import show
    return {"word": best["word"], "pinyin": best["pinyin"],
            "english": show(best["english"]) or best["english"]}


def build_write_order(write_rows, words, strokes_dir):
    import radical_engine as re_
    chars = [r["char"] for r in write_rows]
    band_of = {r["char"]: r["band"] for r in write_rows}

    def strokes(ch):
        if not strokes_dir:
            return ""
        import json
        path = Path(strokes_dir) / f"{ch}.json"
        return len(json.loads(path.read_text(encoding="utf-8"))["strokes"]) if path.exists() else ""

    parts = {ch: [c["component"] for c in re_.decompose(ch)["components"]
                  if c["component"] in band_of and c["component"] != ch] for ch in chars}
    order, placed = [], set()
    for band in (2, 3, 4):
        todo = sorted((c for c in chars if band_of[c] == band),
                      key=lambda c: (_rank(c), strokes(c) or 99))
        while todo:
            # the commonest character whose parts (in this band) are all placed
            nxt = next((c for c in todo if all(p in placed or band_of[p] > band
                                               for p in parts[c])), todo[0])
            todo.remove(nxt)
            placed.add(nxt)
            order.append(nxt)
    rows = []
    for i, ch in enumerate(order, 1):
        cue = _cue(ch, words, band_of[ch])
        rows.append({"char": ch, "band": band_of[ch], "order": i, "strokes": strokes(ch),
                     "cue_word": cue["word"], "cue_pinyin": cue["pinyin"],
                     "cue_english": cue["english"],
                     "builds_on": "".join(p for p in parts[ch] if order.index(p) < i - 1)})
    return rows


def write(name, rows, fields):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main(anki, hsk3, strokes_dir=None):
    anki, hsk3 = Path(anki), Path(hsk3)
    words = build_words(anki)
    write("words.csv", words, ["word", "level", "pinyin", "pos", "english", "erhua"])
    write("recognise.csv", build_recognise(hsk3), ["char", "level"])
    write_rows = build_write(anki)
    write("write.csv", write_rows, ["char", "band"])
    write("write_order.csv", build_write_order(write_rows, words, strokes_dir),
          ["char", "band", "order", "strokes", "cue_word", "cue_pinyin", "cue_english",
           "builds_on"])
    points, examples = build_grammar(anki)
    write("grammar.csv", points, ["id", "level", "point", "type", "category", "detail"])
    write("grammar_examples.csv", examples, ["grammar_id", "chinese", "english"])


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
