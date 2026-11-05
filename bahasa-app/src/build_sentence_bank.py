"""
Write and check listening sentences for words the bank and Tatoeba don't
cover, so sessions serve vetted sentences instead of writing on the spot.

Every sentence passes the writer's gate (target present, no Indonesian,
numbers agree, everyday words only, not flagged) and a reviewer model; each
stored sentence persists at once.

Run from bahasa-app/src with DATABASE_URL and GROQ_API_KEY set (after
seed_from_tatoeba.py, which is cheaper and human-written):

    python build_sentence_bank.py                  # 2 per word, resume
    python build_sentence_bank.py --per-word 3 --limit 50
    python build_sentence_bank.py --words makan,sakit

Groq's free tier allows about 1,000 requests a day and a sentence costs 2-4,
so a full build takes a few runs. It stops cleanly at a rate limit.
"""

import argparse
import logging
import sys
import time

import db_manager as db
from ai_prompter import generate_exercise
from seed_from_tatoeba import vocab_order

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Write listening sentences into the bank")
    parser.add_argument("--per-word", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="max words this run (0 = all)")
    parser.add_argument("--words", type=str, default="", help="comma-separated words only")
    parser.add_argument("--sleep", type=float, default=2.0)
    args = parser.parse_args()

    vocab = vocab_order()
    if args.words:
        wanted = {w.strip().lower() for w in args.words.split(",") if w.strip()}
        vocab = [v for v in vocab if v["malay"] in wanted]
    blocked, flagged = db.get_blocklist(), db.get_recent_flags()
    before = db.bank_stats()
    print(f"Bank before: {before['active_sentences']} sentences, "
          f"{before['vocab_covered']}/{before['vocab_total']} words covered")
    made, failed, words_done = 0, 0, 0
    try:
        for word in vocab:
            need = args.per_word - db.bank_count_for(word["malay"])
            if need <= 0:
                continue
            words_done += 1
            if args.limit and words_done > args.limit:
                print(f"--limit {args.limit} reached; stopping.")
                break
            print(f"\n[{word['malay']}] writing {need}")
            for _ in range(need):
                try:
                    ex = generate_exercise(word, "listen", blocked, flagged)
                except Exception as e:
                    msg = str(e).lower()
                    if "429" in msg or ("rate" in msg and "limit" in msg):
                        print("\nRate limit reached - progress is saved. Run again later.")
                        raise SystemExit(0)
                    logging.error(f"  error: {e}")
                    failed += 1
                    continue
                if not ex:
                    failed += 1
                    continue
                if db.bank_add(word["malay"], ex):
                    made += 1
                    print(f"  + {ex['malay']}")
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted - progress is saved.")
    after = db.bank_stats()
    print(f"\nDone. Added {made} ({failed} failed). Bank now: {after['active_sentences']} "
          f"sentences, {after['vocab_covered']}/{after['vocab_total']} words covered.")


if __name__ == "__main__":
    sys.exit(main())
