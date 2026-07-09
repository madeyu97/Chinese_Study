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
from handwriting_engine import score_character, get_stroke_count, compute_next_review

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_connection():
    db_url = None
    # st.secrets RAISES (rather than returning False) when no secrets file
    # exists at all — which is the normal case when running the batch
    # script locally with DATABASE_URL as an env var.
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
            first_seen_date TEXT NOT NULL
        )
    ''')
    # Vetted sentence bank: exercises are generated ONCE (batch script or
    # first live use), validated, stored here, and re-served from then on.
    # Study sessions never depend on a fresh LLM roll of the dice.
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
    # Learner-flagged sentences: never shown or regenerated again, and fed
    # back into the generation/review prompts as negative examples.
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
    # A missing English cell arrives as float NaN, which crashes the TEXT
    # column insert — coerce to a clean string instead.
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

    # 1. Pull all vocab the user is actively studying (or has mastered)
    cursor.execute("SELECT chinese FROM vocab_progress WHERE review_count > 0")
    rows = cursor.fetchall()

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
                due_reviews.append({
                    "character": ch,
                    "is_new": False,
                    "personal_freq": char_freq[ch],
                    "interval": progress_map[ch]['interval'],
                    "ease_factor": float(progress_map[ch]['ease_factor']),
                    "review_count": progress_map[ch]['review_count'],
                    "next_review_date": progress_map[ch]['next_review_date'],
                    "stroke_count": get_stroke_count(ch),
                })
        else:
            new_candidates.append(ch)

    # 5. Rank new candidates by priority score
    new_candidates.sort(key=lambda ch: score_character(ch, char_freq[ch]))
    selected_new = new_candidates[:new_count]
    new_entries = [{
        "character": ch,
        "is_new": True,
        "personal_freq": char_freq[ch],
        "interval": 0,
        "ease_factor": 2.5,
        "review_count": 0,
        "next_review_date": today_str,
        "stroke_count": get_stroke_count(ch),
    } for ch in selected_new]

    # Due reviews first, then new chars (so you warm up on familiar ground)
    return due_reviews + new_entries


def update_handwriting_progress(character, grade, current_state):
    """Apply SRS grade to a character and upsert progress."""
    new_interval, new_ease, next_review_date = compute_next_review(
        current_interval=current_state.get('interval', 0),
        current_ease=current_state.get('ease_factor', 2.5),
        grade=grade,
    )
    today_str = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO handwriting_progress
            (character, next_review_date, interval, ease_factor, review_count, first_seen_date)
        VALUES (%s, %s, %s, %s, 1, %s)
        ON CONFLICT (character) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = handwriting_progress.review_count + 1
    ''', (character, next_review_date, new_interval, new_ease, today_str))
    conn.commit()
    conn.close()
    logging.info(f"[HW] {character} graded {grade} → next review in {new_interval}d")


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
    """Store a validated exercise. Audio paths are per-machine so they are
    stripped; audio is regenerated from text on demand (and cached)."""
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
        (vocab_chinese, ex.get("chinese", ""),
         psycopg2.extras.Json(ex)))
    added = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return added


def bank_get(vocab_chinese):
    """Serve a vetted exercise for this vocab item: least-used first so
    variety cycles, random among ties. Returns the exercise dict or None."""
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
    """Learner hit the flag button: retire the sentence everywhere."""
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


def get_blocklist():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese FROM sentence_blocklist")
    rows = {r[0] for r in cursor.fetchall()}
    conn.close()
    return rows


def get_recent_flags(limit=8):
    """(sentence, reason) pairs, newest first — injected into generation and
    review prompts so every flag permanently strengthens the pipeline."""
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
    return {"active_sentences": active, "flagged": flagged,
            "vocab_covered": covered, "vocab_total": total_vocab}


def bank_count_for(vocab_chinese):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sentence_bank "
                   "WHERE vocab_chinese = %s AND status = 'active'",
                   (vocab_chinese,))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def unflag_sentence(chinese_sentence):
    """Curation: restore a sentence that was flagged by mistake."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sentence_blocklist WHERE chinese = %s",
                   (chinese_sentence,))
    cursor.execute("UPDATE sentence_bank SET status = 'active' "
                   "WHERE chinese = %s", (chinese_sentence,))
    conn.commit()
    conn.close()


def bank_browse(vocab_chinese=None, status='active', limit=50):
    """List bank rows for the curation page, newest first."""
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


init_db()
import_vocab_from_csv()
