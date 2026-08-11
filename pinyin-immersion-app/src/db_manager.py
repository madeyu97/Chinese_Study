# src/db_manager.py

import os
import hashlib
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
    MAX_REVIEWS_PER_DAY,
    NEW_WORDS_PER_DAY,
    RANDOM_BREADTH_PCT,
)
from handwriting_engine import (precision_for, precision_level,
                                score_character, get_stroke_count,
                                compute_next_review, choose_context_word)
from dictionary_engine import (derive_pinyin, cedict_gloss,
                               character_info, frequency_label)

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
                    minconn=1, maxconn=5, dsn=_database_url())
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
    """Borrow a connection from the pool, reconnecting if it has gone stale."""
    for attempt in (1, 2):
        try:
            p = _get_pool()
            raw = p.getconn()
            if raw.closed:
                p.putconn(raw, close=True)
                raise psycopg2.OperationalError("stale pooled connection")
            return _PooledConnection(p, raw)
        except Exception as e:
            if attempt == 2:
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
            session_mode TEXT DEFAULT 'latest_mix',
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
    conn.commit()

    # Users must exist before anything references them, and the legacy
    # vocab table must be split BEFORE the new-shape vocab_progress is
    # declared — otherwise CREATE TABLE IF NOT EXISTS silently no-ops on the
    # old table and every later index fails.
    _seed_users(conn)
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
        CREATE TABLE IF NOT EXISTS hokkien_deck (
            id SERIAL PRIMARY KEY,
            mandarin TEXT NOT NULL,
            mandarin_full TEXT,
            english TEXT,
            hokkien_hanji TEXT NOT NULL,
            tailo TEXT NOT NULL,
            taiji TEXT,
            tier TEXT DEFAULT 'single',
            sources TEXT,
            alternatives INTEGER DEFAULT 1,
            status TEXT DEFAULT 'unverified',
            note TEXT,
            next_review_date TEXT,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            learn_rank INTEGER DEFAULT 9999,
            UNIQUE (mandarin, hokkien_hanji)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_hokkien_status
        ON hokkien_deck (status, next_review_date)
    ''')
    cursor.execute("ALTER TABLE hokkien_deck "
                   "ADD COLUMN IF NOT EXISTS learn_rank INTEGER DEFAULT 9999")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hokkien_rank "
                   "ON hokkien_deck (status, learn_rank)")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentence_blocklist (
            chinese TEXT PRIMARY KEY,
            reason TEXT,
            flagged_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Per-user Hokkien SRS (the deck itself stays shared — verifications and
    # Tâi-lô corrections are curation work, not personal progress).
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hokkien_audio (
            cache_key TEXT PRIMARY KEY,
            entry_id INTEGER REFERENCES hokkien_deck(id) ON DELETE CASCADE,
            audio BYTEA NOT NULL,
            mime TEXT DEFAULT 'audio/wav',
            provider TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hokkien_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entry_id INTEGER NOT NULL REFERENCES hokkien_deck(id) ON DELETE CASCADE,
            next_review_date TEXT,
            interval INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            review_count INTEGER DEFAULT 0,
            UNIQUE (user_id, entry_id)
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
#   latest_mix      — newest words + random breadth. The original
#                     behaviour, and the one that IGNORES due dates: SRS
#                     grades are stored but never decide what you see.
#   srs_latest      — due reviews first, then newest additions. Real spaced
#                     repetition, keeping the "show me what I just added"
#                     bias.
#   random_balanced — due reviews first, then unseen words sampled evenly
#                     across difficulty bands. Best for a new learner.
DEFAULT_USERS = [
    ("matt", "玛德宇", "latest_mix"),
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
    return (row[0] if row and row[0] else "latest_mix")


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
    """Phase 2: attach existing handwriting and Hokkien progress to the
    first user, once all tables exist."""
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

    # hokkien: move any existing SRS state onto the first user
    try:
        cursor.execute("""
            INSERT INTO hokkien_progress
                (user_id, entry_id, next_review_date, interval,
                 ease_factor, review_count)
            SELECT %s, id, next_review_date, interval, ease_factor, review_count
            FROM hokkien_deck WHERE review_count > 0
            ON CONFLICT (user_id, entry_id) DO NOTHING
        """, (owner_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"[MIGRATE] Hokkien migration issue: {e}")

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


def _csv_fingerprint():
    """Cheap identity for the vocabulary CSV (size + mtime + row count)."""
    try:
        st_ = os.stat(VOCAB_CSV_PATH)
        return f"{st_.st_size}:{int(st_.st_mtime)}"
    except OSError:
        return ""


def import_vocab_from_csv(force=False):
    """Import the CSV into the SHARED vocabulary table.

    PERFORMANCE: this used to run one SELECT per row - about 1,400 network
    round-trips to Supabase on every single app boot, which dominated
    start-up time. Now it does two queries total (read existing keys, bulk
    insert the rest), and skips the work altogether when the CSV hasn't
    changed since the last import.
    """
    if not VOCAB_CSV_PATH.exists():
        logging.warning("CSV file not found. Skipping import.")
        return

    fingerprint = _csv_fingerprint()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS app_meta (
                        key TEXT PRIMARY KEY, value TEXT)""")
    conn.commit()
    if not force and fingerprint:
        cursor.execute("SELECT value FROM app_meta WHERE key = 'vocab_csv'")
        row = cursor.fetchone()
        if row and row[0] == fingerprint:
            conn.close()
            logging.info("Vocabulary CSV unchanged - import skipped.")
            return

    df = pd.read_csv(VOCAB_CSV_PATH)
    df['Chinese'] = df['Chinese'].astype(str).str.strip()
    df['Pinyin'] = df['Pinyin'].astype(str).str.strip()
    df = df.replace('', pd.NA).replace('nan', pd.NA).dropna(subset=['Chinese', 'Pinyin'])
    df['English'] = df['English'].fillna('').astype(str).str.strip()

    # 1 query: everything already stored
    cursor.execute("SELECT chinese, pinyin FROM vocab")
    existing = {(c, p) for c, p in cursor.fetchall()}

    today_str = date.today().isoformat()
    fresh = []
    seen = set()
    for _i, row in df.iterrows():
        key = (row['Chinese'], row['Pinyin'])
        if key in existing or key in seen:
            continue
        seen.add(key)
        fresh.append((row['Chinese'], row['Pinyin'], row['English'], today_str))

    # 1 query: bulk insert
    if fresh:
        psycopg2.extras.execute_values(
            cursor,
            "INSERT INTO vocab (chinese, pinyin, english, date_added) VALUES %s "
            "ON CONFLICT (chinese, pinyin) DO NOTHING",
            fresh, page_size=500)

    if fingerprint:
        cursor.execute("""INSERT INTO app_meta (key, value) VALUES ('vocab_csv', %s)
                          ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                       (fingerprint,))
    conn.commit()
    conn.close()
    logging.info(f"Vocabulary import: {len(fresh)} new, "
                 f"{len(df) - len(fresh)} already present.")


def _ensure_progress(cursor, user_id, vocab_id):
    """Create this user's progress row for a word if they've not met it yet."""
    cursor.execute("""
        INSERT INTO vocab_progress (user_id, vocab_id, next_review_date)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, vocab_id) DO NOTHING
    """, (user_id, vocab_id, date.today().isoformat()))


def flag_word_in_database(chinese_char, user_id):
    """Bump a word's priority for THIS user only."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM vocab WHERE chinese = %s", (chinese_char,))
    for (vid,) in cursor.fetchall():
        _ensure_progress(cursor, user_id, vid)
        cursor.execute("""UPDATE vocab_progress
                          SET priority_weight = priority_weight + 10
                          WHERE user_id = %s AND vocab_id = %s""", (user_id, vid))
    conn.commit()
    conn.close()


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
    """Every vocabulary row this user has not yet seen, with any pooled
    ease data from other learners."""
    sql = _VOCAB_SELECT + """
        LEFT JOIN (SELECT vocab_id, MIN(ease_factor) AS pooled_ease
                   FROM vocab_progress GROUP BY vocab_id) agg
               ON agg.vocab_id = v.id
        WHERE (p.review_count IS NULL OR p.review_count = 0)
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
    """Build today's batch according to this user's session mode.

    latest_mix      — newest words plus random breadth (original behaviour).
    random_balanced — anything genuinely due comes first (real spaced
                      repetition), then unseen words drawn at random but
                      spread evenly across difficulty bands.
    """
    import random as _random
    rng = _random.Random()
    mode = mode or get_session_mode(user_id)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if mode in ("random_balanced", "srs_latest"):
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
            if mode == "srs_latest":
                # newest additions first — what you just put in the CSV
                sql = _VOCAB_SELECT + \
                    " WHERE (p.review_count IS NULL OR p.review_count = 0)"
                params = [user_id]
                if exclude:
                    ph = ",".join(["%s"] * len(exclude))
                    sql += f" AND v.id NOT IN ({ph})"
                    params += exclude
                sql += " ORDER BY v.id DESC LIMIT %s"
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

    # ---- latest_mix (unchanged) ----
    random_count = int(round(total * random_pct))
    latest_count = total - random_count
    cursor.execute(_VOCAB_SELECT + " ORDER BY v.id DESC LIMIT %s",
                   (user_id, latest_count))
    latest_rows = [dict(r) for r in cursor.fetchall()]
    latest_ids = [r['id'] for r in latest_rows]

    if latest_ids:
        ph = ','.join(['%s'] * len(latest_ids))
        cursor.execute(_VOCAB_SELECT + f" WHERE v.id NOT IN ({ph}) "
                       "ORDER BY RANDOM() LIMIT %s",
                       [user_id] + latest_ids + [random_count])
    else:
        cursor.execute(_VOCAB_SELECT + " ORDER BY RANDOM() LIMIT %s",
                       (user_id, random_count))
    random_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    session = latest_rows + random_rows
    rng.shuffle(session)
    return session


def get_due_words(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_str = date.today().isoformat()
    cursor.execute(_VOCAB_SELECT + """
        WHERE p.review_count > 0 AND p.next_review_date <= %s
        ORDER BY p.priority_weight DESC, p.next_review_date ASC
    """, (user_id, today_str))
    due_reviews = [dict(r) for r in cursor.fetchall()]
    needed = MAX_REVIEWS_PER_DAY - len(due_reviews)
    if needed > 0:
        cursor.execute(_VOCAB_SELECT + """
            WHERE p.review_count IS NULL OR p.review_count = 0
            ORDER BY COALESCE(p.priority_weight, 1) DESC, v.id DESC LIMIT %s
        """, (user_id, needed))
        new_words = [dict(r) for r in cursor.fetchall()]
    else:
        new_words = []
    conn.close()
    return (due_reviews + new_words)[:MAX_REVIEWS_PER_DAY]


def update_word_progress(user_id, word_id, next_review_date, new_interval, new_ease):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vocab_progress
            (user_id, vocab_id, next_review_date, interval, ease_factor,
             review_count, priority_weight)
        VALUES (%s, %s, %s, %s, %s, 1, 1)
        ON CONFLICT (user_id, vocab_id) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = vocab_progress.review_count + 1,
            priority_weight = GREATEST(1, vocab_progress.priority_weight - 2)
    """, (user_id, word_id, next_review_date, new_interval, new_ease))
    conn.commit()
    conn.close()


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


def undo_word_progress(user_id, word_id, old_next_review_date, old_interval,
                       old_ease, old_review_count, old_priority):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vocab_progress
            (user_id, vocab_id, next_review_date, interval, ease_factor,
             review_count, priority_weight)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, vocab_id) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = EXCLUDED.review_count,
            priority_weight = EXCLUDED.priority_weight
    """, (user_id, word_id, old_next_review_date, old_interval, old_ease,
          old_review_count, old_priority))
    conn.commit()
    conn.close()


def get_more_words(user_id, exclude_ids, amount=5):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if exclude_ids:
        ph = ','.join(['%s'] * len(exclude_ids))
        cursor.execute(_VOCAB_SELECT + f" WHERE v.id NOT IN ({ph}) "
                       "ORDER BY RANDOM() LIMIT %s",
                       [user_id] + list(exclude_ids) + [amount])
    else:
        cursor.execute(_VOCAB_SELECT + " ORDER BY RANDOM() LIMIT %s",
                       (user_id, amount))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


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
                        ON p.vocab_id = v.id AND p.user_id = %s""", (user_id,))
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
                        ON p.vocab_id = v.id AND p.user_id = %s""", (user_id,))
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
# PENANG HOKKIEN DECK
# Built offline from licensed dictionaries (see build_hokkien_deck.py).
# Entries stay 'unverified' — and undrillable — until the learner confirms
# them, because no open Penang Hokkien lexicon exists to trust blindly.
# ==========================================
def hokkien_add(mandarin, mandarin_full, english, hokkien_hanji, tailo,
                taiji, tier, sources, alternatives, learn_rank=9999):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hokkien_deck
            (mandarin, mandarin_full, english, hokkien_hanji, tailo, taiji,
             tier, sources, alternatives, next_review_date, learn_rank)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (mandarin, hokkien_hanji) DO NOTHING
    """, (mandarin, mandarin_full, english, hokkien_hanji, tailo, taiji,
          tier, sources, alternatives, date.today().isoformat(), learn_rank))
    added = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return added


@_cached(ttl=20)
def hokkien_stats(user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE status = 'verified'),
               COUNT(*) FILTER (WHERE status = 'unverified'),
               COUNT(*) FILTER (WHERE status = 'rejected'),
               COUNT(*) FILTER (WHERE tier = 'penang'),
               COUNT(*) FILTER (WHERE tier = 'consensus')
        FROM hokkien_deck
    """)
    t, v, u, r, p, c = cursor.fetchone()
    studied = 0
    if user_id is not None:
        cursor.execute("SELECT COUNT(*) FROM hokkien_progress "
                       "WHERE user_id = %s AND review_count > 0", (user_id,))
        studied = cursor.fetchone()[0] or 0
    conn.close()
    return {"total": t or 0, "verified": v or 0, "unverified": u or 0,
            "rejected": r or 0, "penang": p or 0, "consensus": c or 0,
            "studied": studied}


def hokkien_queue(limit=25, tier=None):
    """Unverified entries for the verification queue, best-evidence first."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if tier:
        cursor.execute("""SELECT * FROM hokkien_deck
                          WHERE status = 'unverified' AND tier = %s
                          ORDER BY learn_rank ASC, alternatives ASC, id
                          LIMIT %s""", (tier, limit))
    else:
        cursor.execute("""SELECT * FROM hokkien_deck
                          WHERE status = 'unverified'
                          ORDER BY learn_rank ASC, alternatives ASC, id
                          LIMIT %s""", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def hokkien_set_status(entry_id, status, tailo=None, taiji=None, note=None):
    """Verify / reject an entry, optionally correcting its romanisation."""
    conn = get_connection()
    cursor = conn.cursor()
    fields, params = ["status = %s"], [status]
    if tailo is not None:
        fields.append("tailo = %s"); params.append(tailo)
    if taiji is not None:
        fields.append("taiji = %s"); params.append(taiji)
    if note is not None:
        fields.append("note = %s"); params.append(note)
    params.append(entry_id)
    cursor.execute(f"UPDATE hokkien_deck SET {', '.join(fields)} WHERE id = %s",
                   params)
    conn.commit()
    conn.close()


def hokkien_session(user_id, limit=20):
    """Verified entries due for THIS user, easiest/most useful first.

    The deck and its verifications are shared; only the SRS state in
    hokkien_progress is personal, so a card verified by one person is
    immediately available to the other as unseen.
    """
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT d.*,
               COALESCE(hp.interval, 0)      AS interval,
               COALESCE(hp.ease_factor, 2.5) AS ease_factor,
               COALESCE(hp.review_count, 0)  AS review_count,
               hp.next_review_date           AS next_review_date
        FROM hokkien_deck d
        LEFT JOIN hokkien_progress hp
               ON hp.entry_id = d.id AND hp.user_id = %s
        WHERE d.status = 'verified'
          AND (hp.next_review_date IS NULL OR hp.next_review_date <= %s)
        ORDER BY COALESCE(hp.review_count, 0) ASC, d.learn_rank ASC,
                 hp.next_review_date NULLS FIRST
        LIMIT %s
    """, (user_id, today, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def hokkien_grade(user_id, entry_id, grade, current_state):
    """Apply an SRS grade for one user (same engine as handwriting)."""
    new_interval, new_ease, next_review = compute_next_review(
        current_interval=current_state.get("interval", 0) or 0,
        current_ease=float(current_state.get("ease_factor", 2.5) or 2.5),
        grade=grade)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hokkien_progress
            (user_id, entry_id, interval, ease_factor, next_review_date,
             review_count)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (user_id, entry_id) DO UPDATE SET
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            next_review_date = EXCLUDED.next_review_date,
            review_count = hokkien_progress.review_count + 1
    """, (user_id, entry_id, new_interval, new_ease, next_review))
    conn.commit()
    conn.close()
    log_activity(user_id, "hokkien", str(entry_id), grade)
    return new_interval


def hokkien_search(term, limit=30):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    like = f"%{term}%"
    cursor.execute("""
        SELECT * FROM hokkien_deck
        WHERE mandarin ILIKE %s OR english ILIKE %s
           OR hokkien_hanji ILIKE %s OR tailo ILIKE %s
        ORDER BY status DESC, id LIMIT %s
    """, (like, like, like, like, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows



# ==========================================
# HOKKIEN AUDIO CACHE
# Clips live in the database, not on disk: Streamlit Cloud wipes the
# filesystem on reboot, and these come from small volunteer-run TTS
# services we shouldn't hammer. Synthesised once, then reused forever.
# ==========================================
def hokkien_audio_get(cache_key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT audio, mime FROM hokkien_audio WHERE cache_key = %s",
                   (cache_key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None, None
    return bytes(row[0]), row[1]


def hokkien_audio_put(cache_key, entry_id, audio, mime, provider):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hokkien_audio (cache_key, entry_id, audio, mime, provider)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (cache_key) DO NOTHING
    """, (cache_key, entry_id, psycopg2.Binary(audio), mime, provider))
    conn.commit()
    conn.close()


def hokkien_audio_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(audio)), 0) "
                   "FROM hokkien_audio")
    n, total = cursor.fetchone()
    conn.close()
    return {"clips": n or 0, "bytes": int(total or 0)}



# ==========================================
# ACTIVITY LOG + FRIENDLY RIVALRY
#
# Deliberately compares EFFORT (cards done, streaks, consistency) rather
# than lifetime totals. One of you started months earlier, so a raw
# leaderboard would be permanently discouraging for the other and would
# stop being motivating for either.
# ==========================================
ACTIVITY_KINDS = {"listen": "Listening", "speak": "Speaking",
                  "write": "Handwriting", "hokkien": "Hokkien"}


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
