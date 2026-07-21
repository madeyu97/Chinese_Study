# src/db_manager.py

import os
import pandas as pd
from datetime import datetime, date
import logging
import psycopg2
import psycopg2.extras
import streamlit as st

from config import (
    VOCAB_CSV_PATH,
    MAX_REVIEWS_PER_DAY,
    NEW_WORDS_PER_DAY,
    RANDOM_BREADTH_PCT,
)
from handwriting_engine import (score_character, get_stroke_count,
                                compute_next_review, choose_context_word)
from dictionary_engine import derive_pinyin, cedict_gloss

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_connection():
    db_url = None
    try:
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            db_url = st.secrets["DATABASE_URL"]
    except Exception:
        pass
    if not db_url and "DATABASE_URL" in os.environ:
        db_url = os.environ["DATABASE_URL"]
    if not db_url:
        raise ValueError("CRITICAL ERROR: DATABASE_URL is missing!")
    return psycopg2.connect(db_url)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab_progress (
            id SERIAL PRIMARY KEY,
            chinese TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            date_added TEXT NOT NULL,
            next_review_date TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            priority_weight INTEGER DEFAULT 1
        )
    ''')
    # NEW: handwriting progress
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS handwriting_progress (
            id SERIAL PRIMARY KEY,
            character TEXT UNIQUE NOT NULL,
            next_review_date TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            first_seen_date TEXT NOT NULL,
            total_mistakes INTEGER DEFAULT 0,
            recent_grades TEXT DEFAULT '',
            recent_mistakes TEXT DEFAULT '',
            last_reviewed TEXT
        )
    ''')
    # Backfill struggle-tracking columns on databases created before this
    # feature (CREATE TABLE IF NOT EXISTS never alters an existing table).
    for _coldef in ("total_mistakes INTEGER DEFAULT 0",
                    "recent_grades TEXT DEFAULT ''",
                    "recent_mistakes TEXT DEFAULT ''",
                    "last_reviewed TEXT"):
        cursor.execute(
            "ALTER TABLE handwriting_progress "
            "ADD COLUMN IF NOT EXISTS " + _coldef)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentence_bank (
            id SERIAL PRIMARY KEY,
            vocab_chinese TEXT NOT NULL,
            chinese TEXT NOT NULL UNIQUE,
            exercise JSONB NOT NULL,
            status TEXT DEFAULT 'active',
            times_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_bank_vocab
        ON sentence_bank (vocab_chinese, status)
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentence_blocklist (
            chinese TEXT PRIMARY KEY,
            reason TEXT,
            flagged_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Supabase database initialized successfully.")

def import_vocab_from_csv():
    if not VOCAB_CSV_PATH.exists():
        logging.warning("CSV file not found. Skipping import.")
        return
    df = pd.read_csv(VOCAB_CSV_PATH)
    df['Chinese'] = df['Chinese'].astype(str).str.strip()
    df['Pinyin'] = df['Pinyin'].astype(str).str.strip()
    df = df.replace('', pd.NA).replace('nan', pd.NA).dropna(subset=['Chinese', 'Pinyin'])
    df['English'] = df['English'].fillna('').astype(str).str.strip()

    conn = get_connection()
    cursor = conn.cursor()
    new_words_added = 0
    skipped_words = []
    today_str = date.today().isoformat()

    for index, row in df.iterrows():
        cursor.execute('SELECT id FROM vocab_progress WHERE chinese = %s AND pinyin = %s',
                       (row['Chinese'], row['Pinyin']))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO vocab_progress
                (chinese, pinyin, english, date_added, next_review_date)
                VALUES (%s, %s, %s, %s, %s)
            ''', (row['Chinese'], row['Pinyin'], row['English'], today_str, today_str))
            new_words_added += 1
        else:
            skipped_words.append(row['Chinese'])
    conn.commit()
    conn.close()
    if new_words_added > 0:
        logging.info(f"Imported {new_words_added} new words.")
    if skipped_words:
        logging.info(f"Skipped {len(skipped_words)} duplicates.")

def flag_word_in_database(chinese_char):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE vocab_progress SET priority_weight = priority_weight + 10 WHERE chinese = %s',
                   (chinese_char,))
    conn.commit()
    conn.close()


def get_session_words(total=MAX_REVIEWS_PER_DAY, random_pct=RANDOM_BREADTH_PCT):
    import random as _random
    random_count = int(round(total * random_pct))
    latest_count = total - random_count
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT * FROM vocab_progress ORDER BY id DESC LIMIT %s', (latest_count,))
    latest_rows = [dict(r) for r in cursor.fetchall()]
    latest_ids = [r['id'] for r in latest_rows]
    if latest_ids:
        placeholders = ','.join(['%s'] * len(latest_ids))
        cursor.execute(f'''
            SELECT * FROM vocab_progress
            WHERE id NOT IN ({placeholders})
            ORDER BY RANDOM() LIMIT %s
        ''', latest_ids + [random_count])
    else:
        cursor.execute('SELECT * FROM vocab_progress ORDER BY RANDOM() LIMIT %s', (random_count,))
    random_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    session = latest_rows + random_rows
    _random.shuffle(session)
    return session

def get_due_words():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_str = date.today().isoformat()
    cursor.execute('''
        SELECT * FROM vocab_progress WHERE review_count > 0 AND next_review_date <= %s
        ORDER BY priority_weight DESC, next_review_date ASC
    ''', (today_str,))
    due_reviews = [dict(row) for row in cursor.fetchall()]
    needed = MAX_REVIEWS_PER_DAY - len(due_reviews)
    if needed > 0:
        cursor.execute('''
            SELECT * FROM vocab_progress WHERE review_count = 0
            ORDER BY priority_weight DESC, id DESC LIMIT %s
        ''', (needed,))
        new_words = [dict(row) for row in cursor.fetchall()]
    else:
        new_words = []
    conn.close()
    return (due_reviews + new_words)[:MAX_REVIEWS_PER_DAY]

def update_word_progress(word_id, next_review_date, new_interval, new_ease):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE vocab_progress
        SET next_review_date = %s, interval = %s, ease_factor = %s,
            review_count = review_count + 1,
            priority_weight = GREATEST(1, priority_weight - 2)
        WHERE id = %s
    ''', (next_review_date, new_interval, new_ease, word_id))
    conn.commit()
    conn.close()

def get_progress_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vocab_progress")
    total = cursor.fetchone()[0]
    if total == 0:
        conn.close()
        return {"unseen": 0, "learning": 0, "mastered": 0, "total": 0}
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE review_count = 0")
    unseen = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE interval >= 21")
    mastered = cursor.fetchone()[0]
    conn.close()
    return {"unseen": unseen, "learning": total - unseen - mastered, "mastered": mastered, "total": total}

def undo_word_progress(word_id, old_next_review_date, old_interval, old_ease, old_review_count, old_priority):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE vocab_progress
        SET next_review_date = %s, interval = %s, ease_factor = %s,
            review_count = %s, priority_weight = %s
        WHERE id = %s
    ''', (old_next_review_date, old_interval, old_ease, old_review_count, old_priority, word_id))
    conn.commit()
    conn.close()

def get_more_words(exclude_ids, amount=5):
    import random as _random
    if not exclude_ids:
        exclude_ids = [-1]
    random_count = int(round(amount * RANDOM_BREADTH_PCT))
    latest_count = amount - random_count
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    exclude_placeholders = ','.join(['%s'] * len(exclude_ids))
    cursor.execute(f'''
        SELECT * FROM vocab_progress WHERE id NOT IN ({exclude_placeholders})
        ORDER BY id DESC LIMIT %s
    ''', exclude_ids + [latest_count])
    latest_rows = [dict(r) for r in cursor.fetchall()]
    all_excluded = exclude_ids + [r['id'] for r in latest_rows]
    all_placeholders = ','.join(['%s'] * len(all_excluded))
    cursor.execute(f'''
        SELECT * FROM vocab_progress WHERE id NOT IN ({all_placeholders})
        ORDER BY RANDOM() LIMIT %s
    ''', all_excluded + [random_count])
    random_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    extra = latest_rows + random_rows
    _random.shuffle(extra)
    return extra[:amount]

def delete_word_from_db(word_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vocab_progress WHERE id = %s", (word_id,))
    conn.commit()
    conn.close()

def update_word_in_db(word_id, new_chinese, new_pinyin, new_english):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE vocab_progress SET chinese = %s, pinyin = %s, english = %s WHERE id = %s',
                   (new_chinese, new_pinyin, new_english, word_id))
    conn.commit()
    conn.close()


# ======================================================================
# HANDWRITING FUNCTIONS
# ======================================================================

def _is_cjk(ch):
    return '\u4e00' <= ch <= '\u9fff'


def _hw_entry(ch, is_new, personal_freq, progress, vocab_rows):
    """Build one drill-queue entry, including the semantic recall cue: the
    best-known vocab word containing this character, its pinyin and meaning,
    and the character's own pinyin. The character itself is the ANSWER and
    is only ever rendered by HanziWriter inside the drill component."""
    ctx = choose_context_word(ch, vocab_rows) or {}
    return {
        "character": ch,
        "is_new": is_new,
        "personal_freq": personal_freq,
        "interval": (progress or {}).get("interval", 0),
        "ease_factor": float((progress or {}).get("ease_factor", 2.5)),
        "review_count": (progress or {}).get("review_count", 0),
        "next_review_date": (progress or {}).get(
            "next_review_date", date.today().isoformat()),
        "stroke_count": get_stroke_count(ch),
        "char_pinyin": derive_pinyin(ch),
        "word": ctx.get("chinese", ch),
        "word_pinyin": ctx.get("pinyin", ""),
        "word_english": ctx.get("english", ""),
    }


def get_focus_session(text):
    """Drill exactly the CJK characters of `text`, regardless of due dates."""
    chars = []
    for ch in text:
        if _is_cjk(ch) and ch not in chars:
            chars.append(ch)
    if not chars:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT chinese, pinyin, english, review_count
                      FROM vocab_progress""")
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    placeholders = ','.join(['%s'] * len(chars))
    cursor.execute(f"SELECT * FROM handwriting_progress "
                   f"WHERE character IN ({placeholders})", chars)
    progress_map = {r['character']: dict(r) for r in cursor.fetchall()}
    conn.close()
    focus_row = next((w for w in vocab_rows if w["chinese"] == text), None)
    session = []
    for ch in chars:
        prog = progress_map.get(ch)
        entry = _hw_entry(ch, prog is None, 1, prog, vocab_rows)
        if focus_row:
            entry.update(word=focus_row["chinese"],
                         word_pinyin=focus_row["pinyin"],
                         word_english=focus_row["english"])
        elif entry["word"] == ch and not entry["word_english"]:
            gloss = cedict_gloss(ch)[0]
            entry.update(word=text, word_pinyin=derive_pinyin(text),
                         word_english=gloss)
        session.append(entry)
    return session


def get_handwriting_counts():
    """(due_reviews, new_available) for the session setup screen."""
    session = get_handwriting_session(new_count=10**6)
    due = sum(1 for e in session if not e["is_new"])
    new = sum(1 for e in session if e["is_new"])
    return due, new


def get_handwriting_session(new_count=5):
    """
    Build a daily handwriting session from your studying + mastered vocab.

    Returns a list of dicts, each like:
      {"character": "好", "is_new": True, "personal_freq": 8,
       "interval": 0, "ease_factor": 2.5, "review_count": 0,
       "stroke_count": 6, "next_review_date": "..."}

    Composition:
      - All chars whose next_review_date <= today (due reviews)
      - Up to `new_count` brand-new chars, ordered by priority score
        (low stroke count + high personal frequency = top priority)
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_str = date.today().isoformat()

    # 1. Pull all vocab the user is actively studying (or has mastered),
    #    with pinyin/english so each character can carry its word context.
    cursor.execute("""SELECT chinese, pinyin, english, review_count
                      FROM vocab_progress WHERE review_count > 0""")
    rows = [dict(r) for r in cursor.fetchall()]

    if not rows:
        conn.close()
        return []

    # 2. Count personal frequency of each unique CJK character
    char_freq = {}
    for r in rows:
        for ch in r['chinese']:
            if _is_cjk(ch):
                char_freq[ch] = char_freq.get(ch, 0) + 1

    if not char_freq:
        conn.close()
        return []

    unique_chars = list(char_freq.keys())

    # 3. Fetch existing handwriting progress for those chars
    placeholders = ','.join(['%s'] * len(unique_chars))
    cursor.execute(f'''
        SELECT * FROM handwriting_progress WHERE character IN ({placeholders})
    ''', unique_chars)
    progress_map = {row['character']: dict(row) for row in cursor.fetchall()}
    conn.close()

    # 4. Split into due reviews + new candidates
    due_reviews = []
    new_candidates = []
    for ch in unique_chars:
        if ch in progress_map:
            if progress_map[ch]['next_review_date'] <= today_str:
                due_reviews.append(_hw_entry(ch, False, char_freq[ch],
                                             progress_map[ch], rows))
        else:
            new_candidates.append(ch)

    # 5. Rank new candidates by priority score
    new_candidates.sort(key=lambda ch: score_character(ch, char_freq[ch]))
    selected_new = new_candidates[:new_count]
    new_entries = [_hw_entry(ch, True, char_freq[ch], None, rows)
                   for ch in selected_new]

    # Due reviews first, then new chars (so you warm up on familiar ground)
    return due_reviews + new_entries


RECENT_WINDOW = 5          # attempts kept for the "recent mistake rate" ranking
REQUEUE_MISTAKE_THRESHOLD = 4   # >3 mistakes forces same-day requeue + next-day review


def _push_recent(csv_str, value, window=RECENT_WINDOW):
    """Append an int to a comma-string, keep only the last `window`."""
    items = [x for x in (csv_str or "").split(",") if x != ""]
    items.append(str(int(value)))
    items = items[-window:]
    return ",".join(items)


def update_handwriting_progress(character, grade, current_state, mistakes=0):
    """Apply SRS grade to a character, record mistake history, and upsert.

    Returns True if the character should be REQUEUED in the same session
    (more than 3 mistakes) — the caller uses this to re-drill it a few
    cards later, and its next scheduled review is pinned to tomorrow so a
    struggled character never disappears for days.
    """
    requeue = mistakes >= REQUEUE_MISTAKE_THRESHOLD
    new_interval, new_ease, next_review_date = compute_next_review(
        current_interval=current_state.get('interval', 0),
        current_ease=current_state.get('ease_factor', 2.5),
        grade=grade,
    )
    today_str = date.today().isoformat()

    if requeue:
        # Even a later-clean requeue can't push it past tomorrow.
        from datetime import timedelta
        next_review_date = (date.today() + timedelta(days=1)).isoformat()
        new_interval = min(new_interval, 1)

    prev_grades = current_state.get('recent_grades', '') or ''
    prev_mist = current_state.get('recent_mistakes', '') or ''
    new_grades = _push_recent(prev_grades, grade)
    new_mist = _push_recent(prev_mist, mistakes)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO handwriting_progress
            (character, next_review_date, interval, ease_factor, review_count,
             first_seen_date, total_mistakes, recent_grades, recent_mistakes,
             last_reviewed)
        VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
        ON CONFLICT (character) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = handwriting_progress.review_count + 1,
            total_mistakes = handwriting_progress.total_mistakes + EXCLUDED.total_mistakes,
            recent_grades = EXCLUDED.recent_grades,
            recent_mistakes = EXCLUDED.recent_mistakes,
            last_reviewed = EXCLUDED.last_reviewed
    ''', (character, next_review_date, new_interval, new_ease, today_str,
           mistakes, new_grades, new_mist, today_str))
    conn.commit()
    conn.close()
    logging.info(f"[HW] {character} graded {grade} ({mistakes} mistakes) "
                 f"→ next review in {new_interval}d"
                 + (" [REQUEUED this session]" if requeue else ""))
    return requeue


