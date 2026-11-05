"""
Builds the app's word list from the OpenSubtitles 2018 Malay frequency
counts.

    python tools/build_wordlist.py            # rebuild data/wordlist_base.csv
                                              # and data/malay_words.csv

Run from the bahasa-app directory. The three source lists (Malay, English,
Indonesian; hermitdave/FrequencyWords, CC BY-SA 4.0) are downloaded into
tools/sources/ the first time.

Steps
  1. Clean: drop names, English, subtitle markup and credit lines; merge
     abbreviations and OCR errors (yg -> yang); split run-together
     spellings (disini -> di + sini). English words are spotted by how much
     more often they occur in English subtitles than Malay ones; every
     doubtful case in the top 8,000 was decided by hand (wordlist_rules.py).
  2. Fold clitics: melakukannya, padaku, bolehkah, pergilah count towards
     melakukan, pada, boleh, pergi. Words that only look like word + clitic
     (masalah, sekolah, akhirnya) stay whole.
  3. Keep the top 5,000 and flag Indonesian forms with the usual Malaysian
     word.
  4. Join the hand-written glosses (data/glosses.csv): meaning, root,
     affixes, part of speech, register, and an 'unsure' mark where a
     native speaker should check.

Outputs
  data/wordlist_base.csv   rank, malay, count, indonesian   (no glosses)
  data/malay_words.csv     what the app imports
"""

import csv
import math
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(HERE))
from wordlist_rules import (CLITICS, DROP, FOLD_DROP, INDO, KEEP, KEEP_WHOLE, MERGE,  # noqa: E402
                            NOT_INDO, PROCLITICS, SPLIT)

SOURCES = HERE / "sources"
URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/{0}/{0}_50k.txt"
LEXICON = APP / "src" / "malay" / "data" / "lexicon.txt"
BASE_CSV = APP / "data" / "wordlist_base.csv"
GLOSS_CSV = APP / "data" / "glosses.csv"
OUT_CSV = APP / "data" / "malay_words.csv"
INDO_CSV = APP / "src" / "malay" / "data" / "indonesian.csv"
SIZE = 5000
REVIEWED_RANKS = 8000          # raw ranks every rule was checked against
WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")


def load_counts(lang):
    path = SOURCES / f"{lang}_50k.txt"
    if not path.exists():
        SOURCES.mkdir(exist_ok=True)
        print(f"downloading {lang}_50k.txt …")
        urllib.request.urlretrieve(URL.format(lang), path)
    out = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        w, c = line.split()
        out[w] = (i, int(c))
    return out


def stem_known(w, lex):
    """A word, or the word without one clitic, is in the dictionary."""
    if w in lex:
        return True
    cands = {w}
    for s in ("nyalah", "nyakah", "nyapun", "kannya", "annya", "nya", "kulah", "mulah",
              "lah", "kah", "pun", "tah", "ku", "mu"):
        if w.endswith(s) and len(w) - len(s) >= 3:
            cands.add(w[:-len(s)])
    for c in list(cands):
        for p in PROCLITICS:
            if c.startswith(p) and len(c) - len(p) >= 3:
                cands.add(c[len(p):])
    return any(c in lex for c in cands)


def clean(ms, en, lex):
    """Step 1 -> {word: count} for every usable word in the reviewed ranks."""
    ms_total = sum(c for _r, c in ms.values())
    en_total = sum(c for _r, c in en.values())
    counts = {}

    def add(w, c):
        counts[w] = counts.get(w, 0) + c

    for w, (rank, c) in sorted(ms.items(), key=lambda x: x[1][0]):
        if rank > REVIEWED_RANKS:
            break
        if w in DROP or len(w) == 1 or not WORD.fullmatch(w):
            continue
        if w in MERGE:
            add(MERGE[w], c)
            continue
        if w in SPLIT:
            for part in SPLIT[w].split():
                add(part, c)
            continue
        if w in KEEP or w in INDO:
            add(w, c)
            continue
        # English and names: far more frequent (relatively) in English subtitles
        ratio = (c / ms_total) / ((en[w][1] / en_total) if w in en else 0.5 / en_total)
        if stem_known(w, lex) and (ratio >= 20 or w in lex):
            add(w, c)
    return counts


