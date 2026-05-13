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

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_connection():
    """Establishes a connection to the Supabase PostgreSQL database."""
    db_url = None
    if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
    elif "DATABASE_URL" in os.environ:
        db_url = os.environ["DATABASE_URL"]
    if not db_url:
        raise ValueError("CRITICAL ERROR: DATABASE_URL is missing! Streamlit cannot find it in the Secrets menu.")
    return psycopg2.connect(db_url)

def init_db():
    """Creates the vocabulary progress table in Supabase if it doesn't exist."""
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
    conn.commit()
    conn.close()
    logging.info("Supabase database initialized successfully.")

def import_vocab_from_csv():
    """Reads your local CSV, scrubs invisible errors, and uploads to Supabase."""
    if not VOCAB_CSV_PATH.exists():
        logging.warning("CSV file not found. Skipping import.")
        return

    df = pd.read_csv(VOCAB_CSV_PATH)
    df['Chinese'] = df['Chinese'].astype(str).str.strip()
    df['Pinyin'] = df['Pinyin'].astype(str).str.strip()
    df = df.replace('', pd.NA).replace('nan', pd.NA).dropna(subset=['Chinese', 'Pinyin'])

    conn = get_connection()
    cursor = conn.cursor()
    new_words_added = 0
    skipped_words = []
    today_str = date.today().isoformat()

    for index, row in df.iterrows():
        cursor.execute('''
            SELECT id FROM vocab_progress WHERE chinese = %s AND pinyin = %s
        ''', (row['Chinese'], row['Pinyin']))
        exists = cursor.fetchone()

        if not exists:
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
        logging.info(f"✅ Imported {new_words_added} new words to Supabase.")
    if skipped_words:
        logging.info(f"🚫 Skipped {len(skipped_words)} exact duplicate rows.")

def flag_word_in_database(chinese_char):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE vocab_progress SET priority_weight = priority_weight + 10 WHERE chinese = %s
    ''', (chinese_char,))
    conn.commit()
    conn.close()


# ==========================================
# NEW: Session composition — 50% random + 50% latest
# ==========================================
def get_session_words(total=MAX_REVIEWS_PER_DAY, random_pct=RANDOM_BREADTH_PCT):
    """
    Build a daily session composed of:
      - `random_pct` of `total` drawn at random across the whole vocabulary
        (for breadth of revision)
      - the remainder drawn from the most recently added entries
        (bottom-up, by id DESC)

    The two pools are deduplicated and the final list is shuffled so the user
    doesn't perceive a "random block then latest block" pattern.

    Note: this intentionally sets aside the SRS `next_review_date` for SESSION
    SELECTION purposes. Per-word SRS state is still updated when you grade,
    so individual word intervals still grow correctly — you just no longer
    *only* see words flagged due today. That's the breadth trade-off you asked for.
    """
    import random as _random  # local import to avoid shadowing

    random_count = int(round(total * random_pct))
    latest_count = total - random_count

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # 1) Latest additions
    cursor.execute('''
        SELECT * FROM vocab_progress
        ORDER BY id DESC
        LIMIT %s
    ''', (latest_count,))
    latest_rows = [dict(r) for r in cursor.fetchall()]
    latest_ids = [r['id'] for r in latest_rows]

    # 2) Random sample across the rest of the CSV
    if latest_ids:
        placeholders = ','.join(['%s'] * len(latest_ids))
        cursor.execute(f'''
            SELECT * FROM vocab_progress
            WHERE id NOT IN ({placeholders})
            ORDER BY RANDOM()
            LIMIT %s
        ''', latest_ids + [random_count])
    else:
        cursor.execute('''
            SELECT * FROM vocab_progress
            ORDER BY RANDOM()
            LIMIT %s
        ''', (random_count,))
    random_rows = [dict(r) for r in cursor.fetchall()]

    conn.close()

    session = latest_rows + random_rows
    _random.shuffle(session)
    return session


def get_due_words():
    """Legacy SRS-based fetcher. Kept so srs_engine still works if you revert."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_str = date.today().isoformat()
    cursor.execute('''
        SELECT * FROM vocab_progress
        WHERE review_count > 0 AND next_review_date <= %s
        ORDER BY priority_weight DESC, next_review_date ASC
    ''', (today_str,))
    due_reviews = [dict(row) for row in cursor.fetchall()]
    needed_new_words = MAX_REVIEWS_PER_DAY - len(due_reviews)
    if needed_new_words > 0:
        cursor.execute('''
            SELECT * FROM vocab_progress
            WHERE review_count = 0
            ORDER BY priority_weight DESC, id DESC
            LIMIT %s
        ''', (needed_new_words,))
        new_words = [dict(row) for row in cursor.fetchall()]
    else:
        new_words = []
    conn.close()
    final_batch = due_reviews + new_words
    return final_batch[:MAX_REVIEWS_PER_DAY]


def update_word_progress(word_id, next_review_date, new_interval, new_ease):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE vocab_progress
        SET next_review_date = %s,
            interval = %s,
            ease_factor = %s,
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
    total_words = cursor.fetchone()[0]
    if total_words == 0:
        conn.close()
        return {"unseen": 0, "learning": 0, "mastered": 0, "total": 0}
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE review_count = 0")
    unseen = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE interval >= 21")
    mastered = cursor.fetchone()[0]
    learning = total_words - unseen - mastered
    conn.close()
    return {"unseen": unseen, "learning": learning, "mastered": mastered, "total": total_words}

def undo_word_progress(word_id, old_next_review_date, old_interval, old_ease, old_review_count, old_priority):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE vocab_progress
        SET next_review_date = %s,
            interval = %s,
            ease_factor = %s,
            review_count = %s,
            priority_weight = %s
        WHERE id = %s
    ''', (old_next_review_date, old_interval, old_ease, old_review_count, old_priority, word_id))
    conn.commit()
    conn.close()

def get_more_words(exclude_ids, amount=5):
    """
    Fetches extra words using the same 50/50 random+latest composition,
    excluding anything we've already studied in this session.
    """
    import random as _random

    if not exclude_ids:
        exclude_ids = [-1]

    random_count = int(round(amount * RANDOM_BREADTH_PCT))
    latest_count = amount - random_count

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    exclude_placeholders = ','.join(['%s'] * len(exclude_ids))

    cursor.execute(f'''
        SELECT * FROM vocab_progress
        WHERE id NOT IN ({exclude_placeholders})
        ORDER BY id DESC
        LIMIT %s
    ''', exclude_ids + [latest_count])
    latest_rows = [dict(r) for r in cursor.fetchall()]

    all_excluded = exclude_ids + [r['id'] for r in latest_rows]
    all_placeholders = ','.join(['%s'] * len(all_excluded))

    cursor.execute(f'''
        SELECT * FROM vocab_progress
        WHERE id NOT IN ({all_placeholders})
        ORDER BY RANDOM()
        LIMIT %s
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
    cursor.execute('''
        UPDATE vocab_progress SET chinese = %s, pinyin = %s, english = %s WHERE id = %s
    ''', (new_chinese, new_pinyin, new_english, word_id))
    conn.commit()
    conn.close()

# --- Initialization Block ---
init_db()
import_vocab_from_csv()