def get_handwriting_stats():
    """Counts for the handwriting sidebar widget."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total unique chars across studying+mastered vocab
    cursor.execute("SELECT chinese FROM vocab_progress WHERE review_count > 0")
    rows = cursor.fetchall()
    unique_chars = set()
    for r in rows:
        for ch in r[0]:
            if _is_cjk(ch):
                unique_chars.add(ch)
    total = len(unique_chars)

    cursor.execute("SELECT COUNT(*) FROM handwriting_progress")
    practiced = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM handwriting_progress WHERE interval >= 21")
    mastered = cursor.fetchone()[0]

    conn.close()
    return {
        "total_chars_available": total,
        "practiced": practiced,
        "mastered": mastered,
        "unseen": max(0, total - practiced),
    }


# --- Initialization ---

# ==========================================
# SENTENCE BANK + BLOCKLIST
# ==========================================
import json as _json


def bank_add(vocab_chinese, exercise):
    ex = {k: v for k, v in exercise.items() if k != "audio_path"}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sentence_blocklist WHERE chinese = %s",
                   (ex.get("chinese", ""),))
    if cursor.fetchone():
        conn.close()
        return False
    cursor.execute(
        """INSERT INTO sentence_bank (vocab_chinese, chinese, exercise)
           VALUES (%s, %s, %s) ON CONFLICT (chinese) DO NOTHING""",
        (vocab_chinese, ex.get("chinese", ""), psycopg2.extras.Json(ex)))
    added = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return added


def bank_get(vocab_chinese):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(
        """SELECT id, exercise FROM sentence_bank
           WHERE vocab_chinese = %s AND status = 'active'
             AND chinese NOT IN (SELECT chinese FROM sentence_blocklist)
           ORDER BY times_used ASC, RANDOM() LIMIT 1""",
        (vocab_chinese,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    cursor.execute("UPDATE sentence_bank SET times_used = times_used + 1 "
                   "WHERE id = %s", (row["id"],))
    conn.commit()
    conn.close()
    exercise = row["exercise"]
    if isinstance(exercise, str):
        exercise = _json.loads(exercise)
    return exercise


def flag_sentence(chinese_sentence, reason="flagged by learner"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sentence_bank SET status = 'flagged' "
                   "WHERE chinese = %s", (chinese_sentence,))
    cursor.execute(
        """INSERT INTO sentence_blocklist (chinese, reason) VALUES (%s, %s)
           ON CONFLICT (chinese) DO NOTHING""",
        (chinese_sentence, reason))
    conn.commit()
    conn.close()
    logging.info(f"[FLAG] Retired sentence: {chinese_sentence}")


def unflag_sentence(chinese_sentence):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sentence_blocklist WHERE chinese = %s",
                   (chinese_sentence,))
    cursor.execute("UPDATE sentence_bank SET status = 'active' "
                   "WHERE chinese = %s", (chinese_sentence,))
    conn.commit()
    conn.close()


def get_blocklist():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese FROM sentence_blocklist")
    rows = {r[0] for r in cursor.fetchall()}
    conn.close()
    return rows


def get_recent_flags(limit=8):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese, COALESCE(reason, '') FROM sentence_blocklist "
                   "ORDER BY flagged_at DESC LIMIT %s", (limit,))
    rows = [(r[0], r[1]) for r in cursor.fetchall()]
    conn.close()
    return rows


def bank_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FILTER (WHERE status = 'active'),
               COUNT(*) FILTER (WHERE status = 'flagged'),
               COUNT(DISTINCT vocab_chinese) FILTER (WHERE status = 'active')
        FROM sentence_bank""")
    active, flagged, covered = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM vocab_progress")
    total_vocab = cursor.fetchone()[0]
    conn.close()
    return {"active_sentences": active or 0, "flagged": flagged or 0,
            "vocab_covered": covered or 0, "vocab_total": total_vocab or 0}


