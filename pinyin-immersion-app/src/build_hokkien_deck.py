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

# ChhoeTaigi annotates entries inline: (白) colloquial reading, (文) literary,
# (替) substitute character, (俗) common form, plus occasional alternative
# readings like (tshìn). None belong on a flashcard, so strip them all.
ANNOTATION_RE = re.compile(r"[（(][^）)]*[）)]")


def clean_field(value):
    """Remove inline annotations and pick the first variant."""
    if not value:
        return ""
    value = ANNOTATION_RE.sub("", value)
    value = value.split("/")[0]
    return re.sub(r"\s+", " ", value).strip(" -")


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
                kip = clean_field(kip)
                han = clean_field(han)
                if not kip:
                    continue
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


BASIC_FILE = "ChhoeTaigi_TaioanPehoeKichhooGiku.csv"   # 基礎語句 core vocabulary
JUNK_ENGLISH = re.compile(r"^\s*(\d|cf\.|see\b|\[)", re.I)
HANJI_SOURCES = ["ChhoeTaigi_KauiokpooTaigiSutian.csv",
                 "ChhoeTaigi_TaihoaSoanntengTuichiautian.csv"]


def load_romanisation_to_hanji(base):
    """Map (Tâi-lô, Mandarin gloss) -> hàn-jī.

    Keyed on the PAIR, not the romanisation alone. Hokkien is full of
    homophones — sik alone is 色 colour, 熟 ripe, 式 ceremony and 室 room —
    so a romanisation-only lookup confidently assigns wrong characters
    (observed: 龍 lîng "dragon" rendered as 拎). Requiring the Mandarin gloss
    to agree as well makes the mapping trustworthy.
    """
    out = {}
    for fname in HANJI_SOURCES:
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kip = clean_field(row.get("KipUnicode"))
                han = clean_field(row.get("HanLoTaibunKip"))
                if not kip or not han or LATIN_RE.search(han):
                    continue
                for hoa in SPLIT_RE.split(row.get("HoaBun") or ""):
                    hoa = clean_field(hoa)
                    if hoa:
                        out.setdefault((kip, hoa), han)
    return out


def load_core_vocabulary(base):
    """Foundational Hokkien vocabulary (kinship, particles, everyday words)
    that a Mandarin wordlist will never surface. Returns rows ranked by
    cross-dictionary presence — a reasonable proxy for how core a word is."""
    path = os.path.join(base, BASIC_FILE)
    if not os.path.exists(path):
        print(f"  ! {BASIC_FILE} not found — core vocabulary unavailable")
        return []
    rom2han = load_romanisation_to_hanji(base)

    # how many dictionaries mention each romanisation
    freq = collections.Counter()
    for fname in HANJI_SOURCES + [BASIC_FILE]:
        p = os.path.join(base, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kip = clean_field(row.get("KipUnicode"))
                if kip:
                    freq[kip] += 1

    entries = []
    seen = set()
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            kip = clean_field(row.get("KipUnicode"))
            eng = (row.get("EngBun") or "").strip()
            hoa = clean_field(row.get("HoaBun"))
            if not kip or not eng or not hoa:
                continue
            # Some rows carry page references or cross-reference codes rather
            # than a definition (e.g. '2934 [penn5]') — not teachable.
            if JUNK_ENGLISH.match(eng) or len(eng) < 3:
                continue
            # Require romanisation AND Mandarin gloss to agree before trusting
            # the characters (see load_romanisation_to_hanji).
            hanji = rom2han.get((kip, hoa))
            if not hanji:
                continue
            key = (hanji, kip)
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "tailo": normalise_tailo(kip), "english": eng,
                "mandarin": hoa or kip, "hanji": hanji,
                "rank": freq.get(kip, 1),
            })
    entries.sort(key=lambda e: -e["rank"])
    return entries


