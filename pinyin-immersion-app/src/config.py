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
VOCAB_CSV_PATH = DATA_DIR / "vocab_export.csv"
DB_PATH = DATA_DIR / "user_progress.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 2. ENVIRONMENT VARIABLES (API KEYS)
# ==========================================
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

LLM_API_KEY = os.getenv("LLM_API_KEY")
TTS_API_KEY = os.getenv("TTS_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ==========================================
# 3. SESSION SIZE
# ==========================================
MAX_REVIEWS_PER_DAY = 20  # Total cards in a session
NEW_WORDS_PER_DAY = 5     # Legacy — kept for backward compat


# ==========================================
# 4. SESSION COMPOSITION (new)
# ==========================================
# How the daily batch is built. Must sum to 1.0.
#   RANDOM_BREADTH_PCT: random sample across your whole CSV for coverage
#   LATEST_PCT:         most recently added entries (bottom-up by id DESC)
RANDOM_BREADTH_PCT = 0.50
LATEST_PCT = 0.50


# ==========================================
# 5. MODE MIX (new)
# ==========================================
# Within a session, what proportion is each exercise type. Must sum to 1.0.
#   LISTENING_PCT: hear audio → type pinyin → MCQ English (existing flow)
#   RECALL_PCT:    see English + target → speak Chinese → graded by Whisper+LLM
LISTENING_PCT = 0.50
RECALL_PCT = 0.50


# ==========================================
# 6. AI MODELS
# ==========================================
# llama-3.3-70b-versatile is deprecated on Groq and was the source of
# ungrammatical Chinese (e.g. 把-sentences with no verb). gpt-oss-120b is
# Groq's current recommended production replacement and is markedly stronger
# at Chinese. Alternative worth trying: "qwen/qwen3.6-27b" (preview) — a
# Qwen model with native-level Chinese.
GENERATION_MODEL = "openai/gpt-oss-120b"
GRADING_MODEL = "openai/gpt-oss-120b"
# Reviewer is a DIFFERENT model family from the generator on purpose:
# Qwen has native-level Chinese and won't share gpt-oss's blind spots, so
# an error must fool two independent models to reach the learner.
REVIEW_MODEL = "qwen/qwen3.6-27b"
WHISPER_MODEL = "whisper-large-v3"

# ==========================================
# 6b. HOKKIEN AUDIO
# ==========================================
# Which TTS service to try first for Hokkien. Run
#   python src/test_hokkien_audio.py
# to see which respond from your network, listen to the samples it writes,
# and set the best one here. "" = try all in order.
# These voices are TAIWANESE Hokkien: a pronunciation reference, not the
# Penang accent. Audio is cached in the database after first use.
HOKKIEN_TTS_PROVIDER = ""

# ==========================================
# 6c. HANDWRITING PRECISION RAMP
# ==========================================
# Each error-free write of a character tightens how closely your strokes
# must match, so a character you know well demands better placement than
# one you've just met.
#
# These are HanziWriter "leniency" values: HIGHER is more forgiving, 1.0 is
# the library default. Tune to taste - if the drill starts feeling unfair
# raise PRECISION_FLOOR; if it stays too easy, lower it.
PRECISION_START = 1.25   # a brand-new character: generous
PRECISION_STEP  = 0.04   # tightened by this much per clean write
PRECISION_FLOOR = 0.75   # never stricter than this, however well you know it
# Mistakes ease the requirement back off, so a bad day doesn't leave a
# character permanently unwritable.
PRECISION_RELAPSE = 2    # clean-writes forfeited when you fail a character


# ==========================================
# 7. SRS MULTIPLIERS
# ==========================================
EASY_MULTIPLIER = 2.5
GOOD_MULTIPLIER = 1.5
HARD_MULTIPLIER = 1.2
