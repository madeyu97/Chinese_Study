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
LISTENING_PCT = 0.60
RECALL_PCT = 0.40


# ==========================================
# 6. AI MODELS
# ==========================================
GENERATION_MODEL = "llama-3.3-70b-versatile"
GRADING_MODEL = "llama-3.3-70b-versatile"
WHISPER_MODEL = "whisper-large-v3"


# ==========================================
# 7. SRS MULTIPLIERS
# ==========================================
EASY_MULTIPLIER = 2.5
GOOD_MULTIPLIER = 1.5
HARD_MULTIPLIER = 1.2
