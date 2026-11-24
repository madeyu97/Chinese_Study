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
# The 10,000 most common words (SUBTLEX-CH film/TV subtitle corpus, Cai &
# Brysbaert 2010), ranked by how many films each appears in. The ranks file
# covers ~44,000 words so anything you add to vocab_export.csv gets a rank.
FREQUENCY_CSV_PATH = DATA_DIR / "frequency_words.csv"
FREQUENCY_RANKS_PATH = DATA_DIR / "frequency_ranks.csv"

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
# at Chinese. Alternative worth trying: "qwen/qwen3.8-27b" (preview) — a
# Qwen model with native-level Chinese.
GENERATION_MODEL = "openai/gpt-oss-120b"
GRADING_MODEL = "openai/gpt-oss-120b"
# Reviewer is a DIFFERENT model family from the generator on purpose:
# Qwen has native-level Chinese and won't share gpt-oss's blind spots, so
# an error must fool two independent models to reach the learner.
REVIEW_MODEL = "qwen/qwen3.8-27b"
WHISPER_MODEL = "whisper-large-v3"

# Groq's per-model allowance (tokens a minute) on this account, and where a
# call goes when its model's allowance is used up - each model has its own,
# so a full one needn't mean waiting. See ai_budget.py.
AI_TOKENS_PER_MINUTE = {"*": 8000}
AI_FALLBACKS = {
    "openai/gpt-oss-120b": ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
    "qwen/qwen3.8-27b": ["openai/gpt-oss-20b", "openai/gpt-oss-120b"],
    "openai/gpt-oss-20b": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
}
# known words listed in an AI prompt (all of them still count as known when
# the result is checked): the full list was 1,600 tokens of every call
PROMPT_KNOWN_WORDS = 300

# ==========================================
# 6b. HANDWRITING PRECISION RAMP
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


# ==========================================
# GRAMMAR DRILLS
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
# New characters written per day, across all handwriting sources; none while
# more than HANDWRITING_BACKLOG characters are due.
HANDWRITING_NEW_PER_DAY = 5
HANDWRITING_BACKLOG = 30
# New tone groups / character families per day, per drill.
SOUND_NEW_PER_DAY = 3


# ==========================================
# TODAY'S PLAN: TWO SESSIONS A DAY
# ==========================================
# About 25 minutes each, morning and evening (see today_plan.py). The
# evening opens at its hour (local time, see clock.py) and no sooner than
# SESSION_GAP_HOURS after the morning finished - the gap is what makes a
# word met in the morning a real retrieval in the evening. You can always
# start one early; the Today page just says when it's best.
SESSION_OPENS = {"morning": 4, "evening": 17}
SESSION_GAP_HOURS = 4
SESSION_MINUTES = 25
PLAN_HANDWRITING_REVIEWS = 15
PLAN_GRAMMAR_STRUCTURES = 1      # one structure a morning (new, or a review when one is due)
PLAN_SENTENCES_LISTEN = 4
PLAN_SENTENCES_SPEAK = 4
PLAN_RECAP_WORDS = 15            # evening: today's new and missed words, once more
PLAN_READING_SENTENCES = 4


# ======================================================================
# HSK TRACK
# ======================================================================
# People on the HSK 1-4 app: Today · Write · Grammar · Read · Play.
# Anyone else (Selina's deployment) keeps the original app, unchanged.
HSK_TRACK_USERS = {"matt"}

# Grammar on the HSK track: the morning is about HSK_GRAMMAR_MINUTES of
# grammar - reviews first (short), then new structures in what's left. One
# structure a day, reviews first, would add only ~50 of HSK 1-4's 344 in a
# year; this pace does them all in about nine months (see hsk_grammar.py).
HSK_GRAMMAR_MINUTES = 25
HSK_GRAMMAR_NEW_MAX = 2          # full new lessons a day
HSK_GRAMMAR_CHECKS_MAX = 6       # quick checks of structures below your grammar level
HSK_GRAMMAR_CORE_CAP = 45        # longest gap (days) for a core structure
