# src/db_manager.py

import os
import hashlib
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

# Two Streamlit deployments can share this database (one per person, each
# with its own API key and resource allocation). If both boot at once they
# would otherwise race on schema creation and the one-time migration, so
# the whole of init_db runs under a Postgres advisory lock.
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
            last_reviewed TEXT
        )
    ''')
    # Backfill struggle-tracking columns on databases created before this
    # feature (CREATE TABLE IF NOT EXISTS never alters an existing table).
    for _coldef in ("user_id INTEGER",
                    "total_mistakes INTEGER DEFAULT 0",
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


def import_vocab_from_csv():
    """Import the CSV into the SHARED vocabulary table. Progress is per-user
    and is created lazily the first time someone studies a word."""
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
    skipped = 0
    today_str = date.today().isoformat()

    for _index, row in df.iterrows():
        cursor.execute('SELECT id FROM vocab WHERE chinese = %s AND pinyin = %s',
                       (row['Chinese'], row['Pinyin']))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO vocab (chinese, pinyin, english, date_added)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (chinese, pinyin) DO NOTHING
            """, (row['Chinese'], row['Pinyin'], row['English'], today_str))
            new_words_added += 1
        else:
            skipped += 1
    conn.commit()
    conn.close()
    if new_words_added:
        logging.info(f"Imported {new_words_added} new words.")
    if skipped:
        logging.info(f"Skipped {skipped} duplicates.")


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


def get_handwriting_counts(user_id):
    """(due_reviews, new_available) for the session setup screen."""
    session = get_handwriting_session(user_id, new_count=10**6)
    due = sum(1 for e in session if not e["is_new"])
    new = sum(1 for e in session if e["is_new"])
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
             recent_mistakes, last_reviewed)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, character) DO UPDATE SET
            next_review_date = EXCLUDED.next_review_date,
            interval = EXCLUDED.interval,
            ease_factor = EXCLUDED.ease_factor,
            review_count = handwriting_progress.review_count + 1,
            total_mistakes = handwriting_progress.total_mistakes + EXCLUDED.total_mistakes,
            recent_grades = EXCLUDED.recent_grades,
            recent_mistakes = EXCLUDED.recent_mistakes,
            last_reviewed = EXCLUDED.last_reviewed
    ''', (character, user_id, next_review_date, new_interval, new_ease,
           today_str, mistakes, new_grades, new_mist, today_str))
    conn.commit()
    conn.close()
    logging.info(f"[HW] {character} graded {grade} ({mistakes} mistakes) "
                 f"→ next review in {new_interval}d"
                 + (" [REQUEUED this session]" if requeue else ""))
    return requeue


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


init_db()
import_vocab_from_csv()
