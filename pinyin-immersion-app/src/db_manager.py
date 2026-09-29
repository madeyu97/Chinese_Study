# src/db_manager.py

import os
import re
import json
import hashlib
import unicodedata
import threading
import pandas as pd
from datetime import datetime, date
import logging
import psycopg2
import psycopg2.extras
from psycopg2 import pool
import streamlit as st

from config import (
    PRECISION_RELAPSE,
    VOCAB_CSV_PATH,
    FREQUENCY_CSV_PATH,
    FREQUENCY_RANKS_PATH,
    MAX_REVIEWS_PER_DAY,
    NEW_WORDS_PER_DAY,
    RANDOM_BREADTH_PCT,
)
from handwriting_engine import (precision_for, precision_level,
                                score_character, get_stroke_count,
                                compute_next_review, choose_context_word)
from dictionary_engine import (derive_pinyin, cedict_gloss,
                               character_info, frequency_label,
                               has_erhua, strip_erhua)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

_POOL = None
_POOL_LOCK = threading.Lock()


def _database_url():
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
    return db_url


class _PooledConnection:
    """Looks like a psycopg2 connection, but close() returns it to the pool.

    PERFORMANCE: every data function in this module opens a connection and
    closes it, and Streamlit re-runs the whole script on every interaction -
    so a single click used to mean 3-11 fresh TLS handshakes to Supabase.
    Pooling keeps them open and reuses them, which removes most of the
    per-click lag without touching any calling code.
    """

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._returned = False

    def close(self):
        if self._returned:
            return
        self._returned = True
        try:
            if not self._conn.closed:
                # Drop any transaction the caller left open, so the next
                # borrower starts clean.
                self._conn.rollback()
                self._pool.putconn(self._conn)
            else:
                self._pool.putconn(self._conn, close=True)
        except Exception:
            try:
                self._pool.putconn(self._conn, close=True)
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _get_pool():
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = pool.ThreadedConnectionPool(
                    minconn=1, maxconn=10, dsn=_database_url())
    return _POOL


