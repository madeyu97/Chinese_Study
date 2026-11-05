# src/config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 1. DIRECTORY & FILE PATHS
# ==========================================
SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent

DATA_DIR = BASE_DIR / "data"
# The study word list: the 5,000 most common Malay words from film and TV
# subtitles, cleaned, folded and glossed (see data/WORDLIST_SOURCE.md).
WORDLIST_CSV_PATH = DATA_DIR / "malay_words.csv"
# Your own lesson words (clinic Malay first). Rows here are marked
# from_lessons and make up VOCAB_LESSON_SHARE of new words.
LESSONS_CSV_PATH = DATA_DIR / "lessons.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 2. ENVIRONMENT VARIABLES (API KEYS)
# ==========================================
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ==========================================
# 3. AI MODELS
# ==========================================
# The writer and the reviewer are different model families on purpose: an
# error must fool two independent models to reach the learner. Both are
# weaker in Malay than in Chinese and drift towards Indonesian, which is
# why the Indonesian check is mechanical (malay/normalise.py) rather than
# left to the reviewer. Phase 1 picks the reviewer by planting known errors
# and keeping the model that catches the most.
GENERATION_MODEL = "openai/gpt-oss-120b"
GRADING_MODEL = "openai/gpt-oss-120b"
REVIEW_MODEL = "qwen/qwen3.8-27b"
WHISPER_MODEL = "whisper-large-v3"
WHISPER_LANGUAGE = "ms"


# ==========================================
# 4. SRS MULTIPLIERS
# ==========================================
EASY_MULTIPLIER = 2.5
GOOD_MULTIPLIER = 1.5
HARD_MULTIPLIER = 1.2


# ==========================================
# GRAMMAR DRILLS (Phase 4)
# ==========================================
# A word counts as "well studied" for grammar drills once it has been
# reviewed this many times and isn't currently failed (interval >= 1).
GRAMMAR_KNOWN_MIN_REVIEWS = 3
GRAMMAR_KNOWN_MIN_INTERVAL = 1
# Below this many well-studied words, anything reviewed at least once counts.
GRAMMAR_KNOWN_FLOOR = 60
# Cap on words passed to the drill writer (best-known first).
GRAMMAR_VOCAB_CAP = 700
# New grammar structures introduced per day.
GRAMMAR_NEW_PER_DAY = 2
# A stored drill set is replaced once your well-studied vocabulary has
# grown by this fraction since it was written.
GRAMMAR_REFRESH_GROWTH = 0.25


# ==========================================
# VOCABULARY LEARNING ENGINE
# ==========================================
# New words introduced per session / per day (the second is a hard ceiling).
VOCAB_NEW_PER_SESSION = 5
VOCAB_NEW_PER_DAY = 10
# Once this many reviews are due, new words shrink; at twice this, none.
VOCAB_BACKLOG_SOFT = 40
# Reviews per session (recognition and production together).
VOCAB_SESSION_REVIEWS = 25
# Words whose production practice may start in one session.
VOCAB_UNLOCKS_PER_SESSION = 4
# Share of new words drawn from your lesson list (the rest follow frequency).
VOCAB_LESSON_SHARE = 0.4


# ==========================================
# DAILY LIMITS ON NEW MATERIAL (every page)
# ==========================================
# New affix families per day (Phase 5).
AFFIX_NEW_PER_DAY = 3


# ==========================================
# TODAY'S PLAN
# ==========================================
# Full day: every step at its usual size. Short day: a few of the most
# urgent reviews, then a little listening - it still counts as a day.
PLAN_SHORT_REVIEWS = 10
PLAN_GRAMMAR_STRUCTURES = 2
PLAN_SENTENCES_LISTEN = 3
PLAN_SENTENCES_SPEAK = 3
