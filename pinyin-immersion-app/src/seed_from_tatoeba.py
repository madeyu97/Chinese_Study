"""
Seed the sentence bank with human-written Tatoeba sentences.

Tatoeba sentences are written by real speakers (CC-BY licensed), so the
grammar risk that motivates all the LLM validation machinery simply doesn't
exist for them. Only the MCQ distractors come from the LLM (~1 call per
sentence instead of 2-4), so this is also the cheapest way to build bulk
coverage.

DATA FILE — get the Mandarin-English pair file from manythings.org (a
Tatoeba-derived Anki export, tab-separated "English<TAB>Chinese<TAB>attribution"):

    https://www.manythings.org/anki/cmn-eng.zip

Unzip it and run (from the pinyin-immersion-app directory):

    python src/seed_from_tatoeba.py --file cmn-eng.txt
    python src/seed_from_tatoeba.py --file cmn-eng.txt --per-word 3 --limit 50
    python src/seed_from_tatoeba.py --file cmn-eng.txt --words 巴刹,成绩

Like build_sentence_bank.py this is resumable: it skips words that already
have --per-word coverage and stops cleanly on rate limits.
"""

import argparse
import sys
import time
import logging

import db_manager as db
from dictionary_engine import build_breakdown, derive_pinyin, is_cjk_char
from ai_prompter import (
    generate_distractors_for,
    _force_simplified,
    _normalize_ta_pronouns,
    _detect_homophones,
    _classify_target,
    MALAYSIAN_SLANG,
    SLANG_BREAKDOWN_GLOSS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Tatoeba's stock cast of characters — the app's rule is "no invented
# names, use pronouns", so skip sentences built around them.
NAME_BLOCKLIST = ("汤姆", "湯姆", "玛丽", "玛莉", "瑪麗", "玛利亚", "迈克",
                  "穆里尔", "肯尼", "吉姆", "鲍勃", "南希", "贝蒂", "约翰",
                  "彼得", "琳达", "麦克")


def load_pairs(path):
    """Parse the manythings TSV. Tolerant of 2- or 3-column lines."""
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            english, chinese = parts[0].strip(), parts[1].strip()
            if english and chinese and any(is_cjk_char(c) for c in chinese):
                pairs.append((chinese, english))
    return pairs


def usable(chinese, english, min_len, max_len, blocked):
    hanzi_len = sum(1 for c in chinese if is_cjk_char(c))
    if not (min_len <= hanzi_len <= max_len):
        return False
    if any(name in chinese for name in NAME_BLOCKLIST):
        return False
    if chinese in blocked:
        return False
    return True


def make_exercise(chinese, english, vocab_word):
    chinese = _force_simplified(chinese)
    english_correct = english
    if any("他" in g for g in _detect_homophones(chinese)):
        english_correct = _normalize_ta_pronouns(english_correct)

    distractors = generate_distractors_for(chinese, english_correct)
    if len(distractors) < 3:
        return None

    slang_overrides = {k: SLANG_BREAKDOWN_GLOSS[k]
                       for k in SLANG_BREAKDOWN_GLOSS if k in chinese}
    breakdown = build_breakdown(
        chinese, overrides=slang_overrides,
        ensure_words=[vocab_word["chinese"]] + list(MALAYSIAN_SLANG.keys()))

    return {
        "chinese": chinese,
        "pinyin": derive_pinyin(chinese),
        "english_correct": english_correct,
        "english_distractors": distractors,
        "target_pinyin": vocab_word.get("pinyin", ""),
        "word_breakdown": breakdown,
        "grammar_point": {},
        "particle_note": None,
        "target_category": _classify_target(vocab_word["chinese"],
                                            vocab_word.get("english", "")),
        "generation_mode": "listen",
        "source": "tatoeba",
    }


def main():
    parser = argparse.ArgumentParser(description="Seed bank from Tatoeba pairs")
    parser.add_argument("--file", required=True, help="cmn-eng.txt TSV path")
    parser.add_argument("--per-word", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0,
                        help="max words to process this run (0 = all)")
    parser.add_argument("--words", type=str, default="",
                        help="comma-separated hanzi to process only these")
    parser.add_argument("--min-len", type=int, default=4)
    parser.add_argument("--max-len", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    pairs = load_pairs(args.file)
    print(f"Loaded {len(pairs)} Tatoeba pairs from {args.file}")

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese, pinyin, english FROM vocab_progress "
                   "ORDER BY priority_weight DESC, id")
    vocab = [{"chinese": r[0], "pinyin": r[1], "english": r[2]}
             for r in cursor.fetchall()]
    conn.close()
    if args.words:
        wanted = {w.strip() for w in args.words.split(",") if w.strip()}
        vocab = [v for v in vocab if v["chinese"] in wanted]

    blocked = db.get_blocklist()
    made, words_done = 0, 0
    try:
        for word in vocab:
            have = db.bank_count_for(word["chinese"])
            need = args.per_word - have
            if need <= 0:
                continue
            matches = [(c, e) for c, e in pairs
                       if word["chinese"] in c
                       and usable(c, e, args.min_len, args.max_len, blocked)]
            if not matches:
                continue

            words_done += 1
            if args.limit and words_done > args.limit:
                print(f"--limit {args.limit} reached; stopping.")
                break

            print(f"\n[{word['chinese']}] {len(matches)} corpus matches, "
                  f"seeding up to {need}...")
            for chinese, english in matches[:need * 2]:  # spare for failures
                if need <= 0:
                    break
                try:
                    ex = make_exercise(chinese, english, word)
                except Exception as e:
                    msg = str(e).lower()
                    if ("rate" in msg and "limit" in msg) or "429" in msg:
                        print("\nRate limit reached — progress is saved. "
                              "Re-run later to continue.")
                        raise SystemExit(0)
                    logging.error(f"  error: {e}")
                    continue
                if ex and db.bank_add(word["chinese"], ex):
                    made += 1
                    need -= 1
                    print(f"  + {ex['chinese']}")
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted — progress is saved.")

    stats = db.bank_stats()
    print(f"\nDone. Seeded {made} corpus sentences. Bank now: "
          f"{stats['active_sentences']} sentences, "
          f"{stats['vocab_covered']}/{stats['vocab_total']} words covered.")


if __name__ == "__main__":
    sys.exit(main())