def reset_pool():
    """Drop every pooled connection. Used when the database has gone away
    (Supabase closes idle connections, and apps here sleep for hours)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            try:
                _POOL.closeall()
            except Exception:
                pass
            _POOL = None


def get_connection():
    """Borrow a connection from the pool, reconnecting if it has gone stale.

    A pool that is merely busy (every connection lent out - background
    content preparation plus two learners can do that) is waited on, never
    reset: resetting would close connections other threads are still using."""
    import time
    busy_waits, resets = 0, 0
    while True:
        try:
            p = _get_pool()
            raw = p.getconn()
            if raw.closed:
                p.putconn(raw, close=True)
                raise psycopg2.OperationalError("stale pooled connection")
            return _PooledConnection(p, raw)
        except pool.PoolError:
            busy_waits += 1
            if busy_waits > 100:                     # ~10 s of genuine exhaustion
                raise
            time.sleep(0.1)
        except Exception as e:
            resets += 1
            if resets > 1:
                raise
            logging.warning(f"[DB] pool reset after: {e}")
            reset_pool()


# Two Streamlit deployments can share this database (one per person). If
# both boot at once they would otherwise race on schema creation and the
# one-time migration, so init_db runs under a Postgres advisory lock.
_INIT_LOCK_KEY = 728451903


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pg_advisory_lock(%s)", (_INIT_LOCK_KEY,))
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            pin_hash TEXT,
            session_mode TEXT DEFAULT 'random_balanced',
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # No DEFAULT here on purpose: pre-existing rows stay NULL so _seed_users
    # can apply each person's intended mode once, without ever overwriting a
    # choice they've since made themselves.
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_mode TEXT")
    # 'vocab'     - characters drawn from words you have studied
    # 'frequency' - the 500 most common characters, in frequency order
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                   "handwriting_source TEXT DEFAULT 'vocab'")
    # Vocabulary CONTENT is shared by everyone studying on this deployment.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id SERIAL PRIMARY KEY,
            chinese TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            date_added TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_unique
        ON vocab (chinese, pinyin)
    ''')
    # Every word carries its rank in the frequency list (NULL = not in it),
    # and words from your own lesson list are marked, so the lesson-based
    # session modes keep drawing only from them. Everything already in the
    # table when this column first appears came from your lessons.
    cursor.execute("""SELECT 1 FROM information_schema.columns
                      WHERE table_name = 'vocab' AND column_name = 'from_lessons'""")
    had_lesson_flag = cursor.fetchone() is not None
    cursor.execute("ALTER TABLE vocab ADD COLUMN IF NOT EXISTS freq_rank INTEGER")
    cursor.execute("ALTER TABLE vocab ADD COLUMN IF NOT EXISTS "
                   "from_lessons BOOLEAN DEFAULT FALSE")
    if not had_lesson_flag:
        cursor.execute("UPDATE vocab SET from_lessons = TRUE")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocab_freq ON vocab (freq_rank)")
    # 'Malaysia' = the word Malaysians use; 'China' = mainland usage, with the
    # Malaysian word named in its meaning. Blank for everything shared.
    cursor.execute("ALTER TABLE vocab ADD COLUMN IF NOT EXISTS tag TEXT")
    # Grammar drills: per-learner spaced repetition for each structure, and the
    # drill sets written for them (kept so a set can be reused, then replaced
    # as the learner's vocabulary grows).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grammar_progress (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            structure_id TEXT NOT NULL,
            next_review_date TEXT,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            last_score REAL,
            first_seen TEXT,
            last_seen TEXT,
            PRIMARY KEY (user_id, structure_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grammar_drill_sets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            structure_id TEXT NOT NULL,
            known_count INTEGER DEFAULT 0,
            payload TEXT NOT NULL,
            served_count INTEGER DEFAULT 0,
            last_served TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_grammar_sets "
                   "ON grammar_drill_sets (user_id, structure_id)")
    # Vocabulary engine: separate recognition and production schedules per
    # word, and a log of every retrieval (mode, result, what went wrong) that
    # the diagnosis of repeatedly missed words reads.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_skill (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            skill TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease REAL DEFAULT 2.5,
            next_review_date TEXT,
            reps INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_mode TEXT,
            last_result TEXT,
            introduced_on TEXT,
            PRIMARY KEY (user_id, vocab_id, skill)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_skill_due "
                   "ON word_skill (user_id, skill, next_review_date)")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_attempts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            skill TEXT NOT NULL,
            mode TEXT NOT NULL,
            result TEXT NOT NULL,
            detail JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_attempts "
                   "ON word_attempts (user_id, vocab_id, created_at)")
    # What each word is learned through (chunks, sentences, confusables,
    # prompts), written per learner from the words they know.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_content (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            known_count INTEGER DEFAULT 0,
            payload TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_content "
                   "ON word_content (user_id, vocab_id)")
    # Why a word keeps being missed, the remedy built for it, and the
    # learner's own memory hook; resolved once the word holds again.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_diagnosis (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            skill TEXT NOT NULL,
            cause TEXT NOT NULL,
            evidence JSONB,
            confused_with TEXT,
            remedy JSONB,
            note TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_diagnosis "
                   "ON word_diagnosis (user_id, vocab_id) WHERE resolved_at IS NULL")
    # Sound & Pairing drills: a spaced schedule per tone group (syllable) and
    # per character family.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drill_progress (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            drill TEXT NOT NULL,
            key TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease REAL DEFAULT 2.5,
            next_review_date TEXT,
            reps INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_result TEXT,
            PRIMARY KEY (user_id, drill, key)
        )
    ''')
    # The day a group was first drilled, so new groups can be capped per day.
    cursor.execute("ALTER TABLE drill_progress ADD COLUMN IF NOT EXISTS first_seen TEXT")
    # Time ledger: one row per finished session on any page, whether it was a
    # step of the day's plan or chosen from the Library. The Today page reads
    # it to know which steps are done; Together reads it for minutes studied.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day DATE NOT NULL,
            activity TEXT NOT NULL,
            seconds INTEGER DEFAULT 0,
            items INTEGER DEFAULT 0,
            in_plan BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_sessions "
                   "ON study_sessions (user_id, day)")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_scores (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            game TEXT NOT NULL,
            best INTEGER DEFAULT 0,
            plays INTEGER DEFAULT 0,
            last_played TEXT,
            PRIMARY KEY (user_id, game)
        )
    ''')
    conn.commit()

    # Users must exist before anything references them, and the legacy
    # vocab table must be split BEFORE the new-shape vocab_progress is
    # declared — otherwise CREATE TABLE IF NOT EXISTS silently no-ops on the
    # old table and every later index fails.
    _seed_users(conn)
    # latest_mix ignored due dates while its grades still moved the review
    # schedule; it is retired, and anyone still on it moves to the balanced
    # spaced-repetition draw.
    cursor.execute("UPDATE users SET session_mode = 'random_balanced' "
                   "WHERE session_mode = 'latest_mix' OR session_mode IS NULL")
    conn.commit()
    _split_legacy_vocab(conn)
    # SRS state is PER USER. (The pre-multi-user table of the same name held
    # content and progress together; _migrate_to_multiuser splits it.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            next_review_date TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            priority_weight INTEGER DEFAULT 1,
            UNIQUE (user_id, vocab_id)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_vp_user
        ON vocab_progress (user_id, next_review_date)
    ''')
    # NEW: handwriting progress
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS handwriting_progress (
            id SERIAL PRIMARY KEY,
            character TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            next_review_date TEXT NOT NULL,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            first_seen_date TEXT NOT NULL,
            total_mistakes INTEGER DEFAULT 0,
            recent_grades TEXT DEFAULT '',
            recent_mistakes TEXT DEFAULT '',
            last_reviewed TEXT,
            clean_writes INTEGER DEFAULT 0
        )
    ''')
    # Backfill struggle-tracking columns on databases created before this
    # feature (CREATE TABLE IF NOT EXISTS never alters an existing table).
    for _coldef in ("user_id INTEGER",
                    "total_mistakes INTEGER DEFAULT 0",
                    "recent_grades TEXT DEFAULT ''",
                    "recent_mistakes TEXT DEFAULT ''",
                    "last_reviewed TEXT",
                    "clean_writes INTEGER DEFAULT 0"):
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS herbs (
            id SERIAL PRIMARY KEY,
            chinese TEXT NOT NULL UNIQUE,
            pinyin TEXT,
            english TEXT,
            category TEXT,
            tier INTEGER DEFAULT 9,
            latin TEXT,
            alt_script TEXT,
            date_added TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day DATE NOT NULL DEFAULT CURRENT_DATE,
            ts TIMESTAMP DEFAULT NOW(),
            kind TEXT NOT NULL,
            item TEXT,
            grade INTEGER,
            mistakes INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_activity_user_day
        ON activity_log (user_id, day)
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reading_bank (
            id SERIAL PRIMARY KEY,
            chinese TEXT NOT NULL UNIQUE,
            english TEXT,
            char_set TEXT NOT NULL,
            char_count INTEGER DEFAULT 0,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reading_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sentence_id INTEGER NOT NULL REFERENCES reading_bank(id) ON DELETE CASCADE,
            seen_count INTEGER DEFAULT 0,
            last_seen TEXT,
            UNIQUE (user_id, sentence_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nudges (
            id SERIAL PRIMARY KEY,
            from_user INTEGER REFERENCES users(id) ON DELETE CASCADE,
            to_user INTEGER REFERENCES users(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            seen_at TIMESTAMP
        )
    ''')
    conn.commit()

    _migrate_progress_tables(conn)

    try:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (_INIT_LOCK_KEY,))
        conn.commit()
    except Exception:
        pass
    conn.close()
    logging.info("Supabase database initialized successfully.")


# ==========================================
# SHORT-LIVED READ CACHE
# Streamlit re-runs the entire script on every interaction, so the sidebar
# metrics alone used to re-query the database on each click. These are
# read-only summaries where a few seconds of staleness is invisible, and
# any write clears them immediately, so the numbers still update the
# moment you grade a card.
# ==========================================
def _in_streamlit():
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        return False


def _cached(ttl=20):
    """Cache only when actually running inside Streamlit. The offline
    scripts (deck builders, tests) get the plain function, so they neither
    cache stale data nor emit 'no runtime found' warnings."""
    def wrap(fn):
        if not _in_streamlit():
            return fn
        try:
            return st.cache_data(ttl=ttl, show_spinner=False)(fn)
        except Exception:
            return fn
    return wrap


def clear_caches():
    """Drop cached summaries after anything that changes them."""
    if not _in_streamlit():
        return
    try:
        st.cache_data.clear()
    except Exception:
        pass


# ==========================================
# USERS
# ==========================================
# (username, display name, default session mode)
#   srs_latest      — due reviews first, then newest additions.
#   random_balanced — due reviews first, then unseen words sampled evenly
#                     across difficulty bands.
#   srs_frequency   — due reviews first, then unseen words most common first.
# (latest_mix, which ignored due dates, is retired: see init_db.)
DEFAULT_USERS = [
    ("matt", "玛德宇", "random_balanced"),
    ("selina", "姚皢慧", "random_balanced"),
]


def _seed_users(conn):
    cursor = conn.cursor()
    # One-off rename: an early build seeded this user as "jean". Rename in
    # place so her progress, PIN and session mode all carry over, rather
    # than creating a second account alongside it.
    try:
        cursor.execute("SELECT 1 FROM users WHERE username = 'jean'")
        has_old = cursor.fetchone() is not None
        cursor.execute("SELECT 1 FROM users WHERE username = 'selina'")
        has_new = cursor.fetchone() is not None
        if has_old and not has_new:
            cursor.execute("UPDATE users SET username = 'selina' "
                           "WHERE username = 'jean'")
            conn.commit()
            logging.warning("[USERS] Renamed user 'jean' -> 'selina'.")
    except Exception as e:
        conn.rollback()
        logging.warning(f"[USERS] Rename check skipped: {e}")
    for username, display, mode in DEFAULT_USERS:
        cursor.execute(
            "INSERT INTO users (username, display_name, session_mode) "
            "VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
            (username, display, mode))
        # Backfill only if never set (upgrade from before session modes).
        cursor.execute("UPDATE users SET session_mode = %s "
                       "WHERE username = %s AND session_mode IS NULL",
                       (mode, username))
    conn.commit()


def _pin_hash(pin):
    return hashlib.sha256(f"pinyin-immersion::{pin}".encode("utf-8")).hexdigest()


def list_users():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT id, username, display_name, session_mode, "
                   "(pin_hash IS NOT NULL) AS has_pin FROM users ORDER BY id")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def set_session_mode(user_id, mode):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET session_mode = %s WHERE id = %s",
                   (mode, user_id))
    conn.commit()
    conn.close()


def get_handwriting_source(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT handwriting_source FROM users WHERE id = %s",
                   (user_id,))
    row = cursor.fetchone()
    conn.close()
    return (row[0] if row and row[0] else "vocab")


def set_handwriting_source(user_id, source):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET handwriting_source = %s WHERE id = %s",
                   (source, user_id))
    conn.commit()
    conn.close()


def get_session_mode(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT session_mode FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    mode = row[0] if row and row[0] else "random_balanced"
    return "random_balanced" if mode == "latest_mix" else mode


def set_user_pin(user_id, pin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pin_hash = %s WHERE id = %s",
                   (_pin_hash(str(pin)), user_id))
    conn.commit()
    conn.close()


def verify_user_pin(user_id, pin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pin_hash FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return row[0] == _pin_hash(str(pin))


def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT id, username, display_name, session_mode "
                   "FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ==========================================
# ONE-TIME MIGRATION TO MULTI-USER
# Splits the old combined vocab_progress table into shared `vocab` content
# plus per-user progress, and attaches all existing study history to the
# first user. Idempotent, transactional, and NON-DESTRUCTIVE: the original
# table is renamed to vocab_progress_legacy rather than dropped.
# ==========================================
def _split_legacy_vocab(conn):
    """Phase 1: split the old combined vocab_progress table."""
    cursor = conn.cursor()

    cursor.execute("""SELECT column_name FROM information_schema.columns
                      WHERE table_name = 'vocab_progress'""")
    cols = {r[0] for r in cursor.fetchall()}
    legacy_shape = "chinese" in cols

    cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
    owner = cursor.fetchone()
    if not owner:
        return
    owner_id = owner[0]

    if legacy_shape:
        logging.warning("[MIGRATE] Legacy vocab_progress detected — "
                        "splitting into shared vocab + per-user progress…")
        try:
            cursor.execute("ALTER TABLE vocab_progress RENAME TO vocab_progress_legacy")
            cursor.execute("""
                CREATE TABLE vocab_progress (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
                    next_review_date TEXT NOT NULL,
                    interval INTEGER DEFAULT 0,
                    ease_factor REAL DEFAULT 2.5,
                    review_count INTEGER DEFAULT 0,
                    priority_weight INTEGER DEFAULT 1,
                    UNIQUE (user_id, vocab_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vp_user
                ON vocab_progress (user_id, next_review_date)
            """)
            # content -> vocab (deduped, keeping the earliest row per word)
            cursor.execute("""
                INSERT INTO vocab (chinese, pinyin, english, date_added)
                SELECT DISTINCT ON (chinese, pinyin)
                       chinese, pinyin, english, date_added
                FROM vocab_progress_legacy
                ORDER BY chinese, pinyin, id
                ON CONFLICT (chinese, pinyin) DO NOTHING
            """)
            # progress -> the first user
            cursor.execute("""
                INSERT INTO vocab_progress
                    (user_id, vocab_id, next_review_date, interval,
                     ease_factor, review_count, priority_weight)
                SELECT DISTINCT ON (v.id)
                       %s, v.id, l.next_review_date, l.interval,
                       l.ease_factor, l.review_count, l.priority_weight
                FROM vocab_progress_legacy l
                JOIN vocab v ON v.chinese = l.chinese AND v.pinyin = l.pinyin
                ORDER BY v.id, l.review_count DESC, l.id
                ON CONFLICT (user_id, vocab_id) DO NOTHING
            """, (owner_id,))
            conn.commit()
            cursor.execute("SELECT COUNT(*) FROM vocab")
            nv = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM vocab_progress")
            np_ = cursor.fetchone()[0]
            logging.warning(f"[MIGRATE] {nv} shared vocab words, {np_} progress "
                            f"rows kept for user {owner_id}. Original data "
                            f"preserved in vocab_progress_legacy.")
        except Exception as e:
            conn.rollback()
            logging.error(f"[MIGRATE] Vocabulary migration FAILED, rolled back: {e}")
            raise

def _migrate_progress_tables(conn):
    """Phase 2: attach existing handwriting progress to the first user,
    once all tables exist."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
    owner = cursor.fetchone()
    if not owner:
        return
    owner_id = owner[0]

    # handwriting: attach existing rows to the first user, then key on
    # (user_id, character) instead of character alone
    try:
        cursor.execute("UPDATE handwriting_progress SET user_id = %s "
                       "WHERE user_id IS NULL", (owner_id,))
        cursor.execute("""SELECT conname FROM pg_constraint
                          WHERE conrelid = 'handwriting_progress'::regclass
                            AND contype = 'u'""")
        for (name,) in cursor.fetchall():
            cursor.execute(f'ALTER TABLE handwriting_progress DROP CONSTRAINT "{name}"')
        cursor.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_hw_user_char
                          ON handwriting_progress (user_id, character)""")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"[MIGRATE] Handwriting migration issue: {e}")

# Shared projection: vocabulary content LEFT JOINed to one user's progress,
# so a word with no progress row yet simply reads as unseen (review_count 0).
# Every query returns the same dict shape the app used before multi-user.
_VOCAB_SELECT = """
    SELECT v.id AS id, v.chinese, v.pinyin, v.english, v.date_added,
           COALESCE(p.next_review_date, v.date_added) AS next_review_date,
           COALESCE(p.interval, 0)        AS interval,
           COALESCE(p.ease_factor, 2.5)   AS ease_factor,
           COALESCE(p.review_count, 0)    AS review_count,
           COALESCE(p.priority_weight, 1) AS priority_weight
    FROM vocab v
    LEFT JOIN vocab_progress p
           ON p.vocab_id = v.id AND p.user_id = %s
"""
# Pool for the lesson-based modes: your lesson words, plus anything you have
# already studied (whichever list it came from).
_LESSON_OR_STUDIED = "(v.from_lessons OR p.review_count > 0)"


def _csv_fingerprint():
    """Content hash of every vocabulary source file. (Size + mtime changed on
    every Streamlit Cloud reboot, because the repo is re-cloned, so the
    import used to rerun on each cold start.)"""
    h = hashlib.sha256()
    for path in (VOCAB_CSV_PATH, FREQUENCY_CSV_PATH, FREQUENCY_RANKS_PATH):
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:32]


def _read_frequency_files():
    """(rank for every ranked word, the study rows of the top-10,000 list)."""
    ranks, study = {}, []
    if FREQUENCY_RANKS_PATH.exists():
        rdf = pd.read_csv(FREQUENCY_RANKS_PATH, dtype=str, keep_default_na=False)
        for zh, rk in zip(rdf["Chinese"], rdf["Rank"]):
            if zh.strip() and rk.strip():
                ranks.setdefault(zh.strip(), int(rk))
    if FREQUENCY_CSV_PATH.exists():
        # Same three columns as vocab_export.csv; the row order IS the rank.
        fdf = pd.read_csv(FREQUENCY_CSV_PATH, dtype=str, keep_default_na=False)
        tags = fdf["Tag"] if "Tag" in fdf.columns else [""] * len(fdf)
        for rk, (zh, py, en, tag) in enumerate(zip(fdf["Chinese"], fdf["Pinyin"],
                                                   fdf["English"], tags), 1):
            zh, py = zh.strip(), py.strip()
            if zh and py:
                study.append((rk, zh, py, en.strip(), _clean_tag(tag)))
                ranks.setdefault(zh, rk)
    return ranks, study


def _clean_tag(tag):
    tag = str(tag).strip() if tag == tag and tag is not None else ""
    return tag if tag in ("China", "Malaysia") else ""


def _read_lesson_file():
    """Your lesson list. The Tag column is optional, so rows pasted in with
    just Chinese, Pinyin and English still import."""
    rows = []
    if VOCAB_CSV_PATH.exists():
        df = pd.read_csv(VOCAB_CSV_PATH, dtype=str, keep_default_na=False)
        tags = df['Tag'] if 'Tag' in df.columns else [""] * len(df)
        for zh, py, en, tag in zip(df['Chinese'], df['Pinyin'], df['English'], tags):
            zh, py = str(zh).strip(), str(py).strip()
            en = str(en).strip() if en == en else ""
            if zh and py and zh != 'nan' and py != 'nan':
                zh, py = strip_erhua(zh, py)     # no Beijing 儿 (一点儿 -> 一点)
                rows.append((zh, py, en, _clean_tag(tag)))
    return rows


def _progress_strength(p):
    return (p["review_count"] or 0, p["interval"] or 0)


def _merge_card(cursor, progress, src, dst):
    """Move every learner's progress from card `src` onto card `dst`, keeping
    the stronger record where both exist, then delete `src`."""
    dst_rows = {p["user_id"]: p for p in progress.get(dst, [])}
    for p in progress.get(src, []):
        d = dst_rows.get(p["user_id"])
        if d is None:
            cursor.execute("UPDATE vocab_progress SET vocab_id = %s WHERE id = %s",
                           (dst, p["id"]))
            p["vocab_id"] = dst
            dst_rows[p["user_id"]] = p
            progress.setdefault(dst, []).append(p)
            continue
        if _progress_strength(p) > _progress_strength(d):
            for k in ("next_review_date", "interval", "ease_factor", "review_count"):
                d[k] = p[k]
        d["priority_weight"] = max(d["priority_weight"] or 1, p["priority_weight"] or 1)
        cursor.execute("""UPDATE vocab_progress SET next_review_date = %s,
                              interval = %s, ease_factor = %s, review_count = %s,
                              priority_weight = %s WHERE id = %s""",
                       (d["next_review_date"], d["interval"], d["ease_factor"],
                        d["review_count"], d["priority_weight"], d["id"]))
        cursor.execute("DELETE FROM vocab_progress WHERE id = %s", (p["id"],))
    progress.pop(src, None)
    cursor.execute("DELETE FROM vocab WHERE id = %s", (src,))


def run_erhua_cleanup(conn=None):
    """One-off: remove the Beijing 儿 from every stored card. A card whose
    plain form already exists (一点儿 -> 一点) is merged into it, carrying
    progress across; any other card is simply respelled."""
    own_conn = conn is None
    conn = conn or get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, chinese, pinyin FROM vocab ORDER BY id")
    cards = [{"id": v, "chinese": c, "pinyin": p} for v, c, p in cursor.fetchall()]
    cursor.execute("""SELECT id, user_id, vocab_id, next_review_date, interval,
                             ease_factor, review_count, priority_weight
                      FROM vocab_progress""")
    progress = {}
    for r in cursor.fetchall():
        p = dict(zip(("id", "user_id", "vocab_id", "next_review_date", "interval",
                      "ease_factor", "review_count", "priority_weight"), r))
        progress.setdefault(p["vocab_id"], []).append(p)
    by_chinese = {}
    for c in cards:
        by_chinese.setdefault(c["chinese"], []).append(c)
    merged = respelled = 0
    for card in cards:
        if not has_erhua(card["chinese"], card["pinyin"]):
            continue
        zh, py = strip_erhua(card["chinese"], card["pinyin"])
        others = [c for c in by_chinese.get(zh, []) if c["id"] != card["id"]]
        if others:
            target = next((c for c in others
                           if _pinyin_key(c["pinyin"]) == _pinyin_key(py)), others[0])
            _merge_card(cursor, progress, card["id"], target["id"])
            merged += 1
        else:
            cursor.execute("UPDATE vocab SET chinese = %s, pinyin = %s WHERE id = %s",
                           (zh, py, card["id"]))
            card["chinese"], card["pinyin"] = zh, py
            by_chinese.setdefault(zh, []).append(card)
            respelled += 1
    cursor.execute("""INSERT INTO app_meta (key, value) VALUES ('vocab_erhua_v1', 'done')
                      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""")
    conn.commit()
    if own_conn:
        conn.close()
    clear_caches()
    logging.info(f"Erhua cleanup: {merged} cards merged into their plain form, "
                 f"{respelled} respelled.")
    return {"merged": merged, "respelled": respelled}


def run_vocab_cleanup(conn=None):
    """One-off tidy so the shared vocabulary matches the two word lists.

    - A word stored more than once (e.g. 背包 as both 'bèi bāo' and 'bēi bāo')
      becomes one card in the list's spelling. Every learner's progress is
      carried over; where both copies had progress, the stronger one wins.
    - Old cards in neither list (the pre-2026-09 sentence cards) are deleted
      unless someone has made progress with them. Those kept get the lists'
      pinyin style (one syllable per space, lower case).
    Returns counts, or None if the list files are missing.
    """
    from dictionary_engine import format_pinyin
    lesson_rows = _read_lesson_file()
    _ranks, study = _read_frequency_files()
    if len(lesson_rows) < 50 or len(study) < 1000:
        logging.warning("Vocabulary cleanup skipped: list files incomplete.")
        return None

    # Canonical readings: your lesson spelling wins; the frequency list
    # only speaks for words that aren't in your lessons.
    listed = {}
    for zh, py, _en, _tag in lesson_rows:
        listed.setdefault(zh, {}).setdefault(_pinyin_key(py), py)
    for _rk, zh, py, _en, _tag in study:
        if zh not in listed:
            listed[zh] = {_pinyin_key(py): py}

    own_conn = conn is None
    conn = conn or get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, chinese, pinyin FROM vocab ORDER BY id")
    groups = {}
    for vid, zh, py in cursor.fetchall():
        groups.setdefault(zh, []).append({"id": vid, "pinyin": py})
    cursor.execute("""SELECT id, user_id, vocab_id, next_review_date, interval,
                             ease_factor, review_count, priority_weight
                      FROM vocab_progress""")
    progress = {}
    for r in cursor.fetchall():
        p = dict(zip(("id", "user_id", "vocab_id", "next_review_date", "interval",
                      "ease_factor", "review_count", "priority_weight"), r))
        progress.setdefault(p["vocab_id"], []).append(p)

    def studied(vid):
        return any((p["review_count"] or 0) > 0 or (p["priority_weight"] or 1) > 1
                   for p in progress.get(vid, []))

    def weight(vid):
        return max([_progress_strength(p) for p in progress.get(vid, [])] or [(0, 0)])

    def bases(py):
        return re.sub(r"[^a-zü]", "", unicodedata.normalize("NFD", py.lower()))

    merged = deleted = restyled = 0
    to_delete, respell = [], []
    for zh, cards in groups.items():
        readings = listed.get(zh)
        if readings:
            owner = {}
            strays = []
            for key, py in readings.items():
                same = [c for c in cards if _pinyin_key(c["pinyin"]) == key]
                if not same:
                    continue
                keep = next((c for c in same if c["pinyin"] == py), None) or \
                    max(same, key=lambda c: (weight(c["id"]), -c["id"]))
                owner[key] = keep
                strays += [c for c in same if c is not keep]
            strays += [c for c in cards
                       if _pinyin_key(c["pinyin"]) not in readings]
            strays.sort(key=lambda c: weight(c["id"]), reverse=True)
            for c in strays:
                unowned = [k for k in readings if k not in owner]
                if unowned and _pinyin_key(c["pinyin"]) not in readings:
                    # the only copy of this reading: respell it, keep the card
                    key = next((k for k in unowned
                                if bases(readings[k]) == bases(c["pinyin"])), unowned[0])
                    owner[key] = c
                    continue
                target = next((o for k, o in owner.items()
                               if bases(readings[k]) == bases(c["pinyin"])),
                              next(iter(owner.values())))
                _merge_card(cursor, progress, c["id"], target["id"])
                merged += 1
            for key, c in owner.items():
                if c["pinyin"] != readings[key]:
                    respell.append((readings[key], c["id"]))
            continue
        # in neither list: keep only cards someone has made progress with
        keepers = [c for c in cards if studied(c["id"])]
        to_delete += [c["id"] for c in cards if not studied(c["id"])]
        if keepers:
            keepers.sort(key=lambda c: weight(c["id"]), reverse=True)
            for c in keepers[1:]:
                _merge_card(cursor, progress, c["id"], keepers[0]["id"])
                merged += 1
            styled = format_pinyin(keepers[0]["pinyin"])
            if styled != keepers[0]["pinyin"]:
                respell.append((styled, keepers[0]["id"]))

    if to_delete:
        cursor.execute("DELETE FROM vocab WHERE id = ANY(%s)", (to_delete,))
        deleted = len(to_delete)
    for py, vid in respell:
        cursor.execute("UPDATE vocab SET pinyin = %s WHERE id = %s", (py, vid))
    restyled = len(respell)
    cursor.execute("""INSERT INTO app_meta (key, value) VALUES ('vocab_cleanup_v1', 'done')
                      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""")
    conn.commit()
    if own_conn:
        conn.close()
    clear_caches()
    logging.info(f"Vocabulary cleanup: {merged} duplicates merged, {deleted} "
                 f"unstudied old cards removed, {restyled} cards respelled.")
    return {"merged": merged, "deleted": deleted, "respelled": restyled}


_IMPORT_LOCK_KEY = 7_730_517


def import_vocab_from_csv(force=False):
    """Serialised wrapper: if two copies of the app boot together (the cloud
    app and a local run, say) the second waits, then finds the work done."""
    lock_conn = get_connection()
    lock_cur = lock_conn.cursor()
    lock_cur.execute("SELECT pg_advisory_lock(%s)", (_IMPORT_LOCK_KEY,))
    try:
        _import_vocab(force)
    finally:
        lock_cur.execute("SELECT pg_advisory_unlock(%s)", (_IMPORT_LOCK_KEY,))
        lock_conn.close()


def _import_vocab(force=False):
    """Merge your lesson list and the 10,000-word frequency list into the
    SHARED vocabulary table.

    - Your lesson words (vocab_export.csv) always win: their pinyin and
      meaning are used, and they are marked from_lessons.
    - A frequency word is only added if no row with the same characters
      exists, so no word appears twice (a genuine second reading you add
      yourself, like 只 zhǐ / zhī, is still allowed).
    - Every row gets its frequency rank; glosses refresh from the files.
    Runs only when a source file's content changes, in a handful of bulk
    queries.
    """
    if not VOCAB_CSV_PATH.exists() and not FREQUENCY_CSV_PATH.exists():
        logging.warning("No vocabulary files found. Skipping import.")
        return

    fingerprint = _csv_fingerprint()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS app_meta (
                        key TEXT PRIMARY KEY, value TEXT)""")
    conn.commit()
    cursor.execute("SELECT key FROM app_meta WHERE key IN "
                   "('vocab_cleanup_v1', 'vocab_erhua_v1')")
    done = {r[0] for r in cursor.fetchall()}
    cleaned = "vocab_cleanup_v1" in done
    if not force and len(done) == 2:
        cursor.execute("SELECT value FROM app_meta WHERE key = 'vocab_csv'")
        row = cursor.fetchone()
        if row and row[0] == fingerprint:
            conn.close()
            logging.info("Vocabulary files unchanged - import skipped.")
            return
    if not cleaned:
        run_vocab_cleanup(conn)
    if "vocab_erhua_v1" not in done:
        run_erhua_cleanup(conn)

    lesson_rows = _read_lesson_file()
    ranks, study = _read_frequency_files()

    # 1 query: everything already stored. Keyed on a normalised pinyin so a
    # formatting-only difference ('qǐlái' vs 'qǐ lái') is the same word.
    cursor.execute("SELECT id, chinese, pinyin, english, freq_rank, from_lessons, tag "
                   "FROM vocab")
    by_key, by_chinese = {}, {}
    for vid, c, p, e, fr, fl, tg in cursor.fetchall():
        rec = {"id": vid, "chinese": c, "pinyin": p, "english": e,
               "freq_rank": fr, "from_lessons": bool(fl), "tag": tg}
        by_key.setdefault((c, _pinyin_key(p)), []).append(rec)
        by_chinese.setdefault(c, []).append(rec)

    today_str = date.today().isoformat()
    inserts, changed = [], {}

    def change(rec, **fields):
        diff = {k: v for k, v in fields.items() if rec.get(k) != v}
        if diff and rec["id"] is not None:
            rec.update(diff)
            changed[rec["id"]] = rec

    def add(zh, py, en, rank, lesson, tag):
        rec = {"id": None, "chinese": zh, "pinyin": py, "english": en,
               "freq_rank": rank, "from_lessons": lesson, "tag": tag}
        by_key.setdefault((zh, _pinyin_key(py)), []).append(rec)
        by_chinese.setdefault(zh, []).append(rec)
        inserts.append((zh, py, en, today_str, rank, lesson, tag))

    study_tag = {zh: tag for _r, zh, _p, _e, tag in study}

    # 1. your lesson words
    seen = set()
    for zh, py, en, tag in lesson_rows:
        key = (zh, _pinyin_key(py))
        if key in seen:
            continue
        seen.add(key)
        rank = ranks.get(zh)
        tag = tag or study_tag.get(zh) or None
        if key in by_key:
            recs = by_key[key]
            for rec in recs:
                change(rec, english=en or rec["english"], freq_rank=rank,
                       from_lessons=True, tag=tag)
            if len(recs) == 1:
                change(recs[0], pinyin=py)      # the list's exact spelling
            continue
        # Already there from the frequency list under another pinyin
        # spelling: adopt that row (keeping any progress) instead of
        # adding a second copy of the word.
        spare = [r for r in by_chinese.get(zh, [])
                 if not r["from_lessons"] and r["id"] is not None]
        if spare:
            rec = spare[0]
            change(rec, pinyin=py, english=en or rec["english"],
                   freq_rank=rank, from_lessons=True, tag=tag)
            by_key.setdefault(key, []).append(rec)
            continue
        add(zh, py, en, rank, True, tag)

    # 2. the frequency list: a word you already have is never added again
    for rank, zh, py, en, tag in study:
        if zh in by_chinese:
            continue
        add(zh, py, en, rank, False, tag or None)

    # 3. every stored row gets its current rank (older cards included)
    for zh, recs in by_chinese.items():
        rank = ranks.get(zh)
        for rec in recs:
            if rank is not None:
                change(rec, freq_rank=rank)
            elif not rec["from_lessons"] and rec["freq_rank"] is not None:
                change(rec, freq_rank=None)
    # frequency words refresh too (never over one of your lesson words)
    study_by_word = {zh: (py, en, tag) for _r, zh, py, en, tag in study}
    for zh, recs in by_chinese.items():
        if zh not in study_by_word:
            continue
        py, en, tag = study_by_word[zh]
        for rec in recs:
            if rec["from_lessons"]:
                continue
            change(rec, tag=tag or None)
            if en:
                change(rec, english=en)
            if len(recs) == 1 and _pinyin_key(rec["pinyin"]) == _pinyin_key(py):
                change(rec, pinyin=py)

    if changed:
        psycopg2.extras.execute_values(
            cursor,
            "UPDATE vocab SET pinyin = u.pinyin, english = u.english, "
            "freq_rank = u.freq_rank, from_lessons = u.from_lessons, tag = u.tag "
            "FROM (VALUES %s) AS u(id, pinyin, english, freq_rank, from_lessons, tag) "
            "WHERE vocab.id = u.id",
            [(r["id"], r["pinyin"], r["english"], r["freq_rank"], r["from_lessons"],
              r.get("tag")) for r in changed.values()],
            template="(%s, %s, %s, %s::integer, %s::boolean, %s::text)", page_size=1000)
    if inserts:
        psycopg2.extras.execute_values(
            cursor,
            "INSERT INTO vocab (chinese, pinyin, english, date_added, freq_rank, "
            "from_lessons, tag) VALUES %s ON CONFLICT (chinese, pinyin) DO NOTHING",
            inserts, template="(%s, %s, %s, %s, %s::integer, %s::boolean, %s::text)",
            page_size=1000)

    cursor.execute("""INSERT INTO app_meta (key, value) VALUES ('vocab_csv', %s)
                      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                   (fingerprint,))
    conn.commit()
    conn.close()
    clear_caches()
    logging.info(f"Vocabulary import: {len(inserts)} new, {len(changed)} updated.")


def _pinyin_key(pinyin):
    """Pinyin with case, spacing, apostrophes and hyphens ignored."""
    p = unicodedata.normalize("NFC", str(pinyin)).lower()
    return re.sub(r"[\s'’\-]", "", p)


def _ensure_progress(cursor, user_id, vocab_id):
    """Create this user's progress row for a word if they've not met it yet."""
    cursor.execute("""
        INSERT INTO vocab_progress (user_id, vocab_id, next_review_date)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, vocab_id) DO NOTHING
    """, (user_id, vocab_id, date.today().isoformat()))


# ======================================================================
# DIFFICULTY BANDS
# A brand-new learner has no performance history, so difficulty is
# estimated from the shape of the entry. In this deck the honest signal is
# length: single words are approachable, whole sentences are not. Where
# ANYONE has already studied a word, their ease factor refines the guess —
# a word that proved hard for one learner probably is hard.
# ======================================================================
EASY, MEDIUM, HARD = 0, 1, 2
_SENT_PUNCT = "。，？！；：、,?!"


def _difficulty_band(chinese, ease=None):
    han = sum(1 for c in chinese if "\u4e00" <= c <= "\u9fff")
    if any(p in chinese for p in _SENT_PUNCT) or han >= 8:
        band = HARD
    elif han >= 4:
        band = MEDIUM
    else:
        band = EASY
    # A low ease factor means someone kept forgetting it — nudge it harder.
    if ease is not None and ease < 2.2 and band < HARD:
        band += 1
    return band


# Share of a beginner's NEW cards drawn from each band. Weighted toward the
# approachable end, but deliberately never zero on hard: seeing real
# sentences from day one is how the ear gets built.
BAND_MIX = {EASY: 0.45, MEDIUM: 0.35, HARD: 0.20}


def _fetch_all_candidates(cursor, user_id, exclude_ids=()):
    """Every lesson word this user has not yet seen, with any pooled ease
    data from other learners. (Frequency-list words have their own mode.)"""
    sql = _VOCAB_SELECT + """
        LEFT JOIN (SELECT vocab_id, MIN(ease_factor) AS pooled_ease
                   FROM vocab_progress GROUP BY vocab_id) agg
               ON agg.vocab_id = v.id
        WHERE (p.review_count IS NULL OR p.review_count = 0)
          AND v.from_lessons
    """
    params = [user_id]
    if exclude_ids:
        ph = ",".join(["%s"] * len(exclude_ids))
        sql += f" AND v.id NOT IN ({ph})"
        params += list(exclude_ids)
    # pooled_ease has to ride along in the projection
    sql = sql.replace("COALESCE(p.priority_weight, 1) AS priority_weight",
                      "COALESCE(p.priority_weight, 1) AS priority_weight,\n"
                      "           agg.pooled_ease AS pooled_ease")
    cursor.execute(sql, params)
    return [dict(r) for r in cursor.fetchall()]


def _balanced_new_cards(candidates, needed, rng):
    """Sample `needed` unseen cards spread across difficulty bands, fully
    random within each band."""
    buckets = {EASY: [], MEDIUM: [], HARD: []}
    for row in candidates:
        buckets[_difficulty_band(row["chinese"], row.get("pooled_ease"))].append(row)
    for b in buckets.values():
        rng.shuffle(b)

    picked = []
    for band, share in BAND_MIX.items():
        want = int(round(needed * share))
        picked += buckets[band][:want]
        buckets[band] = buckets[band][want:]
    # top up from whatever is left if a band ran dry
    leftovers = buckets[EASY] + buckets[MEDIUM] + buckets[HARD]
    rng.shuffle(leftovers)
    picked += leftovers[:max(0, needed - len(picked))]
    return picked[:needed]


def get_session_words(user_id, total=MAX_REVIEWS_PER_DAY,
                      random_pct=RANDOM_BREADTH_PCT, mode=None):
    """Build a batch according to this user's session mode.

    random_balanced — anything genuinely due comes first (real spaced
                      repetition), then unseen words drawn at random but
                      spread evenly across difficulty bands.
    srs_latest      — anything due first, then your newest lesson words.
    srs_frequency   — anything due first, then unseen words in frequency
                      order: the most common words in spoken Mandarin first.
    latest_mix is retired (it ignored due dates) and now means
    random_balanced.
    """
    import random as _random
    rng = _random.Random()
    mode = mode or get_session_mode(user_id)
    if mode not in ("random_balanced", "srs_latest", "srs_frequency"):
        mode = "random_balanced"

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    today = date.today().isoformat()
    # 1. everything actually due, oldest/most-urgent first
    cursor.execute(_VOCAB_SELECT + """
        WHERE p.review_count > 0 AND p.next_review_date <= %s
        ORDER BY p.priority_weight DESC, p.next_review_date ASC
        LIMIT %s
    """, (user_id, today, total))
    due = [dict(r) for r in cursor.fetchall()]

    # 2. fill the rest with new cards, chosen this user's way
    needed = max(0, total - len(due))
    session = due
    if needed:
        exclude = [r["id"] for r in due]
        if mode in ("srs_latest", "srs_frequency"):
            sql = _VOCAB_SELECT + \
                " WHERE (p.review_count IS NULL OR p.review_count = 0)"
            if mode == "srs_latest":
                sql += " AND v.from_lessons"
            params = [user_id]
            if exclude:
                ph = ",".join(["%s"] * len(exclude))
                sql += f" AND v.id NOT IN ({ph})"
                params += exclude
            if mode == "srs_latest":
                # newest additions first — what you just put in the CSV
                sql += " ORDER BY v.id DESC LIMIT %s"
            else:
                # most common first; words outside the list come last
                sql += " ORDER BY v.freq_rank ASC NULLS LAST, v.id ASC LIMIT %s"
            params.append(needed)
            cursor.execute(sql, params)
            session = due + [dict(r) for r in cursor.fetchall()]
        else:
            candidates = _fetch_all_candidates(
                cursor, user_id, exclude_ids=exclude)
            session = due + _balanced_new_cards(candidates, needed, rng)
    conn.close()
    rng.shuffle(session)
    return session


@_cached(ttl=20)
def get_progress_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vocab")
    total = cursor.fetchone()[0]
    cursor.execute("""SELECT COUNT(*) FROM vocab v
                      LEFT JOIN vocab_progress p
                             ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count IS NULL OR p.review_count = 0""",
                   (user_id,))
    unseen = cursor.fetchone()[0]
    cursor.execute("""SELECT COUNT(*) FROM vocab_progress
                      WHERE user_id = %s AND interval >= 21""", (user_id,))
    mastered = cursor.fetchone()[0]
    conn.close()
    learning = max(0, total - unseen - mastered)
    return {"total": total, "unseen": unseen,
            "learning": learning, "mastered": mastered}


def delete_word_from_db(word_id):
    """Deletes SHARED vocabulary — affects everyone studying this deck."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vocab WHERE id = %s", (word_id,))
    conn.commit()
    conn.close()


