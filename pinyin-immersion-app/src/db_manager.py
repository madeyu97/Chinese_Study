# src/db_manager.py

import os
import pandas as pd
from datetime import datetime, date
import logging
import psycopg2
import psycopg2.extras
import streamlit as st

# Import the paths we set up in config.py
from config import VOCAB_CSV_PATH, MAX_REVIEWS_PER_DAY, NEW_WORDS_PER_DAY

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_connection():
    """Establishes a connection to the Supabase PostgreSQL database."""
    db_url = None
    
    # 1. Safely check if Streamlit Secrets has the URL
    if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
        
    # 2. If not found in secrets, try looking at local environment variables (.env fallback)
    elif "DATABASE_URL" in os.environ:
        db_url = os.environ["DATABASE_URL"]
        
    # 3. If it's STILL missing, throw a clean, human-readable error
    if not db_url:
        raise ValueError("CRITICAL ERROR: DATABASE_URL is missing! Streamlit cannot find it in the Secrets menu.")

    return psycopg2.connect(db_url)
def init_db():
    """Creates the vocabulary progress table in Supabase if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Notice: 'AUTOINCREMENT' is 'SERIAL' in PostgreSQL
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
    """Reads your local CSV and uploads it to Supabase."""
    if not VOCAB_CSV_PATH.exists():
        logging.warning("CSV file not found. Skipping import.")
        return

    df = pd.read_csv(VOCAB_CSV_PATH)
    
    # Drop completely empty rows from the CSV just in case
    df = df.dropna(subset=['Chinese', 'Pinyin']) 
    
    conn = get_connection()
    cursor = conn.cursor()
    
    new_words_added = 0
    today_str = date.today().isoformat()

    for index, row in df.iterrows():
        # FIXED: Require BOTH the Chinese and the Pinyin to match to be considered a duplicate.
        cursor.execute('''
            SELECT id FROM vocab_progress 
            WHERE chinese = %s AND pinyin = %s
        ''', (row['Chinese'], row['Pinyin']))
        
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute('''
                INSERT INTO vocab_progress 
                (chinese, pinyin, english, date_added, next_review_date)
                VALUES (%s, %s, %s, %s, %s)
            ''', (row['Chinese'], row['Pinyin'], row['English'], today_str, today_str))
            new_words_added += 1

    conn.commit()
    conn.close()
    if new_words_added > 0:
        logging.info(f"Imported {new_words_added} new words to Supabase.")

def get_due_words():
    """Fetches a proper mix of due reviews and new words to hit the daily max."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_str = date.today().isoformat()
    
    # 1. Fetch Due Reviews (Words you've seen before that are scheduled for today)
    cursor.execute('''
        SELECT * FROM vocab_progress 
        WHERE review_count > 0 AND next_review_date <= %s 
        ORDER BY priority_weight DESC, next_review_date ASC
    ''', (today_str,))
    due_reviews = [dict(row) for row in cursor.fetchall()]
    
    # 2. FIXED: Dynamically calculate how many new words we need to hit the max
    needed_new_words = MAX_REVIEWS_PER_DAY - len(due_reviews)
    
    if needed_new_words > 0:
        cursor.execute('''
            SELECT * FROM vocab_progress 
            WHERE review_count = 0 
            ORDER BY priority_weight DESC, id ASC
            LIMIT %s
        ''', (needed_new_words,))
        new_words = [dict(row) for row in cursor.fetchall()]
    else:
        new_words = []
    
    conn.close()
    
    # Combine them
    final_batch = due_reviews + new_words
    
    return final_batch[:MAX_REVIEWS_PER_DAY]
    
def update_word_progress(word_id, next_review_date, new_interval, new_ease):
    """Updates SRS stats and applies the priority cool-down."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Notice: Postgres uses GREATEST instead of MAX
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
    """Calculates your learning stats directly from the cloud."""
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
    
    return {
        "unseen": unseen,
        "learning": learning,
        "mastered": mastered,
        "total": total_words
    }

def undo_word_progress(word_id, old_next_review_date, old_interval, old_ease, old_review_count, old_priority):
    """Reverts a word's progress back to its exact state before the user graded it."""
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

# --- Initialization Block ---
init_db()
import_vocab_from_csv()
