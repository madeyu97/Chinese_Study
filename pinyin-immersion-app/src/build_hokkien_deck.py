"""
Build the Penang Hokkien deck from your Mandarin vocabulary.

No LLM is involved. Every entry comes from a licensed dictionary, and each
carries a confidence tier so nothing unverified is ever presented as fact.

SOURCES
-------
1. ChhoeTaigi (required) — CC-licensed Taiwanese Hokkien dictionaries with
   Mandarin headwords (華文), Hokkien hàn-jī and Tâi-lô. Provides the base
   mapping. Get it with:

       git clone --depth 1 https://github.com/ChhoeTaigi/ChhoeTaigiDatabase.git

2. Wiktionary via kaikki.org (optional but recommended) — CC BY-SA. English
   Wiktionary tags Hokkien pronunciations by locality, including Penang.
   Where a Penang-tagged reading exists it overrides the Taiwanese one and
   the entry is promoted to the 'penang' tier. Download the Chinese subset:

       https://kaikki.org/dictionary/Chinese/  (kaikki.org-dictionary-Chinese.jsonl)

CONFIDENCE TIERS
----------------
  penang     — a Penang-tagged reading was found. Highest trust.
  consensus  — 2+ Taiwanese dictionaries agree on the same Hokkien form.
  single     — only one dictionary offered a form. Treat with suspicion.
  (Everything starts unverified; you promote entries to 'verified' in-app.)

USAGE
-----
    python src/build_hokkien_deck.py --chhoetaigi ../ChhoeTaigiDatabase
    python src/build_hokkien_deck.py --chhoetaigi ../ChhoeTaigiDatabase \
        --wiktionary kaikki.org-dictionary-Chinese.jsonl
    python src/build_hokkien_deck.py --chhoetaigi ... --dry-run --limit 30
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

import db_manager as db
from hokkien_engine import tailo_to_taiji, normalise_tailo

# ChhoeTaigi's Mandarin headwords are TRADITIONAL characters; this app's
# vocabulary is SIMPLIFIED. Without conversion the hit rate collapses to
# almost nothing (measured: 0/8 on a simplified sample, 4/8 traditional).
# zhconv is pure-Python with no compiled dependencies, so it installs
# cleanly on Windows. 'zh-tw' is used because ChhoeTaigi is Taiwanese —
# it yields 吃飯 rather than the zh-hant form 喫飯.
try:
    from zhconv import convert as _zh_convert
except ImportError:  # pragma: no cover
    _zh_convert = None
    print("  ! zhconv not installed — simplified vocabulary will barely match.\n"
          "    Fix with:  python -m pip install zhconv")


def lookup_variants(word):
    """Every spelling worth trying against a traditional-character index."""
    seen, out = set(), []
    for cand in (word,
                 _zh_convert(word, "zh-tw") if _zh_convert else None,
                 _zh_convert(word, "zh-hant") if _zh_convert else None):
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out

# ChhoeTaigi files that carry a Mandarin (HoaBun) column, with a weight
# reflecting how directly they assert Mandarin<->Hokkien equivalence.
# iTaigi is an explicit comparison dictionary, so it is trusted most.
CHHOETAIGI_SOURCES = [
    ("ChhoeTaigi_iTaigiHoataiTuichiautian.csv", "iTaigi", 3),
    ("ChhoeTaigi_TaihoaSoanntengTuichiautian.csv", "TaiHoa", 2),
    ("ChhoeTaigi_KauiokpooTaigiSutian.csv", "MOE", 1),
]

SPLIT_RE = re.compile(r"[,，、;；/]")


def load_chhoetaigi(root):
    """Return {mandarin: {hokkien_hanji: {'kip':…, 'srcs':set(), 'w':int}}}."""
    base = root
    if os.path.isdir(os.path.join(root, "ChhoeTaigiDatabase")):
        base = os.path.join(root, "ChhoeTaigiDatabase")

    cand = collections.defaultdict(
        lambda: collections.defaultdict(lambda: {"kip": "", "srcs": set(), "w": 0}))
    found_any = False
    for fname, tag, weight in CHHOETAIGI_SOURCES:
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            print(f"  ! missing {fname} — skipping")
            continue
        found_any = True
        n = 0
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                hoa = (row.get("HoaBun") or "").strip()
                kip = (row.get("KipUnicode") or "").strip()
                han = (row.get("HanLoTaibunKip") or "").strip()
                if not hoa or not kip:
                    continue
                # '(替)' marks a substitute character; '/' separates variants
                kip = kip.replace("(替)", "").split("/")[0].strip()
                han = han.replace("(替)", "").split("/")[0].strip()
                form = han or hoa
                for m in SPLIT_RE.split(hoa):
                    m = m.strip()
                    if not m:
                        continue
                    slot = cand[m][form]
                    slot["w"] += weight
                    slot["srcs"].add(tag)
                    if not slot["kip"]:
                        slot["kip"] = kip
                    n += 1
        print(f"  + {tag}: {n} mappings")
    if not found_any:
        raise SystemExit(
            "No ChhoeTaigi CSVs found. Clone the database first:\n"
            "  git clone --depth 1 "
            "https://github.com/ChhoeTaigi/ChhoeTaigiDatabase.git")
    return cand


def load_penang_overlay(jsonl_path):
    """Extract Penang-tagged Hokkien readings from a kaikki.org Chinese dump.

    Wiktionary marks Hokkien pronunciations by locality; we keep the ones
    whose tags mention Penang (or Malaysian Hokkien). Returns
    {hanji: {'tailo':…, 'poj':…}}.
    """
    overlay = {}
    if not jsonl_path:
        return overlay
    if not os.path.exists(jsonl_path):
        print(f"  ! Wiktionary file not found: {jsonl_path} — skipping overlay")
        return overlay

    kept = 0
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            word = entry.get("word")
            if not word:
                continue
            for snd in entry.get("sounds", []):
                tags = " ".join(snd.get("tags", []) or []).lower()
                raw = (snd.get("raw_tags") and
                       " ".join(snd["raw_tags"]).lower()) or ""
                blob = tags + " " + raw
                if "penang" not in blob and "malaysian hokkien" not in blob:
                    continue
                rec = overlay.setdefault(word, {})
                if "tai-lo" in blob or "tâi-lô" in blob or "tailo" in blob:
                    rec.setdefault("tailo", snd.get("zh-pron") or snd.get("other", ""))
                elif "poj" in blob or "pe̍h-ōe-jī" in blob:
                    rec.setdefault("poj", snd.get("zh-pron") or snd.get("other", ""))
                kept += 1
    print(f"  + Wiktionary: Penang-tagged readings for {len(overlay)} forms "
          f"({kept} sound records)")
    return overlay


SENTENCE_PUNCT = "。，？！；：、,?!"


def classify_entry(word):
    """Why an entry can't be looked up, if it can't.

    A third of a real learner vocabulary is sentences and idiomatic phrases.
    No dictionary contains those, so they are reported separately rather
    than lumped in with genuine lookup failures.
    """
    han = [c for c in word if "\u4e00" <= c <= "\u9fff"]
    if any(p in word for p in SENTENCE_PUNCT):
        return "sentence"
    if len(han) >= 5:
        return "phrase"
    if not han:
        return "non_han"
    return "word"


def decompose(word, cand, max_piece=4):
    """Greedy longest-match split of a compound into dictionary sub-words.

    一定要 -> 一定 + 要. Returns (pieces, forms, tailos) or None. Used only
    when the whole word is absent, and tagged 'composed' because
    word-by-word composition is a weaker claim than a dictionary entry.
    """
    pieces, i = [], 0
    while i < len(word):
        hit = None
        for length in range(min(max_piece, len(word) - i), 0, -1):
            piece = word[i:i + length]
            for variant in lookup_variants(piece):
                if variant in cand:
                    hit = (piece, variant)
                    break
            if hit:
                break
        if not hit:
            return None
        pieces.append(hit)
        i += len(hit[0])
    if len(pieces) < 2:
        return None
    forms, tailos = [], []
    for _piece, variant in pieces:
        form, meta, _n = pick_best(cand[variant])
        if LATIN_RE.search(form):
            return None          # unusable piece — don't build a junk card
        forms.append(form)
        tailos.append(normalise_tailo(meta["kip"]))
    return [p for p, _ in pieces], "".join(forms), "-".join(t for t in tailos if t)


LATIN_RE = re.compile(r"[A-Za-z\u0100-\u01ff\u1e00-\u1eff]")


def pick_best(forms):
    """Rank candidate Hokkien forms: most source agreement first, then weight.

    Forms containing Latin letters are demoted — some dictionary rows mix
    romanisation into the hàn-jī field (e.g. '我lóngm̄-bat'), which makes a
    useless flashcard.
    """
    def key(kv):
        form, meta = kv
        mixed = 1 if LATIN_RE.search(form) else 0
        return (mixed, -len(meta["srcs"]), -meta["w"])
    items = sorted(forms.items(), key=key)
    top_form, top = items[0]
    return top_form, top, len(items)


def main():
    ap = argparse.ArgumentParser(description="Build the Penang Hokkien deck")
    ap.add_argument("--chhoetaigi", required=True,
                    help="path to the cloned ChhoeTaigiDatabase repo")
    ap.add_argument("--wiktionary", default="",
                    help="optional kaikki.org Chinese JSONL for Penang overlay")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N vocab words (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without writing to the database")
    args = ap.parse_args()

    print("Loading ChhoeTaigi…")
    cand = load_chhoetaigi(args.chhoetaigi)
    print(f"  = {len(cand)} unique Mandarin headwords")

    print("Loading Penang overlay…")
    overlay = load_penang_overlay(args.wiktionary)

    print("Reading your vocabulary…")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chinese, pinyin, english FROM vocab_progress "
                "ORDER BY priority_weight DESC, id")
    vocab = [{"chinese": r[0], "pinyin": r[1], "english": r[2]}
             for r in cur.fetchall()]
    conn.close()
    if args.limit:
        vocab = vocab[:args.limit]
    print(f"  = {len(vocab)} vocabulary entries")

    tiers = collections.Counter()
    made = 0
    for v in vocab:
        mand = v["chinese"].strip()
        # Split entries like '之前 / 以前' the same way the main app does
        heads = [h.strip() for h in SPLIT_RE.split(mand) if h.strip()] or [mand]
        forms = None
        used_head = mand
        for h in heads:
            for variant in lookup_variants(h):
                if variant in cand:
                    forms, used_head = cand[variant], h
                    break
            if forms:
                break
        if not forms:
            kind = classify_entry(mand)
            if kind in ("sentence", "phrase", "non_han"):
                tiers[f"skipped_{kind}"] += 1
                continue
            comp = decompose(heads[0], cand)
            if comp:
                _pieces, hokkien_hanji, tailo = comp
                tiers["composed"] += 1
                taiji = tailo_to_taiji(tailo)
                if args.dry_run:
                    print(f"  {mand:8} -> {hokkien_hanji:8} {tailo:18} {taiji:18} "
                          f"[composed]")
                else:
                    if db.hokkien_add(
                            mandarin=heads[0], mandarin_full=mand,
                            english=v["english"], hokkien_hanji=hokkien_hanji,
                            tailo=tailo, taiji=taiji, tier="composed",
                            sources="composed", alternatives=1):
                        made += 1
                continue
            tiers["no_match"] += 1
            continue

        hokkien_hanji, meta, n_alts = pick_best(forms)
        tailo = normalise_tailo(meta["kip"])
        sources = sorted(meta["srcs"])

        tier = "consensus" if len(sources) > 1 else "single"
        ov = overlay.get(hokkien_hanji)
        if ov and ov.get("tailo"):
            tailo = normalise_tailo(ov["tailo"])
            tier = "penang"
        elif ov and ov.get("poj"):
            tier = "penang"

        taiji = tailo_to_taiji(tailo)
        tiers[tier] += 1

        if args.dry_run:
            print(f"  {mand:8} -> {hokkien_hanji:8} {tailo:18} {taiji:18} "
                  f"[{tier}] {sources} alts={n_alts}")
            continue

        if db.hokkien_add(
                mandarin=used_head, mandarin_full=mand,
                english=v["english"], hokkien_hanji=hokkien_hanji,
                tailo=tailo, taiji=taiji, tier=tier,
                sources=",".join(sources), alternatives=n_alts):
            made += 1

    print("\nResults:")
    for k in ("penang", "consensus", "single", "composed"):
        if tiers.get(k):
            print(f"  {k:22} {tiers[k]:5}")
    skipped = sum(v for k, v in tiers.items() if k.startswith("skipped_"))
    if skipped:
        print(f"  {'skipped (sentences/phrases)':22} {skipped:5}"
              "   <- no dictionary contains these; expected, not a failure")
    if tiers.get("no_match"):
        print(f"  {'no dictionary entry':22} {tiers['no_match']:5}")
    if args.dry_run:
        print("(dry run — nothing written)")
    else:
        print(f"Wrote {made} new deck entries.")
        stats = db.hokkien_stats()
        print(f"Deck now: {stats['total']} entries "
              f"({stats['verified']} verified, {stats['penang']} Penang-tagged).")
        print("\nOpen the 福建話 Hokkien page in the app to verify entries. "
              "Nothing drills until you confirm it.")


if __name__ == "__main__":
    sys.exit(main())