def update_word_in_db(word_id, new_chinese, new_pinyin, new_english):
    """Edits SHARED vocabulary content."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE vocab SET chinese = %s, pinyin = %s, english = %s '
                   'WHERE id = %s',
                   (new_chinese, new_pinyin, new_english, word_id))
    conn.commit()
    conn.close()


def _is_cjk(ch):
    return '\u4e00' <= ch <= '\u9fff'


_HERB_CONTEXT_CACHE = {"map": None}


def _herb_context_map():
    """character -> the most important herb containing it.

    Cached per process: the drill asks for this once per card, and the herb
    list only changes on import (which clears it).
    """
    if _HERB_CONTEXT_CACHE["map"] is None:
        out = {}
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("""SELECT chinese, pinyin, english, tier
                           FROM herbs ORDER BY COALESCE(tier, 9), id""")
            for row in cur.fetchall():
                for ch in row["chinese"]:
                    if _is_cjk(ch) and ch not in out:
                        out[ch] = dict(row)
            conn.close()
        except Exception as e:
            logging.warning(f"[HERB] context map unavailable: {e}")
        _HERB_CONTEXT_CACHE["map"] = out
    return _HERB_CONTEXT_CACHE["map"]


def _hw_entry(ch, is_new, personal_freq, progress, vocab_rows):
    """Build one drill-queue entry, including the semantic recall cue: the
    best-known vocab word containing this character, its pinyin and meaning,
    and the character's own pinyin. The character itself is the ANSWER and
    is only ever rendered by HanziWriter inside the drill component."""
    ctx = choose_context_word(ch, vocab_rows) or {}
    # Fall back to a herb. Without this, a herb character reached through
    # the character browser, a weak-character drill or a focus session
    # arrived with no cue at all - just "20 strokes, rare" - because no
    # word in the user's vocabulary contains it.
    if not ctx:
        herb = _herb_context_map().get(ch)
        if herb:
            ctx = {"chinese": herb["chinese"],
                   "pinyin": herb.get("pinyin") or "",
                   "english": herb.get("english") or ""}
    entry = {
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
    # The character's OWN dictionary entry and how common it is. The word
    # gives context; this gives the character's actual meaning, which a
    # single word often doesn't reveal (e.g. 巴 in 巴刹 is a loanword
    # transliteration and tells you nothing about the character).
    info = character_info(ch)
    entry["char_gloss"] = info["gloss"]
    entry["freq_rank"] = info["rank"]
    entry["freq_label"] = frequency_label(info["rank"])
    clean = (progress or {}).get("clean_writes", 0)
    entry["clean_writes"] = clean or 0
    entry["leniency"] = precision_for(clean)
    entry["precision_level"] = precision_level(clean)
    return entry


def get_focus_session(user_id, text):
    """Drill exactly the CJK characters of `text`, regardless of due dates."""
    chars = []
    for ch in text:
        if _is_cjk(ch) and ch not in chars:
            chars.append(ch)
    if not chars:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT v.chinese, v.pinyin, v.english,
                             COALESCE(p.review_count, 0) AS review_count
                      FROM vocab v LEFT JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE v.chinese ~ %s""",
                   (user_id, "[" + "".join(chars) + "]"))
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    placeholders = ','.join(['%s'] * len(chars))
    cursor.execute(f"SELECT * FROM handwriting_progress "
                   f"WHERE user_id = %s AND character IN ({placeholders})",
                   [user_id] + chars)
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


