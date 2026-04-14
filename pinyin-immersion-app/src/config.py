# src/config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 1. DIRECTORY & FILE PATHS
# ==========================================
# Path(__file__).resolve() gets the absolute path of THIS exact script.
# .parent goes up one level to the 'src' directory.
# .parent again goes up to the root project directory.
SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent

# Define where our data lives
DATA_DIR = BASE_DIR / "data"
VOCAB_CSV_PATH = DATA_DIR / "vocab_export.csv"
DB_PATH = DATA_DIR / "user_progress.db"

# Automatically create the 'data' folder if it doesn't exist yet
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 2. ENVIRONMENT VARIABLES (API KEYS)
# ==========================================
# Look for the .env file in the root directory and load it
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Fetch the keys. 
# We use os.getenv() so the app doesn't immediately crash if a key is missing,
# allowing us to handle the missing key gracefully later.
LLM_API_KEY = os.getenv("LLM_API_KEY")
TTS_API_KEY = os.getenv("TTS_API_KEY")


# ==========================================
# 3. APP SETTINGS & SRS CONFIGURATION
# ==========================================
# We can store our Spaced Repetition (SRS) constants here so they are 
# easy to tweak later without digging through complex logic scripts.

MAX_REVIEWS_PER_DAY = 20  # How many Pinyin phrases to test per session
NEW_WORDS_PER_DAY = 5     # How many brand new words to introduce

# Simplified SRS Multipliers
# If you get a word right, the interval until you see it again multiplies by this number.
EASY_MULTIPLIER = 2.5
GOOD_MULTIPLIER = 1.5
HARD_MULTIPLIER = 1.2