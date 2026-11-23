"""
Fill the grammar drill bank overnight, so every lesson is written before
it's needed (see src/drill_bank.py).

For each person on the HSK track: the reviews coming due in the next few
days and the next new structures in HSK order, most urgent first - each
gets a drill set written, checked, reviewed and stored, unless a usable
one is stored already. Then graded reading passages at their reading
level, up to READING_STOCK unread.

    DATABASE_URL=... GROQ_API_KEY=... python tools/fill_bank.py [max_sets]

Run nightly by .github/workflows/fill-drill-bank.yml at 02:00 Malaysia
time (18:00 UTC), when the day's use is over but the day's Groq allowance
(which resets at 00:00 UTC) still has room. Stops at max_sets (default 25),
after MAX_MINUTES, or after three failures in a row (the allowance is
probably used up) - whatever is written stays written.
"""

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("NO_BACKGROUND", "1")       # no app-side background jobs here

MAX_MINUTES = 100
READING_STOCK = 8       # unread reading passages to have ready each morning


def main(max_sets=25):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import clock
    import db_manager as db
    import drill_bank
    import hsk
    import hsk_grammar as hg
    from ahead import write_grammar_set, write_passage
    from config import HSK_TRACK_USERS

    started, written, failed_in_row = time.time(), 0, 0
    users = [u for u in db.list_users() if u["username"].lower() in HSK_TRACK_USERS]
    for user in users:
        uid = user["id"]
        order = hg.learning_order(hsk.grammar_upto(db.get_hsk_levels(uid)))
        todo = drill_bank.targets(db.grammar_progress(uid), order, clock.today())
        logging.info(f"{user['username']}: {len(todo)} structures to have ready")
        for sid in todo:
            if written >= max_sets or time.time() - started > MAX_MINUTES * 60:
                logging.info("grammar: limit reached")
                break
            t0 = time.time()
            known = db.grammar_known_vocab(uid)
            had = db.grammar_pick_set(uid, sid, len(known))
            ok = write_grammar_set(uid, sid, hsk=True)
            if had and ok:
                logging.info(f"  {sid}: ready already")
                continue
            if ok:
                written += 1
                failed_in_row = 0
                logging.info(f"  {sid}: written ({time.time() - t0:.0f}s)")
            else:
                failed_in_row += 1
                logging.warning(f"  {sid}: not written")
                if failed_in_row >= 3:
                    logging.warning("grammar: three failures in a row (allowance used up?)")
                    break
        # graded reading at the reading level: keep a stock of unread passages
        level = (db.get_hsk_levels(uid) or {}).get("read") or 1
        short = READING_STOCK - db.reading_passage_stats(uid, level)["unread"]
        for _ in range(max(0, short)):
            if time.time() - started > MAX_MINUTES * 60 or failed_in_row >= 3:
                break
            ok = write_passage(uid, level)
            logging.info(f"  passage at HSK {level}: {'written' if ok else 'not written'}")
            if not ok:
                break
    logging.info(f"done: {written} sets written")
    return written


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 25)