def list_studied_characters(user_id, scope="all"):
    """Every character this user has drilled, with enough detail to pick
    from: how it's going, how common it is, and what it means.

    scope: 'all' | 'mastered' | 'learning' | 'due' | 'weak'
    Definitions match the sidebar counters exactly - 'practiced' is any
    character with a progress row, 'mastered' is one pushed 21+ days out.
    """
    today_str = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT character, interval, ease_factor, review_count,
                             total_mistakes, recent_mistakes, next_review_date,
                             clean_writes
                      FROM handwriting_progress WHERE user_id = %s""",
                   (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""SELECT v.chinese, v.pinyin, v.english, p.review_count
                      FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    out = []
    for r in rows:
        ch = r["character"]
        interval = r.get("interval") or 0
        mastered = interval >= 21
        due = (r.get("next_review_date") or "9999") <= today_str
        rate = _recent_mistake_rate(r.get("recent_mistakes"))
        if scope == "mastered" and not mastered:
            continue
        if scope == "learning" and mastered:
            continue
        if scope == "due" and not due:
            continue
        if scope == "weak" and rate <= 0:
            continue
        info = character_info(ch)
        ctx = choose_context_word(ch, vocab_rows) or {}
        out.append({
            "character": ch,
            "pinyin": info["pinyin"],
            "gloss": info["gloss"],
            "rank": info["rank"],
            "freq_label": frequency_label(info["rank"]),
            "interval": interval,
            "review_count": r.get("review_count") or 0,
            "total_mistakes": r.get("total_mistakes") or 0,
            "recent_mistake_rate": round(rate, 2),
            "clean_writes": r.get("clean_writes") or 0,
            "precision_level": precision_level(r.get("clean_writes") or 0),
            "next_review_date": r.get("next_review_date"),
            "mastered": mastered,
            "due": due,
            "word": ctx.get("chinese", ""),
            "word_english": ctx.get("english", ""),
        })
    out.sort(key=lambda e: (e["rank"] or 10**6))
    return out


def get_curriculum_session(user_id, new_count=5, limit_rank=500):
    """Handwriting queue driven by character frequency rather than by which
    words you happen to have studied.

    Due reviews come first, then the next unseen characters in frequency
    order. The recall cue still prefers a real vocabulary word containing
    the character; where you have no such word, the character's own pinyin
    and gloss are used instead, so nothing in the curriculum is unreachable.
    """
    from character_curriculum import CHARACTERS, INFO
    today_str = date.today().isoformat()
    wanted = CHARACTERS[:limit_rank]

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT chinese, pinyin, english, review_count
                      FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
    vocab_rows = [dict(r) for r in cursor.fetchall()]

    ph = ",".join(["%s"] * len(wanted))
    cursor.execute(f"""SELECT * FROM handwriting_progress
                       WHERE user_id = %s AND character IN ({ph})""",
                   [user_id] + wanted)
    progress = {r["character"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    def build(ch, is_new):
        entry = _hw_entry(ch, is_new, 1, progress.get(ch), vocab_rows)
        # No studied word contains this character yet - fall back to the
        # curriculum's own pinyin and meaning as the cue.
        if entry["word"] == ch and not entry["word_english"]:
            info = INFO.get(ch, {})
            entry["word"] = ch
            entry["word_pinyin"] = info.get("pinyin", entry["char_pinyin"])
            entry["word_english"] = info.get("gloss", "")
        entry["curriculum_rank"] = INFO.get(ch, {}).get("rank")
        return entry

    due = [build(ch, False) for ch in wanted
           if ch in progress and progress[ch]["next_review_date"] <= today_str]
    due.sort(key=lambda e: (e["next_review_date"], e["curriculum_rank"] or 0))

    new = [build(ch, True) for ch in wanted if ch not in progress][:new_count]
    return due + new


@_cached(ttl=20)
def get_curriculum_progress(user_id, limit_rank=500):
    """How far through the frequency curriculum this user has got.

    The headline number is how many of the 500 characters have actually
    been studied, and coverage is the SUM of those characters' individual
    frequencies. An earlier version reported the furthest CONSECUTIVE
    position reached instead, which stuck at 2/500 for anyone who had
    drilled characters from their vocabulary before switching modes: one
    missing character near the top of the list hid all later progress.
    """
    from character_curriculum import CHARACTERS, coverage_for
    wanted = CHARACTERS[:limit_rank]
    conn = get_connection()
    cursor = conn.cursor()
    ph = ",".join(["%s"] * len(wanted))
    cursor.execute(f"""SELECT character, interval FROM handwriting_progress
                       WHERE user_id = %s AND character IN ({ph})""",
                   [user_id] + wanted)
    rows = cursor.fetchall()
    conn.close()
    started = {r[0] for r in rows}
    mastered = {r[0] for r in rows if (r[1] or 0) >= 21}

    # Secondary, kept for the "working through them in order" view.
    in_order = 0
    for ch in wanted:
        if ch in started:
            in_order += 1
        else:
            break

    return {"total": len(wanted),
            "started": len(started),
            "mastered": len(mastered),
            "in_order": in_order,
            "furthest_rank": len(started),      # headline = real progress
            "text_coverage": round(coverage_for(started), 1),
            "mastered_coverage": round(coverage_for(mastered), 1)}


@_cached(ttl=20)
def get_handwriting_counts(user_id):
    """(due_reviews, new_available) for the session setup screen.

    PERFORMANCE: this used to build an ENTIRE drill session with
    new_count=1,000,000 just to count two numbers - deriving pinyin,
    stroke counts and a context word for every character in the user's
    vocabulary, on every page load. It now counts in SQL.
    """
    today_str = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT v.chinese FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
    chars = {c for (text,) in cursor.fetchall() for c in text if _is_cjk(c)}
    if not chars:
        conn.close()
        return 0, 0
    ph = ",".join(["%s"] * len(chars))
    chars = list(chars)
    cursor.execute(f"""SELECT character, next_review_date
                       FROM handwriting_progress
                       WHERE user_id = %s AND character IN ({ph})""",
                   [user_id] + chars)
    seen = dict(cursor.fetchall())
    conn.close()
    due = sum(1 for c in chars if c in seen and seen[c] <= today_str)
    new = sum(1 for c in chars if c not in seen)
    return due, new


def handwriting_new_today(user_id):
    """Characters written for the first time today, across every source."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM handwriting_progress
                      WHERE user_id = %s AND first_seen_date = %s""",
                   (user_id, date.today().isoformat()))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def handwriting_new_allowance(user_id, due):
    """New characters still allowed today: a daily cap shared by every
    source, and none while reviews have piled up."""
    from config import HANDWRITING_NEW_PER_DAY, HANDWRITING_BACKLOG
    if due > HANDWRITING_BACKLOG:
        return 0
    return max(0, HANDWRITING_NEW_PER_DAY - handwriting_new_today(user_id))


def handwriting_started(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM handwriting_progress WHERE user_id = %s LIMIT 1",
                   (user_id,))
    ok = cursor.fetchone() is not None
    conn.close()
    return ok


def handwriting_due_and_new(user_id, source=None):
    """(due, new_available) for the learner's chosen character source."""
    source = source or get_handwriting_source(user_id)
    if source == "herbs":
        hc = herb_character_counts(user_id)
        return hc["due"], hc["new"]
    if source == "frequency":
        from character_curriculum import CHARACTERS
        cp = get_curriculum_progress(user_id)
        return len(get_curriculum_session(user_id, new_count=0)), \
            max(0, min(len(CHARACTERS), 500) - (cp.get("started", 0) or 0))
    return get_handwriting_counts(user_id)


