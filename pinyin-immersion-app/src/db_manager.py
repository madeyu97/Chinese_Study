# src/db_manager.py

import sqlite3
import pandas as pd
from datetime import datetime, date
import logging

# Import the paths we set up in config.py
from config import DB_PATH, VOCAB_CSV_PATH, MAX_REVIEWS_PER_DAY, NEW_WORDS_PER_DAY

# Set up basic logging so we can see what the database is doing in the terminal
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_connection():
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    """Creates the vocabulary progress table and applies updates if needed."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Create the base table if this is a fresh install
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chinese TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            date_added TEXT NOT NULL,
            
            -- Spaced Repetition (SRS) Columns
            next_review_date TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Add the Priority Weight column if it doesn't exist yet (Migration)
    try:
        cursor.execute("ALTER TABLE vocab_progress ADD COLUMN priority_weight INTEGER DEFAULT 1")
        logging.info("Database migration: Added 'priority_weight' column.")
    except sqlite3.OperationalError:
        # The column already exists, which is fine!
        pass
    
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

def import_vocab_from_csv():
    """Reads vocab_export.csv and adds new words to the database."""
    if not VOCAB_CSV_PATH.exists():
        logging.warning(f"CSV file not found at {VOCAB_CSV_PATH}. Skipping import.")
        return

    df = pd.read_csv(VOCAB_CSV_PATH)
    conn = get_connection()
    cursor = conn.cursor()
    
    new_words_added = 0
    today_str = date.today().isoformat()

    for index, row in df.iterrows():
        cursor.execute("SELECT id FROM vocab_progress WHERE pinyin = ?", (row['Pinyin'],))
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute('''
                INSERT INTO vocab_progress 
                (chinese, pinyin, english, date_added, next_review_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (row['Chinese'], row['Pinyin'], row['English'], today_str, today_str))
            new_words_added += 1

    conn.commit()
    conn.close()
    logging.info(f"Import complete: {new_words_added} new words added to the database.")

# ==========================================
# NEW: PRIORITY FLAGGING SYSTEM
# ==========================================
def flag_word_in_database(chinese_char):
    """Bumps a word to the front of the queue by massively increasing its priority weight."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE vocab_progress 
        SET priority_weight = priority_weight + 10 
        WHERE chinese = ?
    ''', (chinese_char,))
    
    conn.commit()
    conn.close()
    logging.info(f"Priority boosted for word: {chinese_char}")

def get_due_words():
    """Fetches due words, aggressively prioritizing flagged words first."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    today_str = date.today().isoformat()
    
    # Sorted by Priority FIRST, then by urgency (review date)
    cursor.execute('''
        SELECT * FROM vocab_progress 
        WHERE next_review_date <= ? 
        ORDER BY priority_weight DESC, next_review_date ASC, review_count ASC
        LIMIT ?
    ''', (today_str, MAX_REVIEWS_PER_DAY))
    
    due_words = cursor.fetchall()
    conn.close()
    return [dict(word) for word in due_words]

def update_word_progress(word_id, next_review_date, new_interval, new_ease):
    """
    Updates SRS stats and acts as a "cool down" for flagged words.
    Every time you review it, the priority weight drops until it normalizes at 1.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE vocab_progress
        SET next_review_date = ?, 
            interval = ?, 
            ease_factor = ?, 
            review_count = review_count + 1,
            priority_weight = MAX(1, priority_weight - 2)
        WHERE id = ?
    ''', (next_review_date, new_interval, new_ease, word_id))
    
    conn.commit()
    conn.close()
    logging.info(f"Updated word ID {word_id}. Next review: {next_review_date}.")

# ==========================================
# NEW: PROGRESS TRACKING STATS
# ==========================================
def get_progress_stats():
    """Calculates the percentage of words Unseen, Learning, and Mastered."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total words imported from your CSV
    cursor.execute("SELECT COUNT(*) FROM vocab_progress")
    total_words = cursor.fetchone()[0]
    
    if total_words == 0:
        return {"unseen": 0, "learning": 0, "mastered": 0, "total": 0}

    # Unseen: Never reviewed
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE review_count = 0")
    unseen = cursor.fetchone()[0]

    # Mastered: Interval pushed out 21 days or more (Standard SRS 'Mature' card)
    cursor.execute("SELECT COUNT(*) FROM vocab_progress WHERE interval >= 21")
    mastered = cursor.fetchone()[0]

    # Learning: Everything in between
    learning = total_words - unseen - mastered
    
    conn.close()
    
    return {
        "unseen": unseen,
        "learning": learning,
        "mastered": mastered,
        "total": total_words
    }

# --- Initialization Block ---
init_db()
import_vocab_from_csv()