def fold(counts, lex):
    """Step 2: clitic forms count towards their base word."""
    folded = dict(counts)
    for w in sorted(counts, key=lambda x: -counts[x]):
        if w in KEEP_WHOLE or w not in folded:
            continue
        if w in FOLD_DROP:
            folded.pop(w)
            continue
        base = None
        for s in CLITICS:
            if w.endswith(s) and len(w) - len(s) >= 3:
                b = w[:-len(s)]
                if b in counts or b in lex:
                    base = b
                    break
        if base is None:
            for p in PROCLITICS:
                if w.startswith(p) and len(w) - len(p) >= 3 and w[len(p):] in counts \
                        and w not in lex:
                    base = w[len(p):]
                    break
        if base and base != w:
            folded[base] = folded.get(base, 0) + folded.pop(w)
    return folded


def indonesian_flags(top, ms, idl):
    """Step 3b: Indonesian forms -> Malaysian word. Words that look
    Indonesian by frequency but have no entry in INDO are reported for a
    decision."""
    ms_total = sum(c for _r, c in ms.values())
    id_total = sum(c for _r, c in idl.values())
    flags, review = {}, []
    for w, c in top:
        if w in INDO:
            flags[w] = INDO[w]
        elif w not in NOT_INDO:
            ratio = (c / ms_total) / ((idl[w][1] / id_total) if w in idl else 0.5 / id_total)
            if ratio < 0.15:
                review.append(w)
    return flags, review


def main():
    lex = set(LEXICON.read_text(encoding="utf-8").split())
    ms, en, idl = load_counts("ms"), load_counts("en"), load_counts("id")
    counts = fold(clean(ms, en, lex), lex)
    top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:SIZE]
    flags, review = indonesian_flags(top, ms, idl)
    with BASE_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "malay", "count", "indonesian"])
        for i, (word, c) in enumerate(top, 1):
            w.writerow([i, word, c, flags.get(word, "")])
    print(f"{BASE_CSV.name}: {len(top)} words, {len(flags)} Indonesian forms, "
          f"lowest count {top[-1][1]}")
    if review:
        print("Look Indonesian but not decided (add to INDO or NOT_INDO):", " ".join(review))
    with INDO_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["indonesian", "malaysian"])
        w.writerows(sorted(INDO.items()))
    print(f"{INDO_CSV.name}: {len(INDO)} Indonesian -> Malaysian pairs")

    if not GLOSS_CSV.exists():
        print(f"{GLOSS_CSV.name} not found - {OUT_CSV.name} not written.")
        return
    with GLOSS_CSV.open(encoding="utf-8") as f:
        glosses = {r["malay"]: r for r in csv.DictReader(f)}
    missing = [word for word, _c in top if word not in glosses]
    cols = ["rank", "malay", "english", "root", "affixes", "pos", "register", "tag",
            "my_equivalent", "count", "per_million", "check"]
    total = sum(c for _r, c in ms.values())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(cols)
        for i, (word, c) in enumerate(top, 1):
            g = glosses.get(word)
            if not g:
                continue
            tag = g.get("tag") or ("Indonesian" if word in flags else "")
            wr.writerow([i, word, g["english"], g.get("root", ""), g.get("affixes", ""),
                         g.get("pos", ""), g.get("register", ""), tag,
                         flags.get(word, g.get("my_equivalent", "")), c,
                         round(c * 1e6 / total, 1), g.get("check", "")])
    print(f"{OUT_CSV.name}: {len(top) - len(missing)} glossed words"
          + (f"; {len(missing)} still need glosses: {' '.join(missing[:40])}" if missing else ""))


if __name__ == "__main__":
    main()
