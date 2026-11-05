"""Turn the hand-written gloss files (tools/glosses/g01.txt ... g10.txt) into
data/glosses.csv, which build_wordlist.py joins onto the ranked list.

Gloss line format (one word per line, pipe-separated):
    word|english|root|affixes|pos|reg|flags
    reg:   c = colloquial, f = formal, blank = standard
    flags: I = Indonesian form, ? = unsure (goes to the review queue)

Run:  python3 -I tools/glosses_to_csv.py
"""
import csv
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
GLOSS_DIR = APP / "tools" / "glosses"
OUT = APP / "data" / "glosses.csv"

POS = {"n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb",
       "prep": "preposition", "conj": "conjunction", "interj": "interjection",
       "num": "number", "pron": "pronoun", "det": "determiner", "aux": "auxiliary",
       "part": "particle", "q": "question word"}
REG = {"c": "colloquial", "f": "formal", "": "standard"}
EQ = re.compile(r"=\s*([a-z][a-z \-/]*[a-z])")


def parse(path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 7:
            raise ValueError(f"{path.name}:{n}: expected 7 fields, got {len(parts)}")
        word, english, root, affixes, pos, reg, flags = (p.strip() for p in parts)
        if pos not in POS or reg not in REG or flags not in ("", "I", "?"):
            raise ValueError(f"{path.name}:{n}: bad pos/reg/flags in {line!r}")
        eq = ""
        if flags == "I":
            m = EQ.search(english)
            eq = m.group(1).strip() if m else ""
        yield {
            "malay": word, "english": english, "root": root,
            "affixes": affixes.replace(" ", ""), "pos": POS[pos], "register": REG[reg],
            "tag": "Indonesian" if flags == "I" else "",
            "my_equivalent": eq, "check": "unsure" if flags == "?" else "",
        }


def main():
    rows, seen = [], set()
    for path in sorted(GLOSS_DIR.glob("g*.txt")):
        for r in parse(path):
            if r["malay"] in seen:
                raise ValueError(f"duplicate gloss: {r['malay']}")
            seen.add(r["malay"])
            rows.append(r)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    tagged = sum(1 for r in rows if r["tag"])
    unsure = sum(1 for r in rows if r["check"])
    print(f"{OUT.name}: {len(rows)} glosses, {tagged} Indonesian, {unsure} unsure")


if __name__ == "__main__":
    main()