def handwriting_session_for(user_id, new_chars, max_reviews=None, source=None):
    """A standard review session from the chosen source. `new_chars` is in
    characters; herb names are introduced whole, about two characters each."""
    source = source or get_handwriting_source(user_id)
    if source == "herbs":
        chars = get_herb_session(user_id, new_count=(new_chars + 1) // 2)
    elif source == "frequency":
        chars = get_curriculum_session(user_id, new_count=new_chars)
    else:
        chars = get_handwriting_session(user_id, new_count=new_chars)
    if max_reviews is not None and source != "herbs":     # herb names stay whole
        due = [c for c in chars if not c.get("is_new")]
        if len(due) > max_reviews:
            keep = set(id(c) for c in due[:max_reviews])
            chars = [c for c in chars if c.get("is_new") or id(c) in keep]
    return chars


def get_handwriting_session(user_id, new_count=5):
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
    cursor.execute("""SELECT v.chinese, v.pinyin, v.english, p.review_count
                      FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
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
        SELECT * FROM handwriting_progress
        WHERE user_id = %s AND character IN ({placeholders})
    ''', [user_id] + unique_chars)
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

    # 5. Introduce new characters in order of how common they are in
    #    written Chinese, so the most useful ones are learned first.
    #    Characters outside the frequency list sort last.
    new_candidates.sort(
        key=lambda ch: (character_info(ch)["rank"] or 10**6,
                        score_character(ch, char_freq[ch])))
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


def update_handwriting_progress(user_id, character, grade, current_state, mistakes=0):
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

    # A clean write - no mistakes, no reveal - earns one step of extra
    # precision on this character. A failure gives some back, so a bad
    # session can't leave a character permanently at maximum strictness.
    prev_clean = int(current_state.get('clean_writes', 0) or 0)
    if mistakes == 0 and grade >= 2:
        new_clean = prev_clean + 1
    elif grade == 0:
        new_clean = max(0, prev_clean - PRECISION_RELAPSE)
    else:
        new_clean = prev_clean

    prev_grades = current_state.get('recent_grades', '') or ''
    prev_mist = current_state.get('recent_mistakes', '') or ''
    new_grades = _push_recent(prev_grades, grade)
    new_mist = _push_recent(prev_mist, mistakes)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO handwriting_progress
            (character, user_id, next_review_date, interval, ease_factor,
             review_count, first_seen_date, total_mistakes, recent_grades,
             recent_mistakes, last_reviewed, clean_writes)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, character) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = handwriting_progress.review_count + 1,
            total_mistakes = handwriting_progress.total_mistakes + EXCLUDED.total_mistakes,
            recent_grades = EXCLUDED.recent_grades,
            recent_mistakes = EXCLUDED.recent_mistakes,
            last_reviewed = EXCLUDED.last_reviewed,
            clean_writes = EXCLUDED.clean_writes
    ''', (character, user_id, next_review_date, new_interval, new_ease,
           today_str, mistakes, new_grades, new_mist, today_str, new_clean))
    conn.commit()
    conn.close()
    log_activity(user_id, "write", character, grade, mistakes)
    logging.info(f"[HW] {character} graded {grade} ({mistakes} mistakes) "
                 f"→ next review in {new_interval}d"
                 + (" [REQUEUED this session]" if requeue else ""))
    return requeue


@_cached(ttl=20)
def get_handwriting_stats(user_id):
    """Counts for the handwriting sidebar widget."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total unique chars across studying+mastered vocab
    cursor.execute("""SELECT v.chinese FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
    rows = cursor.fetchall()
    unique_chars = set()
    for r in rows:
        for ch in r[0]:
            if _is_cjk(ch):
                unique_chars.add(ch)
    total = len(unique_chars)

    cursor.execute("SELECT COUNT(*) FROM handwriting_progress WHERE user_id = %s",
                   (user_id,))
    practiced = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM handwriting_progress "
                   "WHERE user_id = %s AND interval >= 21", (user_id,))
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


@_cached(ttl=20)
def bank_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FILTER (WHERE status = 'active'),
               COUNT(*) FILTER (WHERE status = 'flagged'),
               COUNT(DISTINCT vocab_chinese) FILTER (WHERE status = 'active')
        FROM sentence_bank""")
    active, flagged, covered = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM vocab")
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


def get_weak_characters(user_id, limit=50, min_attempts=1):
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
        WHERE user_id = %s AND review_count >= %s
    """, (user_id, min_attempts))
    rows = [dict(r) for r in cursor.fetchall()]

    # pull word context for the cue, same as the normal session
    cursor.execute("""SELECT v.chinese, v.pinyin, v.english, p.review_count
                      FROM vocab v JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE p.review_count > 0""", (user_id,))
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


def get_struggle_session(user_id, characters):
    """Build a drill queue for an explicit list of characters (the
    'drill my weak characters' mode). Each character carries full state so
    grades still feed the SRS. Order preserved as given."""
    if not characters:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT v.chinese, v.pinyin, v.english,
                             COALESCE(p.review_count, 0) AS review_count
                      FROM vocab v LEFT JOIN vocab_progress p
                        ON p.vocab_id = v.id AND p.user_id = %s
                      WHERE v.chinese ~ %s""",
                   (user_id, "[" + "".join(characters) + "]"))
    vocab_rows = [dict(r) for r in cursor.fetchall()]
    ph = ','.join(['%s'] * len(characters))
    cursor.execute(f"SELECT * FROM handwriting_progress "
                   f"WHERE user_id = %s AND character IN ({ph})",
                   [user_id] + list(characters))
    pmap = {r['character']: dict(r) for r in cursor.fetchall()}
    conn.close()
    session = []
    for ch in characters:
        session.append(_hw_entry(ch, pmap.get(ch) is None, 1,
                                 pmap.get(ch), vocab_rows))
    return session




def get_char_state(user_id, character):
    """Current stored handwriting state for one character (or None), used to
    roll recent-grade/mistake history correctly across repeated drills."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM handwriting_progress "
                   "WHERE user_id = %s AND character = %s", (user_id, character))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None



# ==========================================
# ACTIVITY LOG + FRIENDLY RIVALRY
#
# Deliberately compares EFFORT (cards done, streaks, consistency) rather
# than lifetime totals. One of you started months earlier, so a raw
# leaderboard would be permanently discouraging for the other and would
# stop being motivating for either.
# ==========================================
# One row per answered card, by the skill it used: reading a word or
# sentence, hearing one, saying one, typing one, writing a character, a
# grammar structure, a tone item, or a game round.
ACTIVITY_KINDS = {"read": "Reading", "listen": "Listening", "speak": "Speaking",
                  "type": "Typing", "write": "Handwriting", "grammar": "Grammar",
                  "tones": "Tones", "games": "Games"}

# Time ledger: which strand of study each page's minutes belong to.
ACTIVITY_STRAND = {"words": "study", "grammar": "study", "tones": "study",
                   "pairs": "study", "handwriting": "study",
                   "sentences": "use", "reading": "use", "games": "play"}
STRANDS = {"study": "Words, grammar, tones & writing",
           "use": "Listening, reading & speaking",
           "play": "Games"}
MAX_SESSION_SECONDS = 45 * 60      # a tab left open doesn't count as study


def log_activity(user_id, kind, item=None, grade=None, mistakes=0):
    """Record one graded card. Never raises: a logging failure must not
    interrupt someone's study session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO activity_log
                          (user_id, kind, item, grade, mistakes)
                          VALUES (%s, %s, %s, %s, %s)""",
                       (user_id, kind, (item or "")[:80], grade, mistakes or 0))
        conn.commit()
        conn.close()
        clear_caches()
    except Exception as e:
        logging.warning(f"[ACTIVITY] not logged: {e}")


@_cached(ttl=20)
def activity_totals(user_id, days=7):
    """Per-kind counts over the last `days` days, plus today's total."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT kind, COUNT(*) FROM activity_log
                      WHERE user_id = %s AND day > CURRENT_DATE - %s::integer
                      GROUP BY kind""", (user_id, days))
    by_kind = {k: n for k, n in cursor.fetchall()}
    cursor.execute("""SELECT COUNT(*) FROM activity_log
                      WHERE user_id = %s AND day = CURRENT_DATE""", (user_id,))
    today = cursor.fetchone()[0] or 0
    cursor.execute("""SELECT COUNT(*) FILTER (WHERE grade >= 2), COUNT(*)
                      FROM activity_log
                      WHERE user_id = %s AND day > CURRENT_DATE - %s::integer
                        AND grade IS NOT NULL""", (user_id, days))
    good, total = cursor.fetchone()
    conn.close()
    return {"by_kind": by_kind, "today": today,
            "week_total": sum(by_kind.values()),
            "accuracy": round(100.0 * good / total) if total else None}


@_cached(ttl=20)
def activity_streak(user_id):
    """Consecutive days studied, counting back from today (or yesterday, so
    the streak isn't shown as broken before you've studied today)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT DISTINCT day FROM activity_log
                      WHERE user_id = %s ORDER BY day DESC LIMIT 400""",
                   (user_id,))
    days = [r[0] for r in cursor.fetchall()]
    conn.close()
    if not days:
        return 0
    from datetime import timedelta
    today = date.today()
    cursor_day = today if days[0] == today else today - timedelta(days=1)
    streak = 0
    for d in days:
        if d == cursor_day:
            streak += 1
            cursor_day -= timedelta(days=1)
        elif d < cursor_day:
            break
    return streak


def daily_series(user_id, days=14):
    """[(day, count)] for a small activity chart, zero-filled."""
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT day, COUNT(*) FROM activity_log
                      WHERE user_id = %s AND day > CURRENT_DATE - %s::integer
                      GROUP BY day""", (user_id, days))
    counts = {d: n for d, n in cursor.fetchall()}
    conn.close()
    today = date.today()
    return [(today - timedelta(days=i), counts.get(today - timedelta(days=i), 0))
            for i in range(days - 1, -1, -1)]


def log_study_session(user_id, activity, seconds, in_plan=False, items=0):
    """Record one finished session in the time ledger. Never raises."""
    try:
        seconds = max(0, min(int(seconds or 0), MAX_SESSION_SECONDS))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO study_sessions
                          (user_id, day, activity, seconds, items, in_plan)
                          VALUES (%s, %s, %s, %s, %s, %s)""",
                       (user_id, date.today(), activity, seconds, int(items or 0),
                        bool(in_plan)))
        conn.commit()
        conn.close()
        clear_caches()
    except Exception as e:
        logging.warning(f"[LEDGER] not logged: {e}")


def plan_done_today(user_id):
    """Plan steps finished today (as step keys)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT DISTINCT activity FROM study_sessions
                      WHERE user_id = %s AND day = %s AND in_plan""",
                   (user_id, date.today()))
    out = {r[0] for r in cursor.fetchall()}
    conn.close()
    return out


def mark_plan_complete(user_id):
    """Record that today's whole plan is done (once per day)."""
    if "plan_complete" not in plan_done_today(user_id):
        log_study_session(user_id, "plan_complete", 0, in_plan=True)


@_cached(ttl=20)
def study_minutes(user_id, days=7):
    """Minutes by activity and by strand over the last `days` days, plus the
    number of days the whole plan was done and days with any study."""
    from datetime import timedelta
    since = date.today() - timedelta(days=days - 1)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT activity, SUM(seconds) FROM study_sessions
                      WHERE user_id = %s AND day >= %s GROUP BY activity""",
                   (user_id, since))
    by_activity = {a: round((sec or 0) / 60) for a, sec in cursor.fetchall()
                   if a != "plan_complete"}
    cursor.execute("""SELECT COUNT(DISTINCT day) FILTER (WHERE activity = 'plan_complete'),
                             COUNT(DISTINCT day) FILTER (WHERE activity <> 'plan_complete')
                      FROM study_sessions WHERE user_id = %s AND day >= %s""",
                   (user_id, since))
    plan_days, study_days = cursor.fetchone()
    conn.close()
    by_strand = {}
    for a, m in by_activity.items():
        k = ACTIVITY_STRAND.get(a, "study")
        by_strand[k] = by_strand.get(k, 0) + m
    return {"by_activity": by_activity, "by_strand": by_strand,
            "total": sum(by_activity.values()), "plan_days": plan_days or 0,
            "study_days": study_days or 0}


def recent_activity(limit=12):
    """Combined feed across everyone, for the 'what's she been up to' view."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT u.display_name, a.kind, a.day, COUNT(*) AS n
                      FROM activity_log a JOIN users u ON u.id = a.user_id
                      WHERE a.day > CURRENT_DATE - 14
                      GROUP BY u.display_name, a.kind, a.day
                      ORDER BY a.day DESC, n DESC LIMIT %s""", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ---------- nudges ----------
def send_nudge(from_user, to_user, message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO nudges (from_user, to_user, message)
                      VALUES (%s, %s, %s)""",
                   (from_user, to_user, message[:280]))
    conn.commit()
    conn.close()