def bank_count_for(vocab_chinese):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sentence_bank "
                   "WHERE vocab_chinese = %s AND status = 'active'",
                   (vocab_chinese,))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def bank_browse(vocab_chinese=None, status='active', limit=50):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if vocab_chinese:
        cursor.execute(
            """SELECT vocab_chinese, chinese, exercise, status, times_used
               FROM sentence_bank WHERE vocab_chinese = %s AND status = %s
               ORDER BY created_at DESC LIMIT %s""",
            (vocab_chinese, status, limit))
    else:
        cursor.execute(
            """SELECT vocab_chinese, chinese, exercise, status, times_used
               FROM sentence_bank WHERE status = %s
               ORDER BY created_at DESC LIMIT %s""",
            (status, limit))
    rows = []
    for r in cursor.fetchall():
        ex = r["exercise"]
        if isinstance(ex, str):
            ex = _json.loads(ex)
        rows.append({"vocab_chinese": r["vocab_chinese"], "chinese": r["chinese"],
                     "exercise": ex, "status": r["status"],
                     "times_used": r["times_used"]})
    conn.close()
    return rows




# ==========================================
# STRUGGLE TRACKING — weakness ranking + focused drills
# ==========================================
def _recent_mistake_rate(recent_mistakes_csv):
    """Mean mistakes over the recent window (0 if no history)."""
    vals = [int(x) for x in (recent_mistakes_csv or "").split(",") if x != ""]
    return sum(vals) / len(vals) if vals else 0.0


