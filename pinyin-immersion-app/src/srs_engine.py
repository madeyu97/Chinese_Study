# src/srs_engine.py

from datetime import date, timedelta
import logging

from config import EASY_MULTIPLIER, GOOD_MULTIPLIER, HARD_MULTIPLIER
from db_manager import update_word_progress, get_session_words

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

GRADE_AGAIN = 0
GRADE_HARD = 1
GRADE_GOOD = 2
GRADE_EASY = 3

def process_review(word_id, current_interval, current_ease, grade):
    """
    Per-word SRS state is still maintained, even though the session-selection
    layer no longer uses next_review_date. This way, if you decide to flip back
    to a strict SRS schedule later, the data is intact.
    """
    if grade == GRADE_AGAIN:
        new_ease = max(1.3, current_ease - 0.20)
    elif grade == GRADE_HARD:
        new_ease = max(1.3, current_ease - 0.15)
    elif grade == GRADE_EASY:
        new_ease = current_ease + 0.15
    else:
        new_ease = current_ease

    if grade == GRADE_AGAIN:
        new_interval = 0
    else:
        if current_interval == 0:
            new_interval = 1
        elif current_interval == 1:
            new_interval = 3
        else:
            if grade == GRADE_HARD:
                new_interval = int(current_interval * HARD_MULTIPLIER)
            elif grade == GRADE_GOOD:
                new_interval = int(current_interval * current_ease)
            elif grade == GRADE_EASY:
                new_interval = int(current_interval * current_ease * EASY_MULTIPLIER)

    new_interval = min(new_interval, 365)
    next_review_date = (date.today() + timedelta(days=new_interval)).isoformat()
    update_word_progress(word_id, next_review_date, new_interval, round(new_ease, 2))
    logging.info(f"Word {word_id} graded {grade}. New interval: {new_interval} days.")
    return next_review_date

def get_todays_quiz_batch():
    """
    Now uses the 50/50 random+latest composition instead of strict SRS due.
    See db_manager.get_session_words() for the rationale.
    """
    batch = get_session_words()
    if not batch:
        logging.info("No words available — is your CSV imported?")
    else:
        logging.info(f"Loaded {len(batch)} words for today's session.")
    return batch