def unseen_nudges(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT n.id, n.message, n.created_at, u.display_name
                      FROM nudges n JOIN users u ON u.id = n.from_user
                      WHERE n.to_user = %s AND n.seen_at IS NULL
                      ORDER BY n.created_at""", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def mark_nudges_seen(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""UPDATE nudges SET seen_at = NOW()
                      WHERE to_user = %s AND seen_at IS NULL""", (user_id,))
    conn.commit()
    conn.close()


def other_users(user_id):
    return [u for u in list_users() if u["id"] != user_id]



# ==========================================
# HERBS (for the Chinese-medicine handwriting set)
# Loaded from data/herbs.csv - export your Herb Dojo list to that file.
# Column names are matched loosely, so most exports work unchanged.
# ==========================================
HERB_CSV_PATH = VOCAB_CSV_PATH.parent / "herbs.csv"

_HERB_COLUMNS = {
    "chinese": ["chinese", "hanzi", "characters", "herb", "name_cn",
                "chinese_name", "中文", "药名", "hanzi_name"],
    "pinyin": ["pinyin", "py", "romanisation", "romanization", "pin_yin",
               "pinyin_name", "拼音"],
    "english": ["english", "meaning", "translation", "en", "common_name",
                "english_name", "gloss", "function", "actions"],
    "category": ["category", "class", "group", "chapter", "type", "family"],
    "tier": ["tier", "level", "priority", "importance", "rank"],
    "latin": ["latin", "pharmaceutical", "lat", "botanical"],
    "alt_script": ["alt_script", "traditional", "simplified", "alt", "other"],
}


def _match_herb_columns(df_columns):
    """Map a Herb Dojo export's columns onto what we need, case- and
    separator-insensitively."""
    norm = {c.strip().lower().replace(" ", "_").replace("-", "_"): c
            for c in df_columns}
    found = {}
    for key, options in _HERB_COLUMNS.items():
        for opt in options:
            if opt in norm:
                found[key] = norm[opt]
                break
    return found


def import_herbs_from_csv(path=None, force=False):
    """Import the herb list. Returns (added, skipped, error_message)."""
    csv_path = path or HERB_CSV_PATH
    if not os.path.exists(csv_path):
        return 0, 0, (f"No herb list found at {csv_path}. Export your herbs "
                      f"to that file with a Chinese column.")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return 0, 0, f"Could not read {csv_path}: {e}"

    cols = _match_herb_columns(df.columns)
    if "chinese" not in cols:
        return 0, 0, (f"Couldn't find a Chinese column in {list(df.columns)}. "
                      f"Rename one to 'Chinese'.")

    today_str = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese FROM herbs")
    existing = {r[0] for r in cursor.fetchall()}

    fresh, seen = [], set()
    for _i, row in df.iterrows():
        ch = str(row.get(cols["chinese"], "")).strip()
        if not ch or ch.lower() == "nan" or ch in existing or ch in seen:
            continue
        if not any(_is_cjk(c) for c in ch):
            continue
        seen.add(ch)
        def val(key):
            c = cols.get(key)
            if not c:
                return ""
            v = str(row.get(c, "")).strip()
            return "" if v.lower() == "nan" else v
        try:
            tier = int(float(val("tier") or 9))
        except ValueError:
            tier = 9
        fresh.append((ch, val("pinyin"), val("english"), val("category"),
                      tier, val("latin"), val("alt_script"), today_str))

    if fresh:
        psycopg2.extras.execute_values(
            cursor,
            "INSERT INTO herbs (chinese, pinyin, english, category, tier, "
            "latin, alt_script, date_added) VALUES %s "
            "ON CONFLICT (chinese) DO NOTHING", fresh, page_size=200)
    conn.commit()
    conn.close()
    _HERB_CONTEXT_CACHE["map"] = None
    clear_caches()
    logging.info(f"Herb import: {len(fresh)} new, {len(df) - len(fresh)} skipped.")
    return len(fresh), len(df) - len(fresh), ""


def herb_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM herbs")
    n = cursor.fetchone()[0]
    conn.close()
    return n or 0


def herb_characters():
    """Every distinct character used across the herb names, with the herbs
    it appears in."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT chinese, pinyin, english, tier, latin, alt_script
                      FROM herbs ORDER BY COALESCE(tier, 9), id""")
    herbs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    by_char = {}
    for h in herbs:
        for ch in h["chinese"]:
            if _is_cjk(ch):
                by_char.setdefault(ch, []).append(h)
    # herbs already arrive in tier order, so entry [0] is the most
    # important herb containing that character - the right one to cue with
    return by_char, herbs


def get_herb_session(user_id, new_count=5):
    """Handwriting queue built HERB BY HERB rather than character by character.

    A herb name is learned as a unit: 麻黃 is drilled as 麻 immediately
    followed by 黃, with the whole name on screen throughout and each
    character revealed as you write it. Practising 黃 in isolation, weeks
    away from 麻, never teaches you the herb.

    SRS is still tracked per character, so a character met in one herb
    counts towards every other herb containing it.
    """
    from radical_engine import describe_word
    today_str = date.today().isoformat()
    _by_char, herbs = herb_characters()
    if not herbs:
        return []

    all_chars = sorted({c for h in herbs for c in h["chinese"] if _is_cjk(c)})
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    ph = ",".join(["%s"] * len(all_chars))
    cursor.execute(f"""SELECT * FROM handwriting_progress
                       WHERE user_id = %s AND character IN ({ph})""",
                   [user_id] + all_chars)
    progress = {r["character"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    def herb_cards(herb):
        """One card per character, carrying the herb as shared context."""
        chars = [c for c in herb["chinese"] if _is_cjk(c)]
        cards = []
        for i, ch in enumerate(chars):
            is_new = ch not in progress
            entry = _hw_entry(ch, is_new, 1, progress.get(ch), [])
            # Cue is the herb, not a vocabulary word
            entry["word"] = herb["chinese"]
            entry["word_pinyin"] = herb.get("pinyin") or ""
            entry["word_english"] = herb.get("english") or ""
            # Where this character sits within the name
            entry["group_word"] = herb["chinese"]
            entry["group_index"] = i
            entry["group_total"] = len(chars)
            entry["group_written"] = chars[:i]      # already written, show them
            entry["herb_tier"] = herb.get("tier") or 9
            entry["herb_latin"] = herb.get("latin") or ""
            entry["herb_alt"] = herb.get("alt_script") or ""
            rad = describe_word(ch)
            first = rad["characters"][0] if rad["characters"] else {}
            entry["radicals"] = first.get("components", [])
            entry["radical_note"] = first.get("substance_note") or ""
            entry["substance"] = first.get("substance") or ""
            cards.append(entry)
        return cards

    def herb_is_due(herb):
        chars = [c for c in herb["chinese"] if _is_cjk(c)]
        seen = [c for c in chars if c in progress]
        if not seen:
            return False
        return any(progress[c]["next_review_date"] <= today_str for c in seen)

    def herb_is_new(herb):
        chars = [c for c in herb["chinese"] if _is_cjk(c)]
        return any(c not in progress for c in chars)

    due_herbs = [h for h in herbs if herb_is_due(h)]
    new_herbs = [h for h in herbs if herb_is_new(h) and h not in due_herbs]
    # herbs already arrive in tier order, so the most clinically important
    # names are introduced first
    new_herbs = new_herbs[:max(0, new_count)]

    session = []
    for h in due_herbs + new_herbs:
        session.extend(herb_cards(h))
    return session


def herb_character_counts(user_id):
    by_char, herbs = herb_characters()
    if not by_char:
        return {"herbs": 0, "characters": 0, "due": 0, "new": 0}
    chars = list(by_char)
    today_str = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    ph = ",".join(["%s"] * len(chars))
    cursor.execute(f"""SELECT character, next_review_date FROM handwriting_progress
                       WHERE user_id = %s AND character IN ({ph})""",
                   [user_id] + chars)
    seen = dict(cursor.fetchall())
    conn.close()
    tier1 = {c for h in herbs if (h.get("tier") or 9) == 1
             for c in h["chinese"] if _is_cjk(c)}
    return {"herbs": len(herbs), "characters": len(chars),
            "tier1_characters": len(tier1),
            "due": sum(1 for c in chars if c in seen and seen[c] <= today_str),
            "new": sum(1 for c in chars if c not in seen)}



# ==========================================
# READING - sentences bounded by what you can write
# ==========================================
def known_characters(user_id):
    """Characters this user has drilled in the handwriting section.

    Deliberately the same set the handwriting counters report, so
    "65 characters studied" and what the reading section will use are
    always the same number.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT character FROM handwriting_progress WHERE user_id = %s",
                   (user_id,))
    chars = {r[0] for r in cursor.fetchall()}
    conn.close()
    return chars


def recent_characters(user_id, limit=12):
    """The characters this user has most recently started writing.

    Reading practice should pull on what you have just learned, not only on
    what you learned months ago - so these are offered to the generator as
    characters to build around, and used to rank stored sentences.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT character FROM handwriting_progress
                      WHERE user_id = %s
                      ORDER BY COALESCE(last_reviewed, first_seen_date) DESC,
                               id DESC
                      LIMIT %s""", (user_id, limit))
    chars = [r[0] for r in cursor.fetchall()]
    conn.close()
    return chars


def due_characters(user_id):
    """Characters whose handwriting review is due - worth seeing in print."""
    today_str = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT character FROM handwriting_progress
                      WHERE user_id = %s AND next_review_date <= %s""",
                   (user_id, today_str))
    chars = {r[0] for r in cursor.fetchall()}
    conn.close()
    return chars


def reading_bank_add(chinese, english, char_set, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO reading_bank
                        (chinese, english, char_set, char_count, created_by)
                      VALUES (%s, %s, %s, %s, %s)
                      ON CONFLICT (chinese) DO NOTHING""",
                   (chinese, english, "".join(sorted(char_set)),
                    len([c for c in chinese if _is_cjk(c)]), user_id))
    added = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return added


def reading_bank_for(user_id, known, max_unknown=3, limit=20,
                     focus=None):
    """Stored sentences this user can read now.

    A sentence generated for one person is reusable by the other as soon
    as they know enough characters, so the bank fills up for both of you.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT b.id, b.chinese, b.english,
                             COALESCE(p.seen_count, 0) AS seen_count
                      FROM reading_bank b
                      LEFT JOIN reading_progress p
                             ON p.sentence_id = b.id AND p.user_id = %s
                      ORDER BY COALESCE(p.seen_count, 0), b.id""", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    focus = set(focus or [])
    out = []
    for r in rows:
        chars = {c for c in r["chinese"] if _is_cjk(c)}
        unknown = {c for c in chars if c not in known}
        if len(unknown) <= max_unknown:
            r["unknown"] = sorted(unknown)
            # how much of what you are currently working on this exercises
            r["focus_hits"] = len(chars & focus)
            out.append(r)
    # unseen first, then sentences that drill your current characters
    out.sort(key=lambda r: (r["seen_count"], -r["focus_hits"], r["id"]))
    return out[:limit]


def reading_mark_seen(user_id, sentence_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO reading_progress
                        (user_id, sentence_id, seen_count, last_seen)
                      VALUES (%s, %s, 1, %s)
                      ON CONFLICT (user_id, sentence_id) DO UPDATE SET
                        seen_count = reading_progress.seen_count + 1,
                        last_seen = EXCLUDED.last_seen""",
                   (user_id, sentence_id, date.today().isoformat()))
    conn.commit()
    conn.close()


def reading_stats(user_id):
    known = known_characters(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reading_bank")
    total = cursor.fetchone()[0] or 0
    cursor.execute("""SELECT COUNT(*) FROM reading_progress
                      WHERE user_id = %s AND seen_count > 0""", (user_id,))
    read = cursor.fetchone()[0] or 0
    conn.close()
    try:
        from character_curriculum import coverage_for
        coverage = round(coverage_for(known), 1)
    except Exception:
        coverage = 0.0
    return {"known_characters": len(known), "coverage": coverage,
            "sentences_in_bank": total, "sentences_read": read}


init_db()
import_vocab_from_csv()


# ==========================================
# GRAMMAR DRILLS
# ==========================================
def grammar_known_vocab(user_id):
    """The learner's well-studied words, best-known first. Falls back to
    anything reviewed once while the list is still short."""
    from config import (GRAMMAR_KNOWN_MIN_REVIEWS, GRAMMAR_KNOWN_MIN_INTERVAL,
                        GRAMMAR_KNOWN_FLOOR, GRAMMAR_VOCAB_CAP)
    conn = get_connection()
    cursor = conn.cursor()
    query = """SELECT v.chinese FROM vocab v
               JOIN vocab_progress p ON p.vocab_id = v.id AND p.user_id = %s
               WHERE p.review_count >= %s AND COALESCE(p.interval, 0) >= %s
                 AND v.chinese ~ '^[一-鿿]+$'
               ORDER BY p.review_count DESC, p.interval DESC LIMIT %s"""
    cursor.execute(query, (user_id, GRAMMAR_KNOWN_MIN_REVIEWS,
                           GRAMMAR_KNOWN_MIN_INTERVAL, GRAMMAR_VOCAB_CAP))
    words = [r[0] for r in cursor.fetchall()]
    if len(words) < GRAMMAR_KNOWN_FLOOR:
        cursor.execute(query, (user_id, 1, 0, GRAMMAR_VOCAB_CAP))
        words = [r[0] for r in cursor.fetchall()]
    conn.close()
    return list(dict.fromkeys(words))


def grammar_china_pairs():
    """(China word, Malaysian word) pairs from the tagged vocabulary, so the
    drill writer prefers the Malaysian word."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chinese, english FROM vocab WHERE tag = 'China'")
    pairs = []
    for zh, en in cursor.fetchall():
        m = re.search(r"\(Malaysia: (\S+) ", en or "")
        if m:
            pairs.append((zh, m.group(1)))
    conn.close()
    return pairs


def grammar_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM grammar_progress WHERE user_id = %s", (user_id,))
    rows = {r["structure_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()
    return rows


def grammar_save_progress(user_id, structure_id, next_review_date, interval,
                          ease, score):
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO grammar_progress (user_id, structure_id, next_review_date,
               interval, ease_factor, review_count, last_score, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)
        ON CONFLICT (user_id, structure_id) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval, ease_factor = EXCLUDED.ease_factor,
            review_count = grammar_progress.review_count + 1,
            last_score = EXCLUDED.last_score, last_seen = EXCLUDED.last_seen
    """, (user_id, structure_id, next_review_date, interval, ease, score, today, today))
    conn.commit()
    conn.close()


def grammar_new_today(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM grammar_progress WHERE user_id = %s "
                   "AND first_seen = %s", (user_id, date.today().isoformat()))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def grammar_pick_set(user_id, structure_id, known_count):
    """A stored drill set worth reusing, or None if a fresh one should be
    written (none stored, all used recently, or vocabulary has grown)."""
    from config import GRAMMAR_REFRESH_GROWTH
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT id, known_count, payload, served_count, last_served
                      FROM grammar_drill_sets
                      WHERE user_id = %s AND structure_id = %s
                      ORDER BY created_at DESC""", (user_id, structure_id))
    sets = [dict(r) for r in cursor.fetchall()]
    conn.close()
    today = date.today().isoformat()
    fresh_enough = [x for x in sets
                    if known_count <= (x["known_count"] or 0) * (1 + GRAMMAR_REFRESH_GROWTH)]
    usable = [x for x in fresh_enough if x["served_count"] < 2 and x["last_served"] != today]
    if not usable:
        return None
    pick = min(usable, key=lambda x: (x["served_count"], x["last_served"] or ""))
    pick["payload"] = json.loads(pick["payload"])
    return pick


def grammar_recent_sentences(user_id, structure_id, limit=3):
    from grammar_drills import sentences_in
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT payload FROM grammar_drill_sets
                      WHERE user_id = %s AND structure_id = %s
                      ORDER BY created_at DESC LIMIT %s""", (user_id, structure_id, limit))
    out = []
    for (payload,) in cursor.fetchall():
        try:
            out += sentences_in(json.loads(payload))
        except Exception:
            pass
    conn.close()
    return out


