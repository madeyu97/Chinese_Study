"""Compare the app's sentence pinyin with a hand-written reference.

    python tools/check_pinyin.py path/to/grammar-pinyin.csv [--show N]

The reference is anki-hsk3's data/grammar-pinyin.csv (chinese,pinyin) for the
official HSK example sentences. Spacing, capitals and punctuation are
ignored; what's counted is a different syllable or a different tone. The
reference leaves the general measure word 个 toneless and so does the app.
"""
import csv
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pinyin_hsk  # noqa: E402

MARKS = {c: (v, t) for v, marks in {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò",
                                    "u": "ūúǔù", "ü": "ǖǘǚǜ"}.items()
         for t, c in enumerate(marks, 1)}


def flat(p):
    p = unicodedata.normalize("NFC", p.lower()).replace("(r)", "r")
    return re.sub(r"[^a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]", "", p)


def main(path, show=0):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    bad = []
    for r in rows:
        zh = re.sub(r"（[^）]*）|\([^)]*\)", "", r["chinese"])
        ref = re.sub(r"\([^)]*\)", "", r["pinyin"])
        ref = re.sub(r"^[AB]: ?|(?<=[.?!]) [AB]: ?", "", ref)
        ours = pinyin_hsk.sentence_pinyin(zh)
        if flat(ours) != flat(ref):
            bad.append((r["chinese"], ours, r["pinyin"]))
    print(f"{len(rows) - len(bad)} of {len(rows)} sentences match the reference")
    for b in bad[:show]:
        print(" | ".join(b))
    return bad


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    main(sys.argv[1], n)
