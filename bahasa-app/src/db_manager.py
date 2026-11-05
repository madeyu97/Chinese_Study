# src/db_manager.py
"""
Everything the app keeps in Postgres (Supabase in production).

Vocabulary and the sentence bank are SHARED by everyone on this database;
progress (word schedules, attempts, grammar, sessions, games) is private to
each learner.

Ported from the Chinese app's db_manager with the character machinery
(handwriting, herbs, character reading, legacy migrations) left out and the
word table reshaped for Malay: one row per spelling, with its root, affixes,
register and an Indonesian tag where it applies.
"""

import hashlib
import json
import logging
import re
import threading
from datetime import date

import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2 import pool
import streamlit as st

from config import LESSONS_CSV_PATH, WORDLIST_CSV_PATH

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

_POOL = None
_POOL_LOCK = threading.Lock()


def _database_url():
    import os
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
    if _schema() != "public" and re.search(r":6543(/|$)", db_url.split("?")[0]):
        # Supabase's transaction pooler hands each transaction to any server
        # connection, so the schema setting below would not stick and this
        # app could write into another app's tables.
        raise ValueError("Use Supabase's Session pooler connection string (port 5432), "
                         "not the Transaction pooler (port 6543).")
    return db_url


def _schema():
    """The Postgres schema this app keeps its tables in. 'bahasa' unless the
    DB_SCHEMA secret says otherwise, so the app can share a database (and its
    DATABASE_URL) with the Chinese app, whose tables have the same names and
    live in 'public'."""
    import os
    name = None
    try:
        if hasattr(st, "secrets") and "DB_SCHEMA" in st.secrets:
            name = st.secrets["DB_SCHEMA"]
    except Exception:
        pass
    name = (name or os.environ.get("DB_SCHEMA") or "bahasa").strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"DB_SCHEMA must be a plain lowercase name, not {name!r}")
    return name


_READY = {}          # id(raw connection) -> connection, once pointed at the schema


def _prepare(raw):
    """Point a new connection at this app's schema: unqualified table names
    then resolve there and nowhere else (the schema is created first, so a
    missing schema can never fall through to 'public')."""
    if _READY.get(id(raw)) is raw:
        return
    schema = _schema()
    cur = raw.cursor()
    try:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        raw.commit()
    except psycopg2.Error:
        raw.rollback()                   # another deployment created it at the same moment
    cur.execute(f'SET search_path TO "{schema}"')
    raw.commit()
    _READY[id(raw)] = raw