def words_from_sentences(vocab, cand):
    """Pull the individual words out of sentence-type vocabulary entries.

    Sentences can't be looked up whole, but the words inside them are words
    the learner is actively studying — the most relevant expansion source
    available. Ordered by how often each word appears across the sentences.
    """
    try:
        import jieba
        jieba.setLogLevel(60)
    except ImportError:
        print("  ! jieba not installed — cannot mine sentences")
        return []
    counts = collections.Counter()
    for v in vocab:
        word = v["chinese"].strip()
        if classify_entry(word) not in ("sentence", "phrase"):
            continue
        for tok in jieba.cut(word):
            tok = tok.strip()
            if len(tok) >= 2 and all("\u4e00" <= c <= "\u9fff" for c in tok):
                counts[tok] += 1
    out = []
    for tok, n in counts.most_common():
        for variant in lookup_variants(tok):
            if variant in cand:
                out.append((tok, variant, n))
                break
    return out



# ======================================================================
# HOKKIEN LEARNING CENTER (malaysia_north) — genuinely Malaysian data
#
#   git clone https://github.com/william-sy/hokkien-learning-center.git
#
# This is northern-Malaysian (Penang-region) Hokkien with English, hàn-jī,
# POJ, Tâi-lô and semantic tags — far closer to what is spoken in Penang
# than the Taiwanese dictionaries. Entries are ranked for a new learner by
# topic, so the verification queue and study order start with what is
# actually useful on day one.
#
# The project describes itself as an open educational resource for Hokkien
# preservation. It carries no formal licence file, so treat this as
# personal study use and credit the project if you share anything built
# from it.
# ======================================================================

# Lower number = learn earlier. Grouped by what a beginner in Penang needs.
TAG_PRIORITY = {
    # survival: greetings, function words, questions
    "greeting": 10, "politeness": 11, "pronoun": 12, "question": 13,
    "negation": 14, "particle": 15, "basic": 16, "exclamation": 17,
    "number": 20, "grammar": 21, "adverb": 22,
    # daily life in Penang
    "food": 30, "drink": 31, "shopping": 32, "time": 33, "family": 34,
    "direction": 35, "place": 36, "transport": 37, "body": 38,
    # common content words
    "verb": 45, "adjective": 46, "home": 47, "emotion": 48, "social": 49,
    "colour": 50, "clothing": 51, "weather": 52, "medical": 53,
    "people": 54, "profession": 55, "education": 56,
    # broader vocabulary
    "culture": 60, "nature": 61, "animal": 62, "plant": 63, "object": 64,
    "loanword": 40,      # Malay/English loans are high-value in Penang
    "misc": 80, "vulgar": 85,
}
DEFAULT_TAG_RANK = 70


def hlc_rank(entry):
    """Usefulness rank for a Hokkien Learning Center entry (lower = sooner)."""
    tags = [t.lower() for t in entry.get("tags", [])]
    base = min((TAG_PRIORITY.get(t, DEFAULT_TAG_RANK) for t in tags),
               default=DEFAULT_TAG_RANK)
    # Penang-specific entries first within their band
    if "penang" in tags:
        base -= 5
    # whole phrases are immediately usable
    if entry.get("category") == "phrase":
        base -= 2
    # entries with characters make better cards than romanisation alone
    if not entry.get("hanzi"):
        base += 1
    return max(1, base)


