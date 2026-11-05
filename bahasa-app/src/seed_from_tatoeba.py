"""
Fill the sentence bank from human-written Tatoeba sentences
(data/tatoeba_ms_en.tsv) before any model writes one.

The sentences are written by real speakers, so the grammar risk that the
writer's gate exists for isn't there; the reviewer checks each English
translation and the model writes only the wrong-answer options (two calls a
sentence). Listen & speak does the same for one word at a time when it
needs a sentence; this script does it in bulk.

Run from bahasa-app/src with DATABASE_URL and GROQ_API_KEY set:

    python seed_from_tatoeba.py                     # 2 per word, lessons first
    python seed_from_tatoeba.py --per-word 3 --limit 50
    python seed_from_tatoeba.py --words makan,sakit

Resumable: words that already have --per-word sentences are skipped, and it
stops cleanly at a rate limit - run it again later.
"""

import argparse
import logging
import sys
import time

import db_manager as db
import tatoeba

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def vocab_order():
    conn = db.get_connection()
    cursor = conn.cursor()
    # your lesson words first, then the frequency list most-common first;
    # Indonesian forms are for recognising, not for modelling sentences on
    cursor.execute("""SELECT malay, english FROM vocab WHERE tag IS NULL
                      ORDER BY from_lessons DESC, freq_rank ASC NULLS LAST, id""")
    rows = [{"malay": r[0], "english": r[1]} for r in cursor.fetchall()]
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Seed the sentence bank from Tatoeba")
    parser.add_argument("--per-word", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="max words this run (0 = all)")
    parser.add_argument("--words", type=str, default="", help="comma-separated words only")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    vocab = vocab_order()
    if args.words:
        wanted = {w.strip().lower() for w in args.words.split(",") if w.strip()}
        vocab = [v for v in vocab if v["malay"] in wanted]
    blocked, flagged = db.get_blocklist(), db.get_recent_flags()
    print(f"{len(tatoeba.pairs())} Tatoeba sentences available")
    made, words_done = 0, 0
    try:
        for word in vocab:
            need = args.per_word - db.bank_count_for(word["malay"])
            if need <= 0:
                continue
            rows = tatoeba.matches(word, blocked, limit=need * 2)
            if not rows:
                continue
            words_done += 1
            if args.limit and words_done > args.limit:
                print(f"--limit {args.limit} reached; stopping.")
                break
            print(f"\n[{word['malay']}] {len(rows)} candidates, seeding up to {need}")
            for row in rows:
                if need <= 0:
                    break
                try:
                    ex = tatoeba.make_exercise(row, word, flagged)
                except Exception as e:
                    msg = str(e).lower()
                    if "429" in msg or ("rate" in msg and "limit" in msg):
                        print("\nRate limit reached - progress is saved. Run again later.")
                        raise SystemExit(0)
                    logging.error(f"  error: {e}")
                    continue
                if ex and db.bank_add(word["malay"], ex):
                    made += 1
                    need -= 1
                    print(f"  + {ex['malay']}")
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted - progress is saved.")
    stats = db.bank_stats()
    print(f"\nDone. Seeded {made} sentences. Bank now: {stats['active_sentences']} sentences, "
          f"{stats['vocab_covered']}/{stats['vocab_total']} words covered.")


if __name__ == "__main__":
    sys.exit(main())