class _PooledConnection:
    """Looks like a psycopg2 connection, but close() returns it to the pool.

    Every data function here opens a connection and closes it, and Streamlit
    re-runs the whole script on every interaction, so pooling keeps the
    connections open and reuses them instead of a fresh TLS handshake to
    Supabase on every click."""

    def __init__(self, pool_, conn):
        self._pool = pool_
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
                    minconn=1, maxconn=8, dsn=_database_url())
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
        _READY.clear()


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
            try:
                _prepare(raw)
            except Exception:
                p.putconn(raw, close=True)
                raise
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
# both boot at once they would otherwise race on schema creation, so
# init_db runs under a Postgres advisory lock.
_INIT_LOCK_KEY = 728451917


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
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Vocabulary CONTENT is shared by everyone studying on this deployment.
    # One row per spelling. root/affixes come from the word list (checked by
    # hand) or the morphology analyser; register is colloquial / standard /
    # formal; tag is 'Indonesian' (recognise only, my_equivalent names the
    # Malaysian word) or 'Utara' (northern Malay, recognise only).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id SERIAL PRIMARY KEY,
            malay TEXT NOT NULL UNIQUE,
            english TEXT NOT NULL,
            root TEXT,
            affixes TEXT,
            pos TEXT,
            register TEXT,
            tag TEXT,
            my_equivalent TEXT,
            e_note TEXT,
            lesson_list TEXT,
            freq_rank INTEGER,
            from_lessons BOOLEAN DEFAULT FALSE,
            needs_check TEXT,
            edited BOOLEAN DEFAULT FALSE,
            date_added TEXT NOT NULL
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocab_freq ON vocab (freq_rank)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocab_root ON vocab (root)")
    # Grammar drills: per-learner spaced repetition for each structure, and
    # the drill sets written for them (kept so a set can be reused, then
    # replaced as the learner's vocabulary grows).
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
    # Affix drills (Phase 5): a spaced schedule per family or drill key.
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
            first_seen TEXT,
            PRIMARY KEY (user_id, drill, key)
        )
    ''')
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
    # A session in progress on any page, one per learner and page, so it
    # survives a dropped connection. See session_store.py.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_sessions (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            day DATE NOT NULL,
            state JSONB NOT NULL,
            elapsed REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_id, name)
        )
    ''')
    # Graded reading (Phase 6): shared passages, who has read which, and
    # words sent from a passage to be learned next.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reading_bank (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL UNIQUE,
            payload JSONB NOT NULL,
            known_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reading_progress (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reading_id INTEGER NOT NULL REFERENCES reading_bank(id) ON DELETE CASCADE,
            first_read TEXT,
            last_read TEXT,
            times INTEGER DEFAULT 0,
            score REAL,
            PRIMARY KEY (user_id, reading_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_requests (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            requested_on TEXT,
            PRIMARY KEY (user_id, vocab_id)
        )
    ''')
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
    # Vetted sentences, reused instead of regenerated; a flagged sentence is
    # retired everywhere and can't come back.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentence_bank (
            id SERIAL PRIMARY KEY,
            vocab_word TEXT NOT NULL,
            sentence TEXT NOT NULL UNIQUE,
            exercise JSONB NOT NULL,
            status TEXT DEFAULT 'active',
            times_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_vocab "
                   "ON sentence_bank (vocab_word, status)")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentence_blocklist (
            sentence TEXT PRIMARY KEY,
            reason TEXT,
            flagged_at TIMESTAMP DEFAULT NOW()
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_day "
                   "ON activity_log (user_id, day)")
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
    cursor.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    _seed_users(conn)
    try:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (_INIT_LOCK_KEY,))
        conn.commit()
    except Exception:
        pass
    conn.close()
    logging.info("Database initialised.")


# ==========================================
# SHORT-LIVED READ CACHE
# Streamlit re-runs the entire script on every interaction. These are
# read-only summaries where a few seconds of staleness is invisible, and any
# write clears them immediately.
# ==========================================
def _in_streamlit():
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        return False


def _cached(ttl=20):
    """Cache only when actually running inside Streamlit, so offline scripts
    and tests get the plain function."""
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
DEFAULT_USERS = [
    ("matt", "Matt"),
    ("selina", "Selina"),
]


def _seed_users(conn):
    cursor = conn.cursor()
    for username, display in DEFAULT_USERS:
        cursor.execute("INSERT INTO users (username, display_name) VALUES (%s, %s) "
                       "ON CONFLICT (username) DO NOTHING", (username, display))
    conn.commit()


def _pin_hash(pin):
    return hashlib.sha256(f"bahasa-study::{pin}".encode("utf-8")).hexdigest()


def list_users():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT id, username, display_name, "
                   "(pin_hash IS NOT NULL) AS has_pin FROM users ORDER BY id")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


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
    cursor.execute("SELECT id, username, display_name FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ==========================================
# VOCABULARY IMPORT
# ==========================================
# Columns the app reads from the word list and the lesson list. Only malay
# and english are required; the rest are filled by the analyser when blank.
# needs_check: 'unsure' marks a gloss that wants a native speaker's eye;
# 'audit' marks a word drawn into the gloss audit (Settings); 'ok' marks a
# word someone has checked, so a re-import doesn't queue it again.
_FIELDS = ("english", "root", "affixes", "pos", "register", "tag", "my_equivalent",
           "e_note", "needs_check")
_TAGS = ("Indonesian", "Utara")
_REGISTERS = ("colloquial", "standard", "formal")


def _csv_fingerprint():
    """Content hash of the vocabulary source files, so the import only runs
    when one of them changes (size + mtime change on every cloud reboot)."""
    h = hashlib.sha256()
    for path in (WORDLIST_CSV_PATH, LESSONS_CSV_PATH):
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:32]


def _cell(row, key):
    v = row.get(key, "")
    v = "" if v is None or v != v else str(v).strip()
    return v


def _clean_row(row):
    """A CSV row -> the vocab fields, normalised. None if unusable."""
    malay = _cell(row, "malay").lower()
    english = _cell(row, "english")
    if not malay or not english or not re.fullmatch(r"[a-z]+(?:[- ][a-z]+)*", malay):
        return None
    out = {"malay": malay, "english": english}
    for k in _FIELDS[1:]:
        out[k] = _cell(row, k) or None
    if out["tag"] not in _TAGS:
        out["tag"] = None
    if out["register"] not in _REGISTERS:
        out["register"] = None
    # the files' 'check' column: anything in it sends the word to the review queue
    out["needs_check"] = "unsure" if (_cell(row, "check") or out.get("needs_check")) else None
    if out["root"]:
        out["root"] = out["root"].lower()
    return out


def _read_csv(path):
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.to_dict("records")


def _analyse_missing(rec):
    """Fill root/affixes for a row that came without them (lesson rows typed
    by hand), using the morphology analyser."""
    if rec.get("root") or " " in rec["malay"] or rec.get("tag") == "Utara":
        return rec                    # northern forms aren't standard derivations
    try:
        from malay import morphology
        a = morphology.analyse(rec["malay"])
        if a.root != rec["malay"] or a.affix_label:      # a root word stores no root
            rec["root"] = a.root
            rec["affixes"] = a.affix_label or None
    except Exception as e:
        logging.warning(f"[IMPORT] analyser unavailable for {rec['malay']}: {e}")
    return rec


_IMPORT_LOCK_KEY = 7_730_523


def import_vocab_from_csv(force=False):
    """Serialised wrapper: if two copies of the app boot together the second
    waits, then finds the work done."""
    lock_conn = get_connection()
    lock_cur = lock_conn.cursor()
    lock_cur.execute("SELECT pg_advisory_lock(%s)", (_IMPORT_LOCK_KEY,))
    try:
        _import_vocab(force)
    finally:
        lock_cur.execute("SELECT pg_advisory_unlock(%s)", (_IMPORT_LOCK_KEY,))
        lock_conn.close()


def _import_vocab(force=False):
    """Merge the frequency word list and your lesson list into the SHARED
    vocab table.

    - Every word-list row gets its rank; its gloss and analysis refresh from
      the file unless the word is one of your lesson words.
    - Lesson rows always win: their meaning is used and they are marked
      from_lessons. A lesson word not on the frequency list is added.
    - A word that drops off both lists keeps its row (and anyone's progress)
      but loses its rank, so it is never introduced as new.
    Runs only when a source file's content changes."""
    if not WORDLIST_CSV_PATH.exists() and not LESSONS_CSV_PATH.exists():
        logging.warning("No vocabulary files found. Skipping import.")
        return
    fingerprint = _csv_fingerprint()
    conn = get_connection()
    cursor = conn.cursor()
    if not force:
        cursor.execute("SELECT value FROM app_meta WHERE key = 'vocab_csv'")
        row = cursor.fetchone()
        if row and row[0] == fingerprint:
            conn.close()
            logging.info("Vocabulary files unchanged - import skipped.")
            return

    ranked = {}
    for i, row in enumerate(_read_csv(WORDLIST_CSV_PATH), 1):
        rec = _clean_row(row)
        if not rec or rec["malay"] in ranked:
            continue
        rank = _cell(row, "rank")
        rec["freq_rank"] = int(rank) if rank.isdigit() else i
        ranked[rec["malay"]] = rec
    lessons = {}
    for row in _read_csv(LESSONS_CSV_PATH):
        rec = _clean_row(row)
        if not rec or rec["malay"] in lessons:
            continue
        rec["lesson_list"] = _cell(row, "list") or "lessons"
        lessons[rec["malay"]] = _analyse_missing(rec)

    cursor.execute("SELECT id, malay, from_lessons FROM vocab")
    stored = {m: (vid, bool(fl)) for vid, m, fl in cursor.fetchall()}
    today_str = date.today().isoformat()
    cols = ("malay", "english", "root", "affixes", "pos", "register", "tag",
            "my_equivalent", "e_note", "needs_check", "lesson_list", "freq_rank",
            "from_lessons")
    rows, ranks = [], []
    for malay in set(ranked) | set(lessons):
        base = ranked.get(malay)
        lesson = lessons.get(malay)
        rec = dict(base or {})
        if lesson:
            # lesson rows win on meaning; analysis fills from the list if absent
            for k, v in lesson.items():
                if v or k not in rec:
                    rec[k] = v
        rec.setdefault("freq_rank", None)
        rec["register"] = rec.get("register") or "standard"
        rec["from_lessons"] = bool(lesson)
        rec.setdefault("lesson_list", None)
        rows.append(tuple(rec.get(k) for k in cols) + (today_str,))
        ranks.append((malay, rec["freq_rank"], rec["from_lessons"], rec["lesson_list"]))
    if rows:
        # A word you have edited in Settings keeps your edit: the files only
        # refresh rows nobody has touched by hand.
        psycopg2.extras.execute_values(cursor, f"""
            INSERT INTO vocab ({", ".join(cols)}, date_added)
            VALUES %s
            ON CONFLICT (malay) DO UPDATE SET
                english = EXCLUDED.english, root = EXCLUDED.root,
                affixes = EXCLUDED.affixes, pos = EXCLUDED.pos,
                register = EXCLUDED.register, tag = EXCLUDED.tag,
                my_equivalent = EXCLUDED.my_equivalent, e_note = EXCLUDED.e_note,
                needs_check = CASE WHEN vocab.english IS DISTINCT FROM EXCLUDED.english
                                     OR vocab.needs_check IS NULL
                                   THEN EXCLUDED.needs_check ELSE vocab.needs_check END
            WHERE NOT vocab.edited""",
            rows, page_size=1000)
        psycopg2.extras.execute_values(cursor, """
            UPDATE vocab SET freq_rank = u.freq_rank, from_lessons = u.from_lessons,
                             lesson_list = u.lesson_list
            FROM (VALUES %s) AS u(malay, freq_rank, from_lessons, lesson_list)
            WHERE vocab.malay = u.malay""",
            ranks, template="(%s, %s::integer, %s::boolean, %s::text)", page_size=1000)
    gone = [vid for m, (vid, _fl) in stored.items() if m not in ranked and m not in lessons]
    if gone:
        cursor.execute("UPDATE vocab SET freq_rank = NULL, from_lessons = FALSE "
                       "WHERE id = ANY(%s)", (gone,))
    cursor.execute("""INSERT INTO app_meta (key, value) VALUES ('vocab_csv', %s)
                      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                   (fingerprint,))
    conn.commit()
    conn.close()
    clear_caches()
    logging.info(f"Vocabulary import: {len(rows)} rows upserted, {len(gone)} unranked.")


# ==========================================
# VOCABULARY: lookups and the editor in Settings
# ==========================================
_WORD_COLS = """v.id, v.malay, v.english, v.root, v.affixes, v.pos, v.register,
                v.tag, v.my_equivalent, v.freq_rank, v.from_lessons"""
_SINGLE_WORD = r"^[a-z]+(-[a-z]+)*$"


@_cached(ttl=60)
def vocab_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*), COUNT(*) FILTER (WHERE from_lessons),
                             COUNT(*) FILTER (WHERE tag = 'Indonesian'),
                             COUNT(*) FILTER (WHERE register = 'colloquial'),
                             COUNT(*) FILTER (WHERE freq_rank IS NOT NULL)
                      FROM vocab""")
    total, lessons, indo, colloquial, ranked = cursor.fetchone()
    conn.close()
    return {"total": total, "lessons": lessons, "indonesian": indo,
            "colloquial": colloquial, "ranked": ranked}


def find_words(query, limit=20):
    """Vocabulary entries matching the Malay, its root or the English."""
    q = (query or "").strip().lower()
    if not q:
        return []
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""SELECT {_WORD_COLS}, v.lesson_list FROM vocab v
                       WHERE v.malay = %s OR v.malay LIKE %s OR v.root = %s
                          OR v.english ILIKE %s
                       ORDER BY (v.malay = %s) DESC, v.freq_rank NULLS LAST, v.id
                       LIMIT %s""",
                   (q, f"%{q}%", q, f"%{q}%", q, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def update_word_in_db(word_id, **fields):
    """Edit a shared word by hand. Only known columns are written; the row is
    marked edited (the word-list file never overwrites it again) and leaves
    the review queue. An audited word whose gloss you changed counts as an
    audit error."""
    allowed = {"malay", "english", "root", "affixes", "pos", "register", "tag",
               "my_equivalent", "e_note"}
    fields = {k: (v.strip() if isinstance(v, str) else v) or None
              for k, v in fields.items() if k in allowed}
    if not fields:
        return
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM vocab WHERE id = %s", (word_id,))
    before = cursor.fetchone()
    if not before:
        conn.close()
        return
    changed = {k: v for k, v in fields.items() if before[k] != v}
    if before["needs_check"] == "audit":
        _audit_count(cursor, "audit_fixed" if changed else "audit_ok")
    sets = ", ".join(f"{k} = %s" for k in changed)
    cursor.execute(f"UPDATE vocab SET {sets + ', ' if sets else ''}edited = %s, "
                   f"needs_check = 'ok' WHERE id = %s",
                   (*changed.values(), bool(changed) or before["edited"], word_id))
    conn.commit()
    conn.close()
    clear_caches()


def mark_word_checked(word_id):
    """The gloss is right as it stands: out of the review queue (an audited
    word counts as correct)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT needs_check FROM vocab WHERE id = %s", (word_id,))
    row = cursor.fetchone()
    if row and row[0] == "audit":
        _audit_count(cursor, "audit_ok")
    cursor.execute("UPDATE vocab SET needs_check = 'ok' WHERE id = %s", (word_id,))
    conn.commit()
    conn.close()
    clear_caches()


def _audit_count(cursor, key):
    cursor.execute("""INSERT INTO app_meta (key, value) VALUES (%s, '1')
                      ON CONFLICT (key) DO UPDATE SET
                          value = (app_meta.value::integer + 1)::text""", (key,))


def review_queue(limit=30):
    """Words waiting for a check, most frequent first: audit draws, then
    glosses marked unsure."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""SELECT {_WORD_COLS}, v.needs_check FROM vocab v
                       WHERE v.needs_check IN ('audit', 'unsure')
                       ORDER BY (v.needs_check = 'audit') DESC, v.freq_rank NULLS LAST
                       LIMIT %s""", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT needs_check, COUNT(*) FROM vocab "
                   "WHERE needs_check IN ('audit', 'unsure') GROUP BY needs_check")
    counts = dict(cursor.fetchall())
    conn.close()
    return rows, counts


def draw_audit(n=200):
    """Put n random, never-edited words from the list into the review queue
    as an audit sample; returns how many were drawn."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""UPDATE vocab SET needs_check = 'audit' WHERE id IN (
                          SELECT id FROM vocab WHERE freq_rank IS NOT NULL AND NOT edited
                            AND needs_check IS NULL ORDER BY RANDOM() LIMIT %s)""", (n,))
    drawn = cursor.rowcount
    conn.commit()
    conn.close()
    clear_caches()
    return drawn


def audit_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM app_meta WHERE key IN ('audit_ok', 'audit_fixed')")
    got = {k: int(v) for k, v in cursor.fetchall()}
    conn.close()
    ok, fixed = got.get("audit_ok", 0), got.get("audit_fixed", 0)
    return {"ok": ok, "fixed": fixed, "done": ok + fixed,
            "accuracy": round(100 * ok / (ok + fixed)) if ok + fixed else None}


def delete_word_from_db(word_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vocab WHERE id = %s", (word_id,))
    conn.commit()
    conn.close()
    clear_caches()


def word_by_malay(malay):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"SELECT {_WORD_COLS} FROM vocab v WHERE v.malay = %s", ((malay or "").lower(),))
    r = cursor.fetchone()
    conn.close()
    return dict(r) if r else None


def glosses_for(words):
    """malay -> english for these words and their roots (word-by-word
    breakdowns under sentences come from here, never from the model)."""
    from malay import morphology
    words = {w.lower() for w in words if w}
    roots = set()
    for w in words:
        a = morphology.analyse(w)
        roots |= {a.root, morphology.attach(a.root, a.prefixes, a.suffix)}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT malay, english FROM vocab WHERE malay = ANY(%s)",
                   (list(words | roots),))
    out = dict(cursor.fetchall())
    conn.close()
    return out


def vocab_ids_for(words):
    """malay -> vocab id, for the words that are in the vocabulary."""
    if not words:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT malay, id FROM vocab WHERE malay = ANY(%s)", (list(words),))
    out = dict(cursor.fetchall())
    conn.close()
    return out


# ==========================================
# SENTENCE BANK
# ==========================================
def bank_add(vocab_word, exercise):
    ex = {k: v for k, v in exercise.items() if k != "audio_path"}
    sentence = ex.get("malay", "")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sentence_blocklist WHERE sentence = %s", (sentence,))
    if cursor.fetchone():
        conn.close()
        return False
    cursor.execute(
        """INSERT INTO sentence_bank (vocab_word, sentence, exercise)
           VALUES (%s, %s, %s) ON CONFLICT (sentence) DO NOTHING""",
        (vocab_word, sentence, psycopg2.extras.Json(ex)))
    added = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return added


def bank_get(vocab_word):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(
        """SELECT id, exercise FROM sentence_bank
           WHERE vocab_word = %s AND status = 'active'
             AND sentence NOT IN (SELECT sentence FROM sentence_blocklist)
           ORDER BY times_used ASC, RANDOM() LIMIT 1""",
        (vocab_word,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    cursor.execute("UPDATE sentence_bank SET times_used = times_used + 1 WHERE id = %s",
                   (row["id"],))
    conn.commit()
    conn.close()
    exercise = row["exercise"]
    if isinstance(exercise, str):
        exercise = json.loads(exercise)
    return exercise


def flag_sentence(sentence, reason="flagged by learner"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sentence_bank SET status = 'flagged' WHERE sentence = %s", (sentence,))
    cursor.execute("""INSERT INTO sentence_blocklist (sentence, reason) VALUES (%s, %s)
                      ON CONFLICT (sentence) DO NOTHING""", (sentence, reason))
    conn.commit()
    conn.close()
    logging.info(f"[FLAG] Retired sentence: {sentence}")


def unflag_sentence(sentence):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sentence_blocklist WHERE sentence = %s", (sentence,))
    cursor.execute("UPDATE sentence_bank SET status = 'active' WHERE sentence = %s", (sentence,))
    conn.commit()
    conn.close()


def get_blocklist():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sentence FROM sentence_blocklist")
    rows = {r[0] for r in cursor.fetchall()}
    conn.close()
    return rows


def get_recent_flags(limit=8):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sentence, COALESCE(reason, '') FROM sentence_blocklist "
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
               COUNT(DISTINCT vocab_word) FILTER (WHERE status = 'active')
        FROM sentence_bank""")
    active, flagged, covered = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM vocab")
    total_vocab = cursor.fetchone()[0]
    conn.close()
    return {"active_sentences": active or 0, "flagged": flagged or 0,
            "vocab_covered": covered or 0, "vocab_total": total_vocab or 0}


def bank_count_for(vocab_word):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sentence_bank WHERE vocab_word = %s AND status = 'active'",
                   (vocab_word,))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def bank_browse(vocab_word=None, status='active', limit=50):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if vocab_word:
        cursor.execute("""SELECT vocab_word, sentence, exercise, status, times_used
                          FROM sentence_bank WHERE vocab_word = %s AND status = %s
                          ORDER BY created_at DESC LIMIT %s""", (vocab_word, status, limit))
    else:
        cursor.execute("""SELECT vocab_word, sentence, exercise, status, times_used
                          FROM sentence_bank WHERE status = %s
                          ORDER BY created_at DESC LIMIT %s""", (status, limit))
    rows = []
    for r in cursor.fetchall():
        ex = r["exercise"]
        if isinstance(ex, str):
            ex = json.loads(ex)
        rows.append({"vocab_word": r["vocab_word"], "sentence": r["sentence"],
                     "exercise": ex, "status": r["status"], "times_used": r["times_used"]})
    conn.close()
    return rows


# ==========================================
# ACTIVITY LOG, TIME LEDGER, NUDGES
# ==========================================
# One row per answered card, by the skill it used.
ACTIVITY_KINDS = {"read": "Reading", "listen": "Listening", "speak": "Speaking",
                  "type": "Typing", "grammar": "Grammar", "affixes": "Affixes",
                  "games": "Games"}

# Time ledger: which strand of study each page's minutes belong to.
ACTIVITY_STRAND = {"words": "study", "grammar": "study", "affixes": "study",
                   "sentences": "use", "reading": "use", "clinic": "use", "penang": "use",
                   "games": "play"}
STRANDS = {"study": "Words, grammar & affixes",
           "use": "Listening, reading & speaking",
           "play": "Games"}
MAX_SESSION_SECONDS = 45 * 60      # a tab left open doesn't count as study


def log_activity(user_id, kind, item=None, grade=None, mistakes=0):
    """Record one graded card. Never raises: a logging failure must not
    interrupt someone's study session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO activity_log (user_id, kind, item, grade, mistakes)
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
    cursor.execute("SELECT COUNT(*) FROM activity_log WHERE user_id = %s AND day = CURRENT_DATE",
                   (user_id,))
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
    cursor.execute("SELECT DISTINCT day FROM activity_log WHERE user_id = %s "
                   "ORDER BY day DESC LIMIT 400", (user_id,))
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
        cursor.execute("""INSERT INTO study_sessions (user_id, day, activity, seconds, items, in_plan)
                          VALUES (%s, %s, %s, %s, %s, %s)""",
                       (user_id, date.today(), activity, seconds, int(items or 0), bool(in_plan)))
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
                      WHERE user_id = %s AND day = %s AND in_plan""", (user_id, date.today()))
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
                      WHERE user_id = %s AND day >= %s GROUP BY activity""", (user_id, since))
    by_activity = {a: round((sec or 0) / 60) for a, sec in cursor.fetchall()
                   if a != "plan_complete"}
    cursor.execute("""SELECT COUNT(DISTINCT day) FILTER (WHERE activity = 'plan_complete'),
                             COUNT(DISTINCT day) FILTER (WHERE activity <> 'plan_complete')
                      FROM study_sessions WHERE user_id = %s AND day >= %s""", (user_id, since))
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
    """Combined feed across everyone, for the Together page."""
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


def send_nudge(from_user, to_user, message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO nudges (from_user, to_user, message) VALUES (%s, %s, %s)",
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
    cursor.execute("UPDATE nudges SET seen_at = NOW() WHERE to_user = %s AND seen_at IS NULL",
                   (user_id,))
    conn.commit()
    conn.close()


def other_users(user_id):
    return [u for u in list_users() if u["id"] != user_id]


# ==========================================
# GRAMMAR DRILLS (store)
# ==========================================
def grammar_known_vocab(user_id):
    """The learner's well-studied words, best-known first. Falls back to
    anything reviewed once while the list is still short."""
    from config import (GRAMMAR_KNOWN_MIN_REVIEWS, GRAMMAR_KNOWN_MIN_INTERVAL,
                        GRAMMAR_KNOWN_FLOOR, GRAMMAR_VOCAB_CAP)
    conn = get_connection()
    cursor = conn.cursor()
    query = f"""SELECT v.malay FROM vocab v
                JOIN word_skill s ON s.vocab_id = v.id AND s.user_id = %s
                                 AND s.skill = 'recognition'
                WHERE s.reps >= %s AND COALESCE(s.interval, 0) >= %s
                  AND v.malay ~ '{_SINGLE_WORD}' AND v.tag IS NULL
                ORDER BY s.reps DESC, s.interval DESC LIMIT %s"""
    cursor.execute(query, (user_id, GRAMMAR_KNOWN_MIN_REVIEWS,
                           GRAMMAR_KNOWN_MIN_INTERVAL, GRAMMAR_VOCAB_CAP))
    words = [r[0] for r in cursor.fetchall()]
    if len(words) < GRAMMAR_KNOWN_FLOOR:
        cursor.execute(query, (user_id, 1, 0, GRAMMAR_VOCAB_CAP))
        words = [r[0] for r in cursor.fetchall()]
    conn.close()
    return list(dict.fromkeys(words))


def grammar_indonesian_pairs():
    """(Indonesian form, Malaysian form) pairs from the tagged vocabulary, so
    writers and reviewers know which word to use instead."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT malay, my_equivalent FROM vocab "
                   "WHERE tag = 'Indonesian' AND my_equivalent IS NOT NULL")
    pairs = [(m, eq) for m, eq in cursor.fetchall()]
    conn.close()
    return pairs


def grammar_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM grammar_progress WHERE user_id = %s", (user_id,))
    rows = {r["structure_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()
    return rows


def grammar_save_progress(user_id, structure_id, next_review_date, interval, ease, score):
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
    cursor.execute("SELECT COUNT(*) FROM grammar_progress WHERE user_id = %s AND first_seen = %s",
                   (user_id, date.today().isoformat()))
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
                      FROM grammar_drill_sets WHERE user_id = %s AND structure_id = %s
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


def grammar_recent_sentences(user_id, structure_id, limit=3, sentences_in=None):
    """Sentences from the latest stored sets, fed back so the next set
    differs. sentences_in extracts them from a payload (grammar_drills)."""
    if sentences_in is None:
        try:
            from grammar_drills import sentences_in
        except ImportError:
            return []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT payload FROM grammar_drill_sets WHERE user_id = %s AND structure_id = %s
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
    cursor.execute("""INSERT INTO grammar_drill_sets (user_id, structure_id, known_count, payload)
                      VALUES (%s, %s, %s, %s) RETURNING id""",
                   (user_id, structure_id, known_count, json.dumps(payload, ensure_ascii=False)))
    new_id = cursor.fetchone()[0]
    cursor.execute("""DELETE FROM grammar_drill_sets WHERE user_id = %s AND structure_id = %s
                      AND id NOT IN (SELECT id FROM grammar_drill_sets WHERE user_id = %s
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
                      last_served = %s WHERE id = %s""", (date.today().isoformat(), set_id))
    conn.commit()
    conn.close()


# ==========================================
# VOCABULARY ENGINE (store)
# ==========================================
def _track_row(r):
    return {"interval": r["interval"], "ease": r["ease"],
            "next_review_date": r["next_review_date"], "reps": r["reps"],
            "lapses": r["lapses"], "streak": r["streak"],
            "last_mode": r["last_mode"], "last_result": r["last_result"],
            "introduced_on": r["introduced_on"]}


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
    """Words recognised reliably enough to start producing them. Indonesian
    and northern forms are recognition-only."""
    from vocab_engine import UNLOCK_MIN_INTERVAL, UNLOCK_MIN_STREAK
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""
        SELECT {_WORD_COLS} FROM word_skill r JOIN vocab v ON v.id = r.vocab_id
        WHERE r.user_id = %s AND r.skill = 'recognition'
          AND r.interval >= %s AND r.streak >= %s
          AND v.malay ~ '{_SINGLE_WORD}' AND v.tag IS NULL
          AND NOT EXISTS (SELECT 1 FROM word_skill p WHERE p.user_id = r.user_id
                          AND p.vocab_id = r.vocab_id AND p.skill = 'production')
        ORDER BY v.freq_rank NULLS LAST, v.id
        LIMIT %s
    """, (user_id, UNLOCK_MIN_INTERVAL, UNLOCK_MIN_STREAK, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _partner(word):
    """The Malaysian word an Indonesian form should wait for: the first word
    of my_equivalent ('mahu / nak' -> 'mahu')."""
    eq = (word.get("my_equivalent") or "").strip().lower()
    m = re.match(r"[a-z]+(?:-[a-z]+)*", eq)
    return m.group(0) if m else None


UTARA_AFTER = 300


def new_word_candidates(user_id, limit=40):
    """(lesson words, frequency words) not yet introduced, each in frequency
    order. Indonesian forms wait until their Malaysian partner has been
    introduced (or, if the partner is not on the list, until 300 words are
    known); northern (Utara) forms wait until 300 words are known."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    base = f"""
        SELECT {_WORD_COLS} FROM vocab v
        WHERE NOT EXISTS (SELECT 1 FROM word_skill s WHERE s.user_id = %s
                          AND s.vocab_id = v.id AND s.skill = 'recognition')
    """
    cursor.execute(base + " AND v.from_lessons ORDER BY v.freq_rank NULLS LAST, v.id LIMIT %s",
                   (user_id, limit))
    lessons = [dict(r) for r in cursor.fetchall()]
    cursor.execute(base + " AND NOT v.from_lessons AND v.freq_rank IS NOT NULL "
                   "ORDER BY v.freq_rank LIMIT %s", (user_id, limit))
    frequency = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""SELECT v.malay FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                      WHERE s.user_id = %s AND s.skill = 'recognition'""", (user_id,))
    known = {r[0] for r in cursor.fetchall()}
    partners = {_partner(w) for w in lessons + frequency if w.get("tag") == "Indonesian"}
    partners.discard(None)
    listed = set()
    if partners:
        cursor.execute("SELECT malay FROM vocab WHERE malay = ANY(%s)", (list(partners),))
        listed = {r[0] for r in cursor.fetchall()}
    conn.close()

    def ready(w):
        if w.get("tag") == "Indonesian":
            p = _partner(w)
            if p and p in listed:
                return p in known
            return len(known) >= UTARA_AFTER   # partner not on the list
        if w.get("tag") == "Utara":
            return len(known) >= UTARA_AFTER
        return True
    return [w for w in lessons if ready(w)], [w for w in frequency if ready(w)]


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
    """Store a skill track."""
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
    conn.commit()
    conn.close()
    clear_caches()


def log_word_attempt(user_id, vocab_id, skill, mode, result, detail=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO word_attempts (user_id, vocab_id, skill, mode, result, detail)
                      VALUES (%s, %s, %s, %s, %s, %s)""",
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


def plan_word_session(user_id, rng=None, review_cap=None, new_cap=None, unlocks=True):
    """Everything the session builder needs, gathered in one place.
    review_cap / new_cap tighten the usual limits (the short day uses them);
    they never loosen the daily cap on new words."""
    from config import (VOCAB_NEW_PER_SESSION, VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT,
                        VOCAB_SESSION_REVIEWS, VOCAB_UNLOCKS_PER_SESSION, VOCAB_LESSON_SHARE)
    import vocab_engine as ve
    review_cap = VOCAB_SESSION_REVIEWS if review_cap is None else min(review_cap, VOCAB_SESSION_REVIEWS)
    due = count_due(user_id)
    rec = due_words(user_id, "recognition", review_cap)
    prod = due_words(user_id, "production", review_cap)
    room = ve.new_word_allowance(due, introduced_today(user_id), VOCAB_NEW_PER_SESSION,
                                 VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT)
    if new_cap is not None:
        room = max(0, min(room, new_cap))
    lessons, frequency = new_word_candidates(user_id)
    asked = requested_words(user_id)[:room]          # words sent from reading go first
    taken = {w["id"] for w in asked}
    new = asked + ve.pick_new_words([w for w in lessons if w["id"] not in taken],
                                    [w for w in frequency if w["id"] not in taken],
                                    room - len(asked), VOCAB_LESSON_SHARE)
    # production starts only when the load is light enough for new material
    unlock_cap = VOCAB_UNLOCKS_PER_SESSION if unlocks and due <= VOCAB_BACKLOG_SOFT else 0
    unlock = production_unlockable(user_id, unlock_cap)
    ids = {w["id"] for w in rec + prod + unlock}
    items = ve.build_session(rec, prod, unlock, new, review_cap, unlock_cap,
                             mode_error_rates(user_id), word_tracks(user_id, ids), rng)
    try:
        import word_diagnosis as wd               # arrives with the Words page (Phase 2)
        preferred = wd.PREFERRED_MODE
    except ImportError:
        preferred = {}
    open_d = open_diagnoses(user_id, [it["word"]["id"] for it in items])
    for it in items:
        dg = open_d.get(it["word"]["id"])
        if dg and it["kind"] == "review":
            it["mode"] = preferred.get((dg["cause"], it["skill"]), it["mode"])
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
    cursor.execute(f"""SELECT DISTINCT v.malay, v.english, v.root, v.affixes, v.tag
                       FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                       WHERE s.user_id = %s AND s.skill = 'recognition'
                         AND v.malay ~ '{_SINGLE_WORD}'""", (user_id,))
    pool_ = [dict(r) for r in cursor.fetchall()]
    if len(pool_) < minimum:
        have = {w["malay"] for w in pool_}
        cursor.execute("""SELECT malay, english, root, affixes, tag FROM vocab
                          WHERE freq_rank IS NOT NULL ORDER BY freq_rank LIMIT %s""",
                       (minimum * 2,))
        pool_ += [dict(r) for r in cursor.fetchall() if r["malay"] not in have][:minimum - len(pool_)]
    conn.close()
    return pool_


def word_content_for(user_id, word, allow_generate=True, known=None):
    """The content to learn `word` through, for this learner (Phase 2).

    Reuses the cached set until it has been used WORD_CONTENT_MAX_USES times
    or the learner's vocabulary has grown enough to write richer sentences.
    Without a cached set (or when generation fails or isn't allowed), falls
    back to a vetted sentence-bank sentence, then to the word alone.
    Returns (payload, content_id or None)."""
    import word_content as wc
    # Indonesian and northern forms are recognition-only: they get no
    # written content (a Malaysian sentence can't model them)
    allow_generate = allow_generate and not word.get("tag")
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
        recent = [w for w in recent_words(user_id) if w != word["malay"]]
        payload = wc.generate(word, known, structures, recent)
        if payload:
            if payload.get("reviewed", True):
                return payload, word_content_save(user_id, word["id"], len(known), payload)
            return payload, None
    if cached:
        return cached["payload"], cached["id"]
    sentence = bank_get(word["malay"])
    if not sentence:
        # a human-written Tatoeba sentence beats the word on its own
        try:
            import tatoeba
            found = tatoeba.matches(word, get_blocklist(), limit=1)
            if found:
                sentence = {"malay": found[0]["malay"], "english_correct": found[0]["english"],
                            "source": "tatoeba"}
        except Exception as e:
            logging.warning(f"[CONTENT] Tatoeba lookup failed: {e}")
    return wc.fallback_content(word, sentence), None


# ---- diagnosis ------------------------------------------------------------
def open_diagnoses(user_id, vocab_ids=None):
    """vocab_id -> the word's latest unresolved diagnosis."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    q = """SELECT d.*, v.malay, v.english FROM word_diagnosis d
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


def recent_words(user_id, days=14, limit=30):
    """Words introduced in the last `days` and answered correctly at least
    once - what grammar drills and new word sentences should recycle."""
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""SELECT v.malay FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                       WHERE s.user_id = %s AND s.skill = 'recognition'
                         AND s.introduced_on >= %s
                         AND (s.streak >= 1 OR s.interval >= 1)
                         AND v.malay ~ '{_SINGLE_WORD}' AND v.tag IS NULL
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


def introduced_words(user_id):
    """Every word the learner has been introduced to (recognition track
    exists), with what the drills need."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""SELECT {_WORD_COLS} FROM word_skill s JOIN vocab v ON v.id = s.vocab_id
                       WHERE s.user_id = %s AND s.skill = 'recognition'""", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


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
    """Families or drill keys met for the first time today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM drill_progress WHERE user_id = %s
                      AND drill = %s AND first_seen = %s""",
                   (user_id, drill, date.today().isoformat()))
    n = cursor.fetchone()[0]
    conn.close()
    return n


def family_forms(roots):
    """{root: [every untagged form of it in the word list, the root word
    included]}, most frequent first - wrong options and glosses for the
    affix drills."""
    roots = sorted({r for r in roots if r})
    if not roots:
        return {}
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""SELECT {_WORD_COLS} FROM vocab v
                       WHERE v.tag IS NULL AND v.malay ~ '{_SINGLE_WORD}'
                         AND (v.root = ANY(%s) OR (v.root IS NULL AND v.malay = ANY(%s)))
                       ORDER BY v.freq_rank NULLS LAST, v.id""", (roots, roots))
    out = {}
    for r in cursor.fetchall():
        r = dict(r)
        out.setdefault(r["root"] or r["malay"], []).append(r)
    conn.close()
    return out


def affix_sentences(user_id, words, per_word=3):
    """{form: [{malay, english}]}: sentences already written for these
    words - the learner's own word content first, then the shared bank.
    No generation: the affix gap drill only reuses checked sentences."""
    out = {w["malay"]: [] for w in words}
    ids = [w["id"] for w in words if w.get("id")]
    if not ids:
        return out
    by_id = {w["id"]: w["malay"] for w in words if w.get("id")}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT DISTINCT ON (vocab_id) vocab_id, payload FROM word_content
                      WHERE user_id = %s AND vocab_id = ANY(%s)
                      ORDER BY vocab_id, created_at DESC, id DESC""", (user_id, ids))
    for vid, payload in cursor.fetchall():
        try:
            sents = json.loads(payload).get("sentences") or []
        except Exception:
            sents = []
        out[by_id[vid]] += [{"malay": s["malay"], "english": s.get("english", "")}
                            for s in sents if s.get("malay")]
    cursor.execute("""SELECT vocab_word, exercise FROM sentence_bank
                      WHERE vocab_word = ANY(%s) AND status = 'active'
                        AND sentence NOT IN (SELECT sentence FROM sentence_blocklist)
                      ORDER BY times_used ASC, id""", (list(out),))
    for word, ex in cursor.fetchall():
        ex = ex if isinstance(ex, dict) else json.loads(ex)
        if ex.get("malay"):
            out[word].append({"malay": ex["malay"], "english": ex.get("english_correct", "")})
    conn.close()
    return {k: v[:per_word * 2] for k, v in out.items()}


# ---- reading ----------------------------------------------------------------
def reading_candidates():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, payload FROM reading_bank WHERE status = 'active' ORDER BY id")
    rows = [{"id": i, "payload": p if isinstance(p, dict) else json.loads(p)}
            for i, p in cursor.fetchall()]
    conn.close()
    return rows


def reading_read_ids(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT reading_id FROM reading_progress WHERE user_id = %s", (user_id,))
    ids = {r[0] for r in cursor.fetchall()}
    conn.close()
    return ids


def reading_save(payload, known_count):
    """Store a checked passage for both learners. Returns its id (the
    existing one if the same text is already stored)."""
    from reading_engine import passage_text
    text = passage_text(payload)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO reading_bank (text, payload, known_count) VALUES (%s, %s, %s)
                      ON CONFLICT (text) DO NOTHING RETURNING id""",
                   (text, psycopg2.extras.Json(payload), known_count))
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT id FROM reading_bank WHERE text = %s", (text,))
        row = cursor.fetchone()
    conn.commit()
    conn.close()
    return row[0]


def reading_mark(user_id, reading_id, score=None):
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reading_progress (user_id, reading_id, first_read, last_read, times, score)
        VALUES (%s, %s, %s, %s, 1, %s)
        ON CONFLICT (user_id, reading_id) DO UPDATE SET last_read = EXCLUDED.last_read,
            times = reading_progress.times + 1,
            score = COALESCE(EXCLUDED.score, reading_progress.score)
    """, (user_id, reading_id, today, today, score))
    conn.commit()
    conn.close()


def reading_retire(reading_id):
    """A passage flagged as wrong is never shown again, to either learner."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reading_bank SET status = 'flagged' WHERE id = %s", (reading_id,))
    conn.commit()
    conn.close()


def reading_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), AVG(score) FROM reading_progress WHERE user_id = %s", (user_id,))
    n, avg = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM reading_bank WHERE status = 'active'")
    bank = cursor.fetchone()[0]
    conn.close()
    return {"read": n or 0, "score": avg, "bank": bank}


def request_words(user_id, words):
    """Queue words to be introduced next on the Words page. words:
    [(malay, english)]. A word missing from the list is added to it (marked
    for checking in Settings, since its meaning came from a passage).
    Returns how many were queued."""
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    n = 0
    for malay, english in words:
        malay = (malay or "").strip().lower()
        if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", malay):
            continue
        cursor.execute("SELECT id FROM vocab WHERE malay = %s", (malay,))
        row = cursor.fetchone()
        if not row:
            if not english:
                continue
            rec = _analyse_missing({"malay": malay, "english": english})
            cursor.execute("""INSERT INTO vocab (malay, english, root, affixes, register, lesson_list,
                              needs_check, date_added) VALUES (%s, %s, %s, %s, 'standard', 'reading',
                              'unsure', %s) ON CONFLICT (malay) DO NOTHING RETURNING id""",
                           (malay, english, rec.get("root"), rec.get("affixes"), today))
            row = cursor.fetchone()
            if not row:
                continue
        cursor.execute("""INSERT INTO word_requests (user_id, vocab_id, requested_on) VALUES (%s, %s, %s)
                          ON CONFLICT DO NOTHING""", (user_id, row[0], today))
        n += cursor.rowcount
    conn.commit()
    conn.close()
    clear_caches()
    return n


def requested_words(user_id):
    """Words sent from reading, not yet introduced, oldest request first."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""SELECT {_WORD_COLS} FROM word_requests r JOIN vocab v ON v.id = r.vocab_id
                       WHERE r.user_id = %s AND NOT EXISTS (
                           SELECT 1 FROM word_skill s WHERE s.user_id = r.user_id
                           AND s.vocab_id = v.id AND s.skill = 'recognition')
                       ORDER BY r.requested_on, v.id""", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


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


# ---- sessions in progress ---------------------------------------------------
def saved_session_put(user_id, name, state_json, elapsed=0):
    """Save a session in progress (state_json is a JSON string)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO saved_sessions (user_id, name, day, state, elapsed, updated_at)
                      VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
                      ON CONFLICT (user_id, name) DO UPDATE SET
                          day = EXCLUDED.day, state = EXCLUDED.state,
                          elapsed = EXCLUDED.elapsed, updated_at = NOW()""",
                   (user_id, name, date.today(), state_json, float(elapsed or 0)))
    conn.commit()
    conn.close()


def saved_session_get(user_id, name, same_day=True, max_age_hours=24):
    """{state, elapsed} for a saved session, if it's recent enough: saved
    today when same_day, otherwise within max_age_hours. Never raises."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT state, elapsed, day FROM saved_sessions
                          WHERE user_id = %s AND name = %s
                            AND updated_at > NOW() - (%s || ' hours')::interval""",
                       (user_id, name, str(max_age_hours)))
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        logging.warning(f"[STORE] saved {name} unreadable: {e}")
        return None
    if not row or (same_day and row[2] != date.today()):
        return None
    return {"state": row[0], "elapsed": row[1]}


def saved_session_del(user_id, name):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_sessions WHERE user_id = %s AND name = %s",
                       (user_id, name))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"[STORE] saved {name} not cleared: {e}")


# ---- sentence practice (Listen & speak, Phase 3) ---------------------------
def sentence_practice_words(user_id, limit=40):
    """Words already introduced, for sentence listening and speaking: due
    recognition first, then words introduced in the last fortnight (weakest
    first), then the rest at random. Never a word you haven't met. Each row
    carries both skill tracks."""
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
          AND v.malay ~ '{_SINGLE_WORD}'
        ORDER BY (COALESCE(r.next_review_date, '') <= %s) DESC,
                 (COALESCE(r.introduced_on, '') >= %s) DESC,
                 r.interval ASC, RANDOM()
        LIMIT %s
    """, (user_id, today, fortnight, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


init_db()
import_vocab_from_csv()