def grammar_save_set(user_id, structure_id, known_count, payload, keep=4):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO grammar_drill_sets (user_id, structure_id,
                          known_count, payload) VALUES (%s, %s, %s, %s) RETURNING id""",
                   (user_id, structure_id, known_count,
                    json.dumps(payload, ensure_ascii=False)))
    new_id = cursor.fetchone()[0]
    cursor.execute("""DELETE FROM grammar_drill_sets WHERE user_id = %s
                      AND structure_id = %s AND id NOT IN (
                          SELECT id FROM grammar_drill_sets WHERE user_id = %s
                          AND structure_id = %s ORDER BY created_at DESC, id DESC
                          LIMIT %s)""",
                   (user_id, structure_id, user_id, structure_id, keep))
    conn.commit()
    conn.close()
    return new_id


def grammar_mark_served(set_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""UPDATE grammar_drill_sets SET served_count = served_count + 1,
                      last_served = %s WHERE id = %s""",
                   (date.today().isoformat(), set_id))
    conn.commit()
    conn.close()


# ==========================================
# VOCABULARY ENGINE
# ==========================================
_WORD_COLS = """v.id, v.chinese, v.pinyin, v.english, v.tag, v.freq_rank,
                v.from_lessons"""


def _track_row(r):
    return {"interval": r["interval"], "ease": r["ease"],
            "next_review_date": r["next_review_date"], "reps": r["reps"],
            "lapses": r["lapses"], "streak": r["streak"],
            "last_mode": r["last_mode"], "last_result": r["last_result"],
            "introduced_on": r["introduced_on"]}


def sync_word_skills(user_id):
    """Keep the recognition schedule in step with vocab_progress, which the
    classic session, handwriting and reading still use:
    - words studied before this engine existed get a recognition track
      seeded from their existing progress (nothing is lost);
    - if the classic session has reviewed a word more recently, its
      recognition track catches up."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease,
               next_review_date, reps, lapses, streak, introduced_on)
        SELECT p.user_id, p.vocab_id, 'recognition', COALESCE(p.interval, 0),
               COALESCE(p.ease_factor, 2.5), p.next_review_date, p.review_count, 0,
               CASE WHEN COALESCE(p.interval, 0) >= 1 THEN LEAST(p.review_count, 3) ELSE 0 END,
               %s
        FROM vocab_progress p
        WHERE p.user_id = %s AND p.review_count > 0
        ON CONFLICT (user_id, vocab_id, skill) DO NOTHING
    """, ("seeded", user_id))
    cursor.execute("""
        UPDATE word_skill s SET interval = COALESCE(p.interval, 0),
               ease = COALESCE(p.ease_factor, 2.5),
               next_review_date = p.next_review_date, reps = p.review_count
        FROM vocab_progress p
        WHERE s.user_id = %s AND s.skill = 'recognition'
          AND p.user_id = s.user_id AND p.vocab_id = s.vocab_id
          AND p.review_count > s.reps
    """, (user_id,))
    conn.commit()
    conn.close()


def word_tracks(user_id, vocab_ids):
    """(vocab_id, skill) -> track for the given words."""
    if not vocab_ids:
        return {}
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM word_skill WHERE user_id = %s AND vocab_id = ANY(%s)",
                   (user_id, list(vocab_ids)))
    out = {(r["vocab_id"], r["skill"]): _track_row(r) for r in cursor.fetchall()}
    conn.close()
    return out


def due_words(user_id, skill, limit, today=None):
    """Words whose `skill` is due, most overdue first, repeated misses
    breaking ties."""
    today = (today or date.today()).isoformat()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""
        SELECT {_WORD_COLS} FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
        WHERE s.user_id = %s AND s.skill = %s
          AND COALESCE(s.next_review_date, '') <= %s
        ORDER BY s.next_review_date NULLS FIRST, s.lapses DESC, v.freq_rank NULLS LAST
        LIMIT %s
    """, (user_id, skill, today, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def count_due(user_id, today=None):
    today = (today or date.today()).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM word_skill WHERE user_id = %s
                      AND COALESCE(next_review_date, '') <= %s""", (user_id, today))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def production_unlockable(user_id, limit):
    """Words recognised reliably enough to start producing them."""
    from vocab_engine import UNLOCK_MIN_INTERVAL, UNLOCK_MIN_STREAK
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""
        SELECT {_WORD_COLS} FROM word_skill r JOIN vocab v ON v.id = r.vocab_id
        WHERE r.user_id = %s AND r.skill = 'recognition'
          AND r.interval >= %s AND r.streak >= %s
          AND v.chinese ~ '^[一-鿿]{{1,6}}$' AND COALESCE(v.tag, '') <> 'China'
          AND NOT EXISTS (SELECT 1 FROM word_skill p WHERE p.user_id = r.user_id
                          AND p.vocab_id = r.vocab_id AND p.skill = 'production')
        ORDER BY v.freq_rank NULLS LAST, v.id
        LIMIT %s
    """, (user_id, UNLOCK_MIN_INTERVAL, UNLOCK_MIN_STREAK, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def new_word_candidates(user_id, limit=40):
    """(lesson words, frequency words) not yet introduced, each in frequency
    order. China-tagged (mainland) words wait until their Malaysian partner
    has been introduced."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    base = f"""
        SELECT {_WORD_COLS} FROM vocab v
        WHERE NOT EXISTS (SELECT 1 FROM word_skill s WHERE s.user_id = %s
                          AND s.vocab_id = v.id AND s.skill = 'recognition')
          AND v.chinese !~ '[，。！？,.!?]'
    """
    cursor.execute(base + " AND v.from_lessons ORDER BY v.freq_rank NULLS LAST, v.id LIMIT %s",
                   (user_id, limit))
    lessons = [dict(r) for r in cursor.fetchall()]
    cursor.execute(base + " AND NOT v.from_lessons AND v.freq_rank IS NOT NULL "
                   "ORDER BY v.freq_rank LIMIT %s", (user_id, limit))
    frequency = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""SELECT v.chinese FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                      WHERE s.user_id = %s AND s.skill = 'recognition'""", (user_id,))
    known = {r[0] for r in cursor.fetchall()}
    conn.close()

    def partner_ready(w):
        if w.get("tag") != "China":
            return True
        m = re.search(r"\(Malaysia: (\S+) ", w.get("english") or "")
        return bool(m) and m.group(1) in known
    return [w for w in lessons if partner_ready(w)], [w for w in frequency if partner_ready(w)]


def introduced_today(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM word_skill WHERE user_id = %s
                      AND skill = 'recognition' AND introduced_on = %s""",
                   (user_id, date.today().isoformat()))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def save_word_track(user_id, vocab_id, skill, track, mode=None):
    """Store a skill track. The recognition track is mirrored into
    vocab_progress so everything else in the app keeps seeing progress."""
    track = dict(track)
    track["next_review_date"] = track.get("next_review_date") or date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease,
               next_review_date, reps, lapses, streak, last_mode, last_result,
               introduced_on)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, vocab_id, skill) DO UPDATE SET
            interval = EXCLUDED.interval, ease = EXCLUDED.ease,
            next_review_date = EXCLUDED.next_review_date, reps = EXCLUDED.reps,
            lapses = EXCLUDED.lapses, streak = EXCLUDED.streak,
            last_mode = EXCLUDED.last_mode, last_result = EXCLUDED.last_result
    """, (user_id, vocab_id, skill, track.get("interval", 0), track.get("ease", 2.5),
          track.get("next_review_date"), track.get("reps", 0), track.get("lapses", 0),
          track.get("streak", 0), mode or track.get("last_mode"), track.get("last_result"),
          track.get("introduced_on") or date.today().isoformat()))
    if skill == "recognition":
        cursor.execute("""
            INSERT INTO vocab_progress (user_id, vocab_id, next_review_date, interval,
                   ease_factor, review_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, vocab_id) DO UPDATE SET
                next_review_date = EXCLUDED.next_review_date,
                interval = EXCLUDED.interval, ease_factor = EXCLUDED.ease_factor,
                review_count = EXCLUDED.review_count
        """, (user_id, vocab_id, track.get("next_review_date"), track.get("interval", 0),
              track.get("ease", 2.5), track.get("reps", 0)))
    conn.commit()
    conn.close()
    clear_caches()