def get_weak_characters(limit=50, min_attempts=1):
    """Characters ranked by RECENT struggle, worst first.

    Ranking key is the recent mistake rate (mean mistakes over the last
    ~5 attempts), so a character you've improved on naturally falls down
    the list. Ties broken by recent Again/Hard grades, then lifetime
    mistakes. Only characters with at least `min_attempts` recorded
    attempts are included."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT character, review_count, total_mistakes, recent_grades,
               recent_mistakes, next_review_date, interval, ease_factor
        FROM handwriting_progress
        WHERE review_count >= %s
    """, (min_attempts,))
    rows = [dict(r) for r in cursor.fetchall()]

    # pull word context for the cue, same as the normal session
    cursor.execute("""SELECT chinese, pinyin, english, review_count
                      FROM vocab_progress WHERE review_count > 0""")
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    ranked = []
    for r in rows:
        rate = _recent_mistake_rate(r.get("recent_mistakes"))
        if rate <= 0 and not [g for g in (r.get("recent_grades") or "").split(",")
                              if g in ("0", "1")]:
            continue  # no recent struggle at all — not "weak"
        recent_bad = sum(1 for g in (r.get("recent_grades") or "").split(",")
                         if g in ("0", "1"))
        r["_rate"] = rate
        r["_recent_bad"] = recent_bad
        ranked.append(r)

    ranked.sort(key=lambda r: (-r["_rate"], -r["_recent_bad"],
                               -(r.get("total_mistakes") or 0)))
    ranked = ranked[:limit]

    out = []
    for r in ranked:
        ctx = choose_context_word(r["character"], vocab_rows) or {}
        out.append({
            "character": r["character"],
            "recent_mistake_rate": round(r["_rate"], 2),
            "recent_bad_grades": r["_recent_bad"],
            "total_mistakes": r.get("total_mistakes") or 0,
            "review_count": r.get("review_count") or 0,
            "char_pinyin": derive_pinyin(r["character"]),
            "word": ctx.get("chinese", r["character"]),
            "word_pinyin": ctx.get("pinyin", ""),
            "word_english": ctx.get("english", ""),
            # carry SRS state so a drill here still updates the schedule
            "interval": r.get("interval", 0),
            "ease_factor": float(r.get("ease_factor", 2.5)),
            "next_review_date": r.get("next_review_date"),
            "recent_grades": r.get("recent_grades", ""),
            "recent_mistakes": r.get("recent_mistakes", ""),
            "is_new": False,
        })
    return out


def get_struggle_session(characters):
    """Build a drill queue for an explicit list of characters (the
    'drill my weak characters' mode). Each character carries full state so
    grades still feed the SRS. Order preserved as given."""
    if not characters:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT chinese, pinyin, english, review_count
                      FROM vocab_progress""")
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    ph = ','.join(['%s'] * len(characters))
    cursor.execute(f"SELECT * FROM handwriting_progress WHERE character IN ({ph})",
                   characters)
    pmap = {r['character']: dict(r) for r in cursor.fetchall()}
    conn.close()
    session = []
    for ch in characters:
        session.append(_hw_entry(ch, pmap.get(ch) is None, 1,
                                 pmap.get(ch), vocab_rows))
    return session




def get_char_state(character):
    """Current stored handwriting state for one character (or None), used to
    roll recent-grade/mistake history correctly across repeated drills."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM handwriting_progress WHERE character = %s",
                   (character,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


init_db()
import_vocab_from_csv()