def load_hlc(path):
    """Load malaysia_north entries plus the shared phrase list."""
    base = path
    for candidate in (os.path.join(path, "data"), path):
        if os.path.isdir(os.path.join(candidate, "dialects", "malaysia_north")):
            base = candidate
            break
    else:
        raise SystemExit(
            f"Could not find data/dialects/malaysia_north under {path}.\n"
            "Clone it with:\n"
            "  git clone --depth 1 "
            "https://github.com/william-sy/hokkien-learning-center.git")

    entries = []
    mn_dir = os.path.join(base, "dialects", "malaysia_north")
    for fname in sorted(os.listdir(mn_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(mn_dir, fname), encoding="utf-8") as f:
                entries.extend(json.load(f))

    phrases_path = os.path.join(base, "phrases.json")
    if os.path.exists(phrases_path):
        with open(phrases_path, encoding="utf-8") as f:
            for p in json.load(f):
                p.setdefault("tags", []).append("greeting")
                p["category"] = "phrase"
                entries.append(p)

    # Lesson order is the most authoritative signal available: promote any
    # entry whose English matches a lesson word, ranked by lesson number.
    lessons_path = os.path.join(base, "lessons.json")
    lesson_rank = {}
    if os.path.exists(lessons_path):
        with open(lessons_path, encoding="utf-8") as f:
            for lesson in json.load(f).get("lessons", []):
                for pos, key in enumerate(lesson.get("wordKeys", [])):
                    lesson_rank.setdefault(key.strip().lower(),
                                           lesson.get("order", 99))

    out = []
    seen = set()
    for e in entries:
        eng = (e.get("english") or "").strip()
        tailo = normalise_tailo(e.get("tl") or e.get("poj") or "")
        if not eng or not tailo:
            continue
        hanji = (e.get("hanzi") or "").strip()
        key = (hanji or tailo, eng.lower())
        if key in seen:
            continue
        seen.add(key)
        rank = hlc_rank(e)
        lr = lesson_rank.get(eng.lower())
        if lr is not None:
            rank = lr          # lesson words outrank everything (1-19)
        out.append({
            "english": eng, "tailo": tailo,
            "hanji": hanji or "—",
            "tags": ",".join(e.get("tags", [])),
            "rank": rank,
            "example": (e.get("example") or "").strip(),
        })
    out.sort(key=lambda x: (x["rank"], x["english"].lower()))
    return out


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


# Hokkien characters have separate literary (文) and colloquial (白) readings.
# Dictionaries list the literary one for an isolated character, but inside a
# counting phrase the colloquial reading is correct: 一碗 is tsi̍t-uánn, not
# i̍t-uánn. Whole-word dictionary hits already carry the right reading — this
# only corrects word-by-word composition.
COLLOQUIAL_IN_COMPOUND = {
    "一": "tsi̍t",
    "二": "nn\u0304g",
    "個": "\u00ea",
    "个": "\u00ea",
}

# Characters that behave as classifiers/measure words, used to detect a
# counting phrase.
MEASURE_WORDS = set("盤盘碟碗次擺摆個个杯支枝張张條条隻只件本頭头包份塊块"
                    "粒瓶罐點点箱台部間间張张床區区種种層层頓顿位隻")


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
    for pos, (piece, variant) in enumerate(pieces):
        form, meta, _n = pick_best(cand[variant])
        if LATIN_RE.search(form):
            return None          # unusable piece — don't build a junk card
        tailo = normalise_tailo(meta["kip"])
        # Apply the colloquial reading when this piece is a numeral or 個
        # sitting inside a counting phrase.
        if piece in COLLOQUIAL_IN_COMPOUND:
            nxt = pieces[pos + 1][0] if pos + 1 < len(pieces) else ""
            if piece in ("個", "个") or (nxt and (nxt[0] in MEASURE_WORDS
                                                 or nxt in COLLOQUIAL_IN_COMPOUND)):
                tailo = COLLOQUIAL_IN_COMPOUND[piece]
        forms.append(form)
        tailos.append(tailo)
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
    ap.add_argument("--from-sentences", action="store_true",
                    help="also mine the words inside your sentence entries")
    ap.add_argument("--hlc", default="",
                    help="path to a cloned hokkien-learning-center repo; adds "
                         "genuinely Malaysian vocabulary ordered by usefulness")
    ap.add_argument("--hlc-limit", type=int, default=0,
                    help="cap how many HLC entries to add (0 = all)")
    ap.add_argument("--core", type=int, default=0,
                    help="also add N core Hokkien words (kinship, particles, "
                         "everyday vocabulary a Mandarin list never surfaces)")
    ap.add_argument("--target", type=int, default=0,
                    help="aim for this total deck size; enables --from-sentences "
                         "and tops up with core vocabulary automatically")
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

        rank_by_tier = {"penang": 200, "consensus": 300, "single": 500}
        if db.hokkien_add(
                mandarin=used_head, mandarin_full=mand,
                english=v["english"], hokkien_hanji=hokkien_hanji,
                tailo=tailo, taiji=taiji, tier=tier,
                sources=",".join(sources), alternatives=n_alts,
                learn_rank=rank_by_tier.get(tier, 500)):
            made += 1

    # ------------------------------------------------------------------
    # PASS 0 — Hokkien Learning Center (real Malaysian vocabulary)
    # ------------------------------------------------------------------
    if args.hlc:
        print("\nLoading Hokkien Learning Center (malaysia_north)…")
        hlc = load_hlc(args.hlc)
        if args.hlc_limit:
            hlc = hlc[:args.hlc_limit]
        print(f"  {len(hlc)} Malaysian entries, ordered by usefulness")
        added = 0
        for e in hlc:
            if args.dry_run:
                if added < 14:
                    print(f"  [{e['rank']:3}] {e['hanji']:8} {e['tailo']:20} "
                          f"{e['english'][:38]:38} {e['tags'][:26]}")
                added += 1
                continue
            if db.hokkien_add(mandarin=e["english"], mandarin_full=e["english"],
                              english=e["english"], hokkien_hanji=e["hanji"],
                              tailo=e["tailo"], taiji=tailo_to_taiji(e["tailo"]),
                              tier="malaysian", sources="hokkien-learning-center",
                              alternatives=1, learn_rank=e["rank"]):
                added += 1
                made += 1
        tiers["malaysian"] = added
        print(f"  {'previewed' if args.dry_run else 'added'} {added}")

    # ------------------------------------------------------------------
    # EXPANSION PASS 1 — words inside your sentence entries
    # ------------------------------------------------------------------
    want_sentences = args.from_sentences or args.target
    if want_sentences:
        print("\nMining words from your sentence entries…")
        mined = words_from_sentences(vocab, cand)
        added = 0
        for tok, variant, _n in mined:
            forms = cand[variant]
            hokkien_hanji, meta, n_alts = pick_best(forms)
            if LATIN_RE.search(hokkien_hanji):
                continue
            tailo = normalise_tailo(meta["kip"])
            sources = sorted(meta["srcs"])
            tier = "consensus" if len(sources) > 1 else "single"
            ov = overlay.get(hokkien_hanji)
            if ov and (ov.get("tailo") or ov.get("poj")):
                if ov.get("tailo"):
                    tailo = normalise_tailo(ov["tailo"])
                tier = "penang"
            if args.dry_run:
                if added < 10:
                    print(f"  {tok:8} -> {hokkien_hanji:8} {tailo:18} [{tier}] (from sentences)")
            elif db.hokkien_add(mandarin=tok, mandarin_full=tok,
                                english="(from your sentences)",
                                hokkien_hanji=hokkien_hanji, tailo=tailo,
                                taiji=tailo_to_taiji(tailo), tier=tier,
                                sources=",".join(sources) or "sentence-mined",
                                alternatives=n_alts, learn_rank=400):
                added += 1
                made += 1
            tiers[f"sentence_{tier}"] += 1
        print(f"  {'previewed' if args.dry_run else 'added'} "
              f"{len(mined) if args.dry_run else added} words from sentences")

    # ------------------------------------------------------------------
    # EXPANSION PASS 2 — core Hokkien vocabulary
    # ------------------------------------------------------------------
    core_wanted = args.core
    if args.target and not args.dry_run:
        current = db.hokkien_stats()["total"]
        core_wanted = max(0, args.target - current)
    elif args.target and args.dry_run:
        core_wanted = args.core or 500

    if core_wanted:
        print(f"\nAdding up to {core_wanted} core Hokkien words…")
        core = load_core_vocabulary(
            os.path.join(args.chhoetaigi, "ChhoeTaigiDatabase")
            if os.path.isdir(os.path.join(args.chhoetaigi, "ChhoeTaigiDatabase"))
            else args.chhoetaigi)
        added = 0
        for e in core:
            if added >= core_wanted:
                break
            if args.dry_run:
                if added < 10:
                    print(f"  {e['hanji']:8} {e['tailo']:18} "
                          f"{tailo_to_taiji(e['tailo']):18} — {e['english'][:40]}")
                added += 1
                continue
            if db.hokkien_add(mandarin=e["mandarin"], mandarin_full=e["mandarin"],
                              english=e["english"], hokkien_hanji=e["hanji"],
                              tailo=e["tailo"], taiji=tailo_to_taiji(e["tailo"]),
                              tier="core", sources="basic-vocabulary",
                              alternatives=1, learn_rank=600):
                added += 1
                made += 1
        tiers["core"] = added
        print(f"  {'previewed' if args.dry_run else 'added'} {added} core words")

    print("\nResults:")
    for k in ("malaysian", "penang", "consensus", "single", "composed", "core",
              "sentence_penang", "sentence_consensus", "sentence_single"):
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