def log_word_attempt(user_id, vocab_id, skill, mode, result, detail=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO word_attempts (user_id, vocab_id, skill, mode,
                          result, detail) VALUES (%s, %s, %s, %s, %s, %s)""",
                   (user_id, vocab_id, skill, mode, result,
                    json.dumps(detail or {}, ensure_ascii=False)))
    conn.commit()
    conn.close()


def mode_error_rates(user_id, days=30):
    """mode -> share of recent attempts in that mode that were missed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT mode, COUNT(*) FILTER (WHERE result = 'wrong'),
                             COUNT(*) FILTER (WHERE result <> 'ungraded')
                      FROM word_attempts WHERE user_id = %s
                        AND created_at > NOW() - (%s || ' days')::interval
                      GROUP BY mode""", (user_id, str(days)))
    out = {m: (w / n if n else 0.0) for m, w, n in cursor.fetchall()}
    conn.close()
    return out


def word_attempts(user_id, vocab_id, limit=30):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT skill, mode, result, detail, created_at FROM word_attempts
                      WHERE user_id = %s AND vocab_id = %s
                      ORDER BY created_at DESC, id DESC LIMIT %s""", (user_id, vocab_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def plan_word_session(user_id, rng=None, review_cap=None, new_cap=None, unlocks=True):
    """Everything the session builder needs, gathered in one place.
    review_cap / new_cap tighten the usual limits (the short day uses them);
    they never loosen the daily cap on new words."""
    from config import (VOCAB_NEW_PER_SESSION, VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT,
                        VOCAB_SESSION_REVIEWS, VOCAB_UNLOCKS_PER_SESSION,
                        VOCAB_LESSON_SHARE)
    import vocab_engine as ve
    review_cap = VOCAB_SESSION_REVIEWS if review_cap is None else min(review_cap, VOCAB_SESSION_REVIEWS)
    sync_word_skills(user_id)
    due = count_due(user_id)
    rec = due_words(user_id, "recognition", review_cap)
    prod = due_words(user_id, "production", review_cap)
    room = ve.new_word_allowance(due, introduced_today(user_id), VOCAB_NEW_PER_SESSION,
                                 VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT)
    if new_cap is not None:
        room = max(0, min(room, new_cap))
    lessons, frequency = new_word_candidates(user_id)
    new = ve.pick_new_words(lessons, frequency, room, VOCAB_LESSON_SHARE)
    # production starts only when the load is light enough for new material
    unlock_cap = VOCAB_UNLOCKS_PER_SESSION if unlocks and due <= VOCAB_BACKLOG_SOFT else 0
    unlock = production_unlockable(user_id, unlock_cap)
    ids = {w["id"] for w in rec + prod + unlock}
    items = ve.build_session(rec, prod, unlock, new, review_cap, unlock_cap,
                             mode_error_rates(user_id), word_tracks(user_id, ids), rng)
    import word_diagnosis as wd
    open_d = open_diagnoses(user_id, [it["word"]["id"] for it in items])
    for it in items:
        dg = open_d.get(it["word"]["id"])
        if dg and it["kind"] == "review":
            it["mode"] = wd.PREFERRED_MODE.get((dg["cause"], it["skill"]), it["mode"])
            it["confused_with"] = dg.get("confused_with")
    return {"items": items, "due": due, "new_allowed": room}


# ---- word content ---------------------------------------------------------
# A cached set is rewritten after this many uses (fresh sentences), or once the
# learner's known vocabulary has grown this much since it was written.
WORD_CONTENT_MAX_USES = 12
WORD_CONTENT_REFRESH_GROWTH = 0.5


def word_content_get(user_id, vocab_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT id, known_count, payload, uses FROM word_content
                      WHERE user_id = %s AND vocab_id = %s
                      ORDER BY created_at DESC, id DESC LIMIT 1""", (user_id, vocab_id))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    return {"id": r["id"], "known_count": r["known_count"], "uses": r["uses"],
            "payload": json.loads(r["payload"])}


def word_content_save(user_id, vocab_id, known_count, payload, keep=2):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO word_content (user_id, vocab_id, known_count, payload)
                      VALUES (%s, %s, %s, %s) RETURNING id""",
                   (user_id, vocab_id, known_count, json.dumps(payload, ensure_ascii=False)))
    new_id = cursor.fetchone()[0]
    cursor.execute("""DELETE FROM word_content WHERE user_id = %s AND vocab_id = %s
                      AND id NOT IN (SELECT id FROM word_content WHERE user_id = %s
                                     AND vocab_id = %s ORDER BY created_at DESC, id DESC
                                     LIMIT %s)""",
                   (user_id, vocab_id, user_id, vocab_id, keep))
    conn.commit()
    conn.close()
    return new_id


def word_content_used(content_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE word_content SET uses = uses + 1 WHERE id = %s", (content_id,))
    conn.commit()
    conn.close()


def word_pool(user_id, minimum=300):
    """Words to draw multiple-choice options from: the learner's introduced
    words, topped up with the most frequent words while that list is short."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT DISTINCT v.chinese, v.pinyin, v.english FROM word_skill s
                      JOIN vocab v ON v.id = s.vocab_id
                      WHERE s.user_id = %s AND s.skill = 'recognition'
                        AND v.chinese ~ '^[一-鿿]{1,6}$'""", (user_id,))
    pool = [dict(r) for r in cursor.fetchall()]
    if len(pool) < minimum:
        have = {w["chinese"] for w in pool}
        cursor.execute("""SELECT chinese, pinyin, english FROM vocab
                          WHERE freq_rank IS NOT NULL ORDER BY freq_rank LIMIT %s""",
                       (minimum * 2,))
        pool += [dict(r) for r in cursor.fetchall() if r["chinese"] not in have][:minimum - len(pool)]
    conn.close()
    return pool


def word_content_for(user_id, word, allow_generate=True, known=None):
    """The content to learn `word` through, for this learner.

    Reuses the cached set until it has been used WORD_CONTENT_MAX_USES times
    or the learner's vocabulary has grown enough to write richer sentences.
    Without a cached set (or when generation fails or isn't allowed), falls
    back to a vetted sentence-bank sentence, then to the word alone.
    Returns (payload, content_id or None)."""
    import word_content as wc
    if not re.fullmatch(r"[\u4e00-\u9fff]{1,8}", word.get("chinese") or ""):
        # old sentence cards and Latin-script entries: nothing to write
        cached = word_content_get(user_id, word["id"])
        return (cached["payload"], cached["id"]) if cached else \
            (wc.fallback_content(word, bank_get(word["chinese"])), None)
    cached = word_content_get(user_id, word["id"])
    known = known if known is not None else grammar_known_vocab(user_id)
    stale = cached and (
        cached["uses"] >= WORD_CONTENT_MAX_USES
        or (cached["uses"] >= 4 and len(known) > (cached["known_count"] or 0)
            * (1 + WORD_CONTENT_REFRESH_GROWTH)))
    if cached and not (stale and allow_generate):
        return cached["payload"], cached["id"]
    if allow_generate:
        structures = wc.practising_structures(grammar_progress(user_id), date.today())
        recent = [w for w in recent_words(user_id) if w != word["chinese"]]
        payload = wc.generate(word, known, structures, recent)
        if payload:
            if payload.get("reviewed", True):
                return payload, word_content_save(user_id, word["id"], len(known), payload)
            return payload, None
    if cached:
        return cached["payload"], cached["id"]
    return wc.fallback_content(word, bank_get(word["chinese"])), None


# ---- diagnosis ------------------------------------------------------------
def open_diagnoses(user_id, vocab_ids=None):
    """vocab_id -> the word's latest unresolved diagnosis."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    q = """SELECT d.*, v.chinese, v.pinyin, v.english FROM word_diagnosis d
           JOIN vocab v ON v.id = d.vocab_id
           WHERE d.user_id = %s AND d.resolved_at IS NULL"""
    params = [user_id]
    if vocab_ids is not None:
        q += " AND d.vocab_id = ANY(%s)"
        params.append(list(vocab_ids))
    cursor.execute(q + " ORDER BY d.created_at", params)
    out = {r["vocab_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()
    return out


def save_diagnosis(user_id, vocab_id, skill, diag):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO word_diagnosis (user_id, vocab_id, skill, cause, evidence,
                          confused_with) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                   (user_id, vocab_id, skill, diag["cause"],
                    json.dumps(diag.get("evidence") or [], ensure_ascii=False),
                    diag.get("confused_with")))
    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_id


def update_diagnosis(diag_id, remedy=None, note=None):
    conn = get_connection()
    cursor = conn.cursor()
    if remedy is not None:
        cursor.execute("UPDATE word_diagnosis SET remedy = %s WHERE id = %s",
                       (json.dumps(remedy, ensure_ascii=False), diag_id))
    if note is not None:
        cursor.execute("UPDATE word_diagnosis SET note = %s WHERE id = %s", (note, diag_id))
    conn.commit()
    conn.close()


def resolve_diagnosis(diag_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE word_diagnosis SET resolved_at = NOW() WHERE id = %s", (diag_id,))
    conn.commit()
    conn.close()


def word_attempts_all(user_id, vocab_id, limit=40):
    """Both skills, newest first (what the diagnosis reads)."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT skill, mode, result, detail, created_at FROM word_attempts
                      WHERE user_id = %s AND vocab_id = %s
                      ORDER BY created_at DESC, id DESC LIMIT %s""", (user_id, vocab_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def word_by_chinese(chinese):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT id, chinese, pinyin, english, tag FROM vocab WHERE chinese = %s
                      ORDER BY from_lessons DESC, freq_rank NULLS LAST LIMIT 1""", (chinese,))
    r = cursor.fetchone()
    conn.close()
    return dict(r) if r else None


def recent_words(user_id, days=14, limit=30):
    """Words introduced in the last `days` and answered correctly at least
    once - what grammar drills and new word sentences should recycle."""
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT v.chinese FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                      WHERE s.user_id = %s AND s.skill = 'recognition'
                        AND s.introduced_on >= %s AND s.introduced_on <> 'seeded'
                        AND (s.streak >= 1 OR s.interval >= 1)
                        AND v.chinese ~ '^[一-鿿]{1,6}$'
                      ORDER BY s.introduced_on DESC, v.freq_rank NULLS LAST LIMIT %s""",
                   (user_id, cutoff, limit))
    out = [r[0] for r in cursor.fetchall()]
    conn.close()
    return out


def network_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FILTER (WHERE skill = 'recognition'),
                             COUNT(*) FILTER (WHERE skill = 'production')
                      FROM word_skill WHERE user_id = %s AND reps > 0""", (user_id,))
    rec, prod = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM grammar_progress WHERE user_id = %s", (user_id,))
    gram = cursor.fetchone()[0]
    conn.close()
    return {"recognition": rec, "production": prod, "grammar": gram}


# ---- Sound & Pairing drills ------------------------------------------------
def introduced_words(user_id):
    """Every Chinese word the learner has been introduced to (recognition
    track exists), with what the drills need."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT v.id, v.chinese, v.pinyin, v.english, v.freq_rank, v.tag
                      FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                      WHERE s.user_id = %s AND s.skill = 'recognition'
                        AND v.chinese ~ '^[一-鿿]+$'""", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def single_char_words(chars):
    """char -> its own vocabulary entry (for 'on its own it means…')."""
    if not chars:
        return {}
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT DISTINCT ON (chinese) chinese, pinyin, english, freq_rank
                      FROM vocab WHERE chinese = ANY(%s)
                      ORDER BY chinese, from_lessons DESC, freq_rank NULLS LAST""", (list(chars),))
    out = {r["chinese"]: dict(r) for r in cursor.fetchall()}
    conn.close()
    return out


def drill_progress_get(user_id, drill):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM drill_progress WHERE user_id = %s AND drill = %s",
                   (user_id, drill))
    out = {r["key"]: {k: r[k] for k in ("interval", "ease", "next_review_date", "reps",
                                         "lapses", "streak", "last_result")}
           for r in cursor.fetchall()}
    conn.close()
    return out


def drill_progress_save(user_id, drill, key, track):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO drill_progress (user_id, drill, key, interval, ease, next_review_date,
               reps, lapses, streak, last_result, first_seen)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, drill, key) DO UPDATE SET
            interval = EXCLUDED.interval, ease = EXCLUDED.ease,
            next_review_date = EXCLUDED.next_review_date, reps = EXCLUDED.reps,
            lapses = EXCLUDED.lapses, streak = EXCLUDED.streak,
            last_result = EXCLUDED.last_result
    """, (user_id, drill, key, track.get("interval", 0), track.get("ease", 2.5),
          track.get("next_review_date") or date.today().isoformat(), track.get("reps", 0),
          track.get("lapses", 0), track.get("streak", 0), track.get("last_result"),
          date.today().isoformat()))
    conn.commit()
    conn.close()


def drill_new_today(user_id, drill):
    """Groups (tone) or families (pair) met for the first time today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM drill_progress WHERE user_id = %s
                      AND drill = %s AND first_seen = %s""",
                   (user_id, drill, date.today().isoformat()))
    n = cursor.fetchone()[0]
    conn.close()
    return n


# ---- games ----------------------------------------------------------------
def game_scores(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game, best, plays FROM game_scores WHERE user_id = %s", (user_id,))
    out = {g: {"best": b, "plays": p} for g, b, p in cursor.fetchall()}
    conn.close()
    return out


def save_game_score(user_id, game, score):
    """Record a finished game; returns True if it was a new best."""
    before = game_scores(user_id).get(game, {}).get("best", 0)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO game_scores (user_id, game, best, plays, last_played)
                      VALUES (%s, %s, %s, 1, %s)
                      ON CONFLICT (user_id, game) DO UPDATE SET
                          best = GREATEST(game_scores.best, EXCLUDED.best),
                          plays = game_scores.plays + 1, last_played = EXCLUDED.last_played""",
                   (user_id, game, score, date.today().isoformat()))
    conn.commit()
    conn.close()
    return score > before


def vocab_ids_for(chineses):
    """chinese -> vocab id, for the words that are in the vocabulary."""
    if not chineses:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT DISTINCT ON (chinese) chinese, id FROM vocab WHERE chinese = ANY(%s)
                      ORDER BY chinese, from_lessons DESC, freq_rank NULLS LAST""", (list(chineses),))
    out = dict(cursor.fetchall())
    conn.close()
    return out


# ---- sentence practice (Listen & speak) ------------------------------------
def sentence_practice_words(user_id, limit=40):
    """Words already introduced, for sentence listening and speaking: due
    recognition first, then words introduced in the last fortnight (weakest
    first), then the rest at random. Never a word you haven't met, so this
    page adds no new material. Each row carries both skill tracks."""
    from datetime import timedelta
    today = date.today().isoformat()
    fortnight = (date.today() - timedelta(days=14)).isoformat()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""
        SELECT {_WORD_COLS},
               r.interval AS rec_interval, r.next_review_date AS rec_due,
               r.introduced_on, p.next_review_date AS prod_due,
               p.interval AS prod_interval
        FROM word_skill r JOIN vocab v ON v.id = r.vocab_id
        LEFT JOIN word_skill p ON p.user_id = r.user_id AND p.vocab_id = r.vocab_id
                               AND p.skill = 'production'
        WHERE r.user_id = %s AND r.skill = 'recognition'
          AND v.chinese ~ '^[一-鿿]{{1,8}}$'
        ORDER BY (COALESCE(r.next_review_date, '') <= %s) DESC,
                 (COALESCE(r.introduced_on, '') >= %s) DESC,
                 r.interval ASC, RANDOM()
        LIMIT %s
    """, (user_id, today, fortnight, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def find_words(query, limit=20):
    """Vocabulary entries matching hanzi, pinyin or English, for the editor."""
    q = (query or "").strip()
    if not q:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT id, chinese, pinyin, english, tag, freq_rank, from_lessons
                      FROM vocab WHERE chinese = %s OR chinese LIKE %s
                         OR pinyin ILIKE %s OR english ILIKE %s
                      ORDER BY (chinese = %s) DESC, freq_rank NULLS LAST, id
                      LIMIT %s""",
                   (q, f"%{q}%", f"%{q}%", f"%{q}%", q, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
