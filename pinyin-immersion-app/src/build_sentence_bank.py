"""
Batch sentence-bank builder.

Pre-generates and validates exercises for every vocab item, so study
sessions serve vetted sentences instead of rolling fresh LLM dice. Safe to
interrupt and re-run: every stored sentence persists immediately, and
--only-missing (default) skips words that already have enough coverage.

Usage (from the pinyin-immersion-app directory):

    python src/build_sentence_bank.py                  # 3 per word, resume
    python src/build_sentence_bank.py --per-word 5
    python src/build_sentence_bank.py --limit 50       # cap words this run
    python src/build_sentence_bank.py --words 巴刹,成绩  # specific words

Groq free tier allows ~1000 requests/day and each sentence costs roughly
2-4 calls (generation + review + retries), so a full first build of a large
vocab list takes a few runs across a few days. The script stops cleanly on
rate limits; just run it again later — it picks up where it left off.
"""

import argparse
import sys
import time
import logging

import db_manager as db
from ai_prompter import generate_dictation_exercise

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def get_all_vocab():
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese, pinyin, english FROM vocab_progress "
                   "ORDER BY priority_weight DESC, id")
    rows = [{"chinese": r[0], "pinyin": r[1], "english": r[2]}
            for r in cursor.fetchall()]
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Pre-generate the sentence bank")
    parser.add_argument("--per-word", type=int, default=3,
                        help="target vetted sentences per vocab item (default 3)")
    parser.add_argument("--limit", type=int, default=0,
                        help="max words to process this run (0 = all)")
    parser.add_argument("--words", type=str, default="",
                        help="comma-separated hanzi to process only these")
    parser.add_argument("--sleep", type=float, default=2.0,
                        help="seconds between generations (rate-limit kindness)")
    args = parser.parse_args()

    vocab = get_all_vocab()
    if args.words:
        wanted = {w.strip() for w in args.words.split(",") if w.strip()}
        vocab = [v for v in vocab if v["chinese"] in wanted]

    blocked = db.get_blocklist()
    flagged = db.get_recent_flags()
    stats_before = db.bank_stats()
    print(f"Bank before: {stats_before['active_sentences']} sentences, "
          f"{stats_before['vocab_covered']}/{stats_before['vocab_total']} words covered")

    made, skipped, failed, words_done = 0, 0, 0, 0
    try:
        for word in vocab:
            have = db.bank_count_for(word["chinese"])
            need = args.per_word - have
            if need <= 0:
                skipped += 1
                continue

            words_done += 1
            if args.limit and words_done > args.limit:
                print(f"--limit {args.limit} reached; stopping.")
                break

            print(f"\n[{word['chinese']}] have {have}, generating {need}...")
            for _ in range(need):
                try:
                    ex = generate_dictation_exercise(
                        word, mode="listen",
                        blocked_sentences=blocked,
                        flagged_examples=flagged)
                except Exception as e:
                    msg = str(e).lower()
                    if "rate" in msg and "limit" in msg or "429" in msg:
                        print("\nRate limit reached — progress is saved. "
                              "Re-run later to continue.")
                        raise SystemExit(0)
                    logging.error(f"  generation error: {e}")
                    failed += 1
                    continue

                if not ex:
                    failed += 1
                    continue
                if db.bank_add(word["chinese"], ex):
                    made += 1
                    print(f"  + {ex['chinese']}")
                else:
                    # duplicate sentence — doesn't add variety, count as skip
                    print(f"  = duplicate: {ex['chinese']}")
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted — progress is saved.")

    stats_after = db.bank_stats()
    print(f"\nDone. Added {made} sentences ({failed} failed). "
          f"Bank now: {stats_after['active_sentences']} sentences, "
          f"{stats_after['vocab_covered']}/{stats_after['vocab_total']} words covered.")


if __name__ == "__main__":
    sys.exit(main())
