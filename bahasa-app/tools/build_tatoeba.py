"""Build data/tatoeba_ms_en.tsv: human-written Malay sentences from Tatoeba
with their English translations, filtered for the app.

Tatoeba (https://tatoeba.org) sentences are written by real speakers and
shared under CC BY 2.0 FR. Each kept sentence records its Tatoeba id and
author, for attribution.

Kept only if the sentence:
  - is in Latin script (not Jawi), 3-12 words, without digits or quotes
  - names nobody (Tatoeba's stock Tom and Mary): no capitalised word after
    the first, apart from places and languages
  - has no Indonesian forms
  - uses at most one word from outside the 5,000-word list
"dia" / "-nya" sentences get He/She in the English.

Run:  python3 -I tools/build_tatoeba.py   (downloads the exports if missing)
"""
import bz2
import csv
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP / "src"))
import ai_prompter as ap  # noqa: E402
from malay import normalise  # noqa: E402

SOURCES = HERE / "sources"
OUT = APP / "data" / "tatoeba_ms_en.tsv"
BASE = "https://downloads.tatoeba.org/exports/per_language/"
FILES = {"zsm_sentences_detailed.tsv.bz2": "zsm/", "zsm-eng_links.tsv.bz2": "zsm/",
         "eng_sentences.tsv.bz2": "eng/"}
PROPER = set("""Malaysia Melayu Inggeris Cina Jepun India Indonesia Singapura Thailand Kuala
Lumpur Pulau Pinang Johor Kedah Sabah Sarawak Melaka Perak Selangor Kelantan Terengganu Pahang
Islam Allah Tuhan Bahasa Asia Eropah Amerika Afrika Australia Perancis Jerman Itali Sepanyol
Rusia Korea Mesir Arab Thai Tamil Krismas Ahad Isnin Selasa Rabu Khamis Jumaat Sabtu Januari
Februari Mac April Mei Jun Julai Ogos September Oktober November Disember""".split())


def fetch():
    SOURCES.mkdir(exist_ok=True)
    for name, sub in FILES.items():
        path = SOURCES / name
        if not path.exists():
            print(f"downloading {name}…")
            urllib.request.urlretrieve(BASE + sub + name, path)


def lines(name):
    with bz2.open(SOURCES / name, "rt", encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n").split("\t")


# Tatoeba's stock cast, some of whom are also Malay words (sami = monk)
NAMES = set("""tom mary john sami layla ken jim bob alice maria jack mike tony kate bill emily
lucy muiriel betty nancy peter linda yanni skura dan jane david paul""".split())


# Sentences with a known error, by Tatoeba id: 751564 has "Dapatkan" for "Dapatkah".
BAD_IDS = {"751564"}


def keep(malay):
    if not re.fullmatch(r"[A-Za-z\s,.!?'\-]+", malay) or "'" in malay:
        return False
    toks = malay.split()
    if not 3 <= len(toks) <= 12:
        return False
    for i, t in enumerate(toks):
        word = t.strip(",.!?")
        if word[:1].isupper() and (word.lower() in NAMES or (i and word not in PROPER)):
            return False
    if normalise.indonesian_in(malay):
        return False
    return len(ap.off_list(malay)) <= 1


def main():
    fetch()
    malay = {p[0]: (p[2], p[3] if len(p) > 3 else "") for p in lines("zsm_sentences_detailed.tsv.bz2")
             if len(p) >= 3}
    links = defaultdict(list)
    for p in lines("zsm-eng_links.tsv.bz2"):
        links[p[0]].append(p[1])
    wanted = {e for es in links.values() for e in es}
    english = {p[0]: p[2] for p in lines("eng_sentences.tsv.bz2") if p[0] in wanted}
    rows, seen = [], set()
    for sid, (text, author) in malay.items():
        ens = [english[e] for e in links.get(sid, []) if e in english]
        text = re.sub(r"\s+", " ", text).strip()
        if not ens or text in seen or sid in BAD_IDS or not keep(text):
            continue
        seen.add(text)
        en = ens[0]
        if ap.gender_neutral(text):
            en = ap.normalize_pronouns(en)
        rows.append((text, en, sid, author))
    rows.sort(key=lambda r: int(r[2]))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["malay", "english", "tatoeba_id", "author"])
        w.writerows(rows)
    print(f"{OUT.name}: {len(rows)} sentences kept of {len(malay)} Malay sentences "
          f"({sum(1 for s in malay if links.get(s))} with an English translation)")


if __name__ == "__main__":
    main()
