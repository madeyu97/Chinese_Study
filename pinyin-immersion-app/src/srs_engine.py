# src/srs_engine.py

from datetime import date, timedelta
import logging

# Import configurations and database functions (Respecting dependencies)
from config import EASY_MULTIPLIER, GOOD_MULTIPLIER, HARD_MULTIPLIER
from db_manager import update_word_progress, get_due_words

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Define the grading scale you will use when answering a question
GRADE_AGAIN = 0  # You completely forgot it
GRADE_HARD = 1   # You remembered, but it took serious effort
GRADE_GOOD = 2   # You remembered it normally
GRADE_EASY = 3   # It was instantaneous

def process_review(word_id, current_interval, current_ease, grade):
    """
    Calculates the new interval and ease factor based on the user's grade,
    then updates the database.
    """
    
    # 1. Calculate the new ease factor
    # Ease factor dictates how quickly the intervals grow over time.
    # We adjust it slightly based on performance, keeping a minimum floor of 1.3
    if grade == GRADE_AGAIN:
        new_ease = max(1.3, current_ease - 0.20)
    elif grade == GRADE_HARD:
        new_ease = max(1.3, current_ease - 0.15)
    elif grade == GRADE_EASY:
        new_ease = current_ease + 0.15
    else: # GRADE_GOOD
        new_ease = current_ease # Ease stays the same if performance is standard

    # 2. Calculate the new interval (in days)
    if grade == GRADE_AGAIN:
        # If you forget it, reset the interval to 0 (review tomorrow or later today)
        new_interval = 0
    else:
        if current_interval == 0:
            # First time graduating from a new/forgotten word
            new_interval = 1 
        elif current_interval == 1:
            # Second successful review, jump to a few days based on ease
            new_interval = 3 
        else:
            # Apply the specific multiplier based on how hard it was
            if grade == GRADE_HARD:
                new_interval = int(current_interval * HARD_MULTIPLIER)
            elif grade == GRADE_GOOD:
                new_interval = int(current_interval * current_ease) # Use dynamic ease for 'Good'
            elif grade == GRADE_EASY:
                new_interval = int(current_interval * current_ease * EASY_MULTIPLIER)
                
    # Ensure intervals don't grow completely out of control (max 1 year)
    new_interval = min(new_interval, 365)

    # 3. Calculate the next review date
    next_review_date = (date.today() + timedelta(days=new_interval)).isoformat()

    # 4. Save to database
    update_word_progress(word_id, next_review_date, new_interval, round(new_ease, 2))
    
    logging.info(f"Word {word_id} graded {grade}. New interval: {new_interval} days. Next review: {next_review_date}.")

    return next_review_date

def get_todays_quiz_batch():
    """
    Helper function to pull the due words from the database.
    The frontend (Streamlit) will call this to get the words it needs to test.
    """
    due_words = get_due_words()
    if not due_words:
        logging.info("No words due for review today! Great job.")
    else:
        logging.info(f"Loaded {len(due_words)} words for today's session.")
    
    return due_words