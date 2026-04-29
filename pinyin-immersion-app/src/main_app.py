# src/main_app.py

import streamlit as st
import os
import random
import json
from datetime import date


# Import our custom modules
from srs_engine import get_todays_quiz_batch, process_review
from ai_prompter import generate_dictation_exercise
from audio_engine import create_audio_file
from db_manager import flag_word_in_database, get_progress_stats, undo_word_progress, get_more_words

# ==========================================
# 1. CACHE MANAGEMENT
# ==========================================
CACHE_FILE = "session_cache.json"

def load_cached_session():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("date") == str(date.today()):
                return cache
        except Exception:
            pass
    return None

def save_cached_session():
    cache = {
        "date": str(date.today()),
        "words_due": st.session_state.words_due,
        "current_index": st.session_state.current_index,
        "current_exercise": st.session_state.current_exercise,
        "audio_path": st.session_state.audio_path,
        "stage": st.session_state.stage,
        "shuffled_options": st.session_state.shuffled_options,
        "user_pinyin": st.session_state.user_pinyin,
        "mcq_correct": st.session_state.mcq_correct,
        "exercise_history": st.session_state.exercise_history, # NEW: Save history
        "audio_history": st.session_state.audio_history        # NEW: Save history
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)

# ==========================================
# 2. APP CONFIGURATION & STATE MANAGEMENT
# ==========================================
st.set_page_config(page_title="Pinyin Immersion", page_icon="🎧", layout="centered")

# --- NEW: THE MIDNIGHT RESET ---
# If the tab was left open overnight, wipe the memory so it grabs a fresh daily batch
if 'session_date' in st.session_state and st.session_state.session_date != str(date.today()):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
# Initialize Session State variables
if 'words_due' not in st.session_state:
    cached_state = load_cached_session()
    
    if cached_state:
        # Restore everything from the cache
        for key, value in cached_state.items():
            if key != "date":
                st.session_state[key] = value
        st.session_state.session_date = str(date.today())
    else:
        # Start a fresh session
        st.session_state.words_due = get_todays_quiz_batch()
        st.session_state.current_index = 0
        st.session_state.current_exercise = None
        st.session_state.audio_path = None
        st.session_state.stage = 1
        st.session_state.shuffled_options = []
        st.session_state.user_pinyin = ""
        st.session_state.mcq_correct = None
        st.session_state.exercise_history = {} 
        st.session_state.audio_history = {}    
        st.session_state.session_date = str(date.today()) # Stamp today's date!
        save_cached_session()
# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def grade_word_and_next(grade):
    current_word = st.session_state.words_due[st.session_state.current_index]
    
    process_review(
        word_id=current_word['id'],
        current_interval=current_word['interval'],
        current_ease=current_word['ease_factor'],
        grade=grade
    )
    
    st.session_state.current_index += 1
    st.session_state.current_exercise = None
    st.session_state.audio_path = None
    st.session_state.stage = 1
    st.session_state.shuffled_options = []
    st.session_state.user_pinyin = ""
    st.session_state.mcq_correct = None
    save_cached_session()

def undo_last_grade():
    """Restores the database and UI to the previous word."""
    if st.session_state.current_index > 0:
        prev_index = st.session_state.current_index - 1
        original_word = st.session_state.words_due[prev_index]
        
        # 1. Fix the Database
        undo_word_progress(
            word_id=original_word['id'],
            old_next_review_date=original_word['next_review_date'],
            old_interval=original_word['interval'],
            old_ease=original_word['ease_factor'],
            old_review_count=original_word['review_count'],
            old_priority=original_word.get('priority_weight', 1)
        )
        
        # 2. Fix the UI state (jump straight to the grading stage)
        st.session_state.current_index = prev_index
        
        # JSON converts int keys to strings, so we cast to string to retrieve safely
        idx_str = str(prev_index) 
        st.session_state.current_exercise = st.session_state.exercise_history.get(idx_str)
        st.session_state.audio_path = st.session_state.audio_history.get(idx_str)
        
        st.session_state.stage = 3 # Put them right back at the 4 buttons
        save_cached_session()

def advance_to_stage_2():
    st.session_state.stage = 2
    save_cached_session()

def advance_to_stage_3():
    st.session_state.stage = 3
    save_cached_session()

# ==========================================
# 4. THE MAIN USER INTERFACE
# ==========================================
# ==========================================
# 4. THE MAIN USER INTERFACE
# ==========================================
st.title("🎧 Pinyin Immersion Study")

if st.session_state.current_index >= len(st.session_state.words_due):
    st.success("🎉 You're all caught up for today! Great job.")
    st.balloons()
    
    # --- NEW: The "Do 5 More" Overtime Button ---
    if st.button("➕ Do 5 More Words", type="primary", use_container_width=True):
        with st.spinner("Fetching more words..."):
            # Gather the IDs of everything we've already studied today
            exclude_ids = [word['id'] for word in st.session_state.words_due]
            
            # Ask the database for 5 more
            extra_words = get_more_words(exclude_ids, amount=5)
            
            if extra_words:
                st.session_state.words_due.extend(extra_words)
                save_cached_session()
                st.rerun() # Instantly restart the UI loop!
            else:
                st.warning("You've completely exhausted your database! Add more words to your CSV.")
    
    st.stop()

current_word = st.session_state.words_due[st.session_state.current_index]

# --- NEW: Progress Bar with Undo Button Layout ---
total_words = len(st.session_state.words_due)
col1, col2 = st.columns([4, 1])

with col1:
    st.progress((st.session_state.current_index) / total_words)
    st.caption(f"Reviewing word {st.session_state.current_index + 1} of {total_words}")

with col2:
    if st.session_state.current_index > 0:
        if st.button("↩️ Undo", use_container_width=True):
            undo_last_grade()
            st.rerun()

st.markdown("---")

# ==========================================
# 4.5 THE PROGRESS SIDEBAR
# ==========================================
with st.sidebar:
    st.header("📊 Global Progress")
    stats = get_progress_stats()
    
    if stats['total'] > 0:
        unseen_pct = int((stats['unseen'] / stats['total']) * 100)
        learning_pct = int((stats['learning'] / stats['total']) * 100)
        mastered_pct = int((stats['mastered'] / stats['total']) * 100)
        
        st.metric("Total CSV Vocabulary", stats['total'])
        st.markdown("---")
        
        st.write(f"**👀 Unseen:** {stats['unseen']} words ({unseen_pct}%)")
        st.progress(stats['unseen'] / stats['total'])
        
        st.write(f"**🧠 Learning:** {stats['learning']} words ({learning_pct}%)")
        st.progress(stats['learning'] / stats['total'])
        
        st.write(f"**🏆 Mastered:** {stats['mastered']} words ({mastered_pct}%)")
        st.progress(stats['mastered'] / stats['total'])
        
        st.markdown("---")
        st.caption("Mastered = successfully pushed 21+ days into the future.")
    else:
        st.write("No vocabulary found. Please check your CSV.")

# ==========================================
# 5. GENERATING THE EXERCISE
# ==========================================
if st.session_state.current_exercise is None:
    with st.spinner("Generating localized audio scenario..."):
        exercise_data = generate_dictation_exercise(current_word)
        
        if exercise_data:
            st.session_state.current_exercise = exercise_data
            st.session_state.audio_path = create_audio_file(exercise_data['chinese'])
            
            # --- NEW: Save to history dictionaries ---
            idx_str = str(st.session_state.current_index)
            st.session_state.exercise_history[idx_str] = exercise_data
            st.session_state.audio_history[idx_str] = st.session_state.audio_path
            
            options = exercise_data['english_distractors'] + [exercise_data['english_correct']]
            random.shuffle(options)
            st.session_state.shuffled_options = options
            
            save_cached_session()
        else:
            st.error("Failed to generate exercise. Check your API connection.")
            st.stop()

# ==========================================
# 6. STAGE 1: PINYIN DICTATION
# ==========================================
st.subheader("Listen & Transcribe:")

if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
    st.audio(st.session_state.audio_path, format="audio/mp3")
else:
    st.warning("⚠️ The audio engine failed to generate the voice file.")
    if st.button("🔄 Retry Audio", type="primary"):
        with st.spinner("Retrying audio..."):
            st.session_state.audio_path = create_audio_file(st.session_state.current_exercise['chinese'])
            st.session_state.audio_history[str(st.session_state.current_index)] = st.session_state.audio_path
            save_cached_session()
            st.rerun()

if st.session_state.stage == 1:
    st.text_input("Type the Pinyin you hear:", key="pinyin_input")
    if st.button("Submit Pinyin", type="primary", use_container_width=True):
        st.session_state.user_pinyin = st.session_state.pinyin_input
        advance_to_stage_2()
        st.rerun()

# ==========================================
# 7. STAGE 2: MULTIPLE CHOICE MEANING
# ==========================================
if st.session_state.stage >= 2:
    st.success(f"**Your Pinyin:** {st.session_state.user_pinyin}")
    
if st.session_state.stage == 2:
    st.markdown("### What does the sentence mean?")
    st.info("Select the most accurate, nuanced translation:")
    
    if not st.session_state.shuffled_options or len(st.session_state.shuffled_options) < 2:
        st.error("⚠️ The AI failed to generate the multiple-choice options properly.")
        if st.button("🔄 Regenerate This Word", type="primary"):
            st.session_state.current_exercise = None
            st.session_state.audio_path = None
            st.session_state.stage = 1
            save_cached_session()
            st.rerun()
    else:
        selected_meaning = st.radio("Choose translation:", st.session_state.shuffled_options, index=None, label_visibility="collapsed")
        
        if st.button("Submit Meaning", type="primary", use_container_width=True, disabled=(selected_meaning is None)):
            if selected_meaning == st.session_state.current_exercise['english_correct']:
                st.session_state.mcq_correct = True
            else:
                st.session_state.mcq_correct = False
                
            advance_to_stage_3()
            st.rerun()

# ==========================================
# 8. STAGE 3: THE REVIEW PHASE & DICTIONARY
# ==========================================
if st.session_state.stage == 3:
    st.markdown("---")
    st.markdown("### The Solution")
    
    if st.session_state.mcq_correct is not None:
        if st.session_state.mcq_correct:
            st.success("✅ **Translation:** Correct!")
        else:
            st.error("❌ **Translation:** Incorrect.")
    
    st.info(f"**Correct Pinyin:** {st.session_state.current_exercise['pinyin']}")
    st.info(f"**Correct English:** {st.session_state.current_exercise['english_correct']}")
    st.caption(f"*(Characters: {st.session_state.current_exercise['chinese']})*")
    
    gp = st.session_state.current_exercise.get('grammar_point')
    if gp and gp.get('structure'):
        st.markdown("#### 🧠 Grammar Point")
        st.info(f"**{gp['structure']}**: {gp['explanation']}")

    pn = st.session_state.current_exercise.get('particle_note')
    if pn and pn.get('particle'):
        st.markdown("#### 🗣️ Local Particle")
        st.warning(f"**{pn['particle']}**: {pn['explanation']}")

    st.markdown("#### 📖 Dictionary Breakdown")
    st.write("Click on any Pinyin word below to reveal its meaning and character.")
    
    words = st.session_state.current_exercise.get('word_breakdown', [])
    
    cols_per_row = 3
    for i in range(0, len(words), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(words):
                word = words[i + j]
                
                char = word.get('chinese', word.get('hanzi', '?'))
                pleco_url = f"plecoapi://x-callback-url/s?q={char}"
                mdbg_url = f"https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb={char}"
                
                with col:
                    with st.expander(f"{word.get('pinyin', '')}"):
                        st.write(f"**{word.get('english', '')}**")
                        st.caption(f"Char: {char}")
                        
                        button_key = f"flag_btn_{i}_{j}_{char}"
                        if st.button("🚩 Needs Practice", key=button_key):
                            flag_word_in_database(char)
                            st.toast(f"Flagged '{char}' for more practice!")
                        
                        st.markdown("---")
                        st.markdown(f"📱 [Open in Pleco]({pleco_url})")
                        st.markdown(f"💻 [Open in Web]({mdbg_url})")

    st.markdown("---")
    st.markdown("#### Grade yourself (Be honest!):")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Again (0)\nFailed both", use_container_width=True):
            grade_word_and_next(0)
            st.rerun()
    with col2:
        if st.button("Hard (1)\nMissed one", use_container_width=True):
            grade_word_and_next(1)
            st.rerun()
    with col3:
        if st.button("Good (2)\nGot both", use_container_width=True):
            grade_word_and_next(2)
            st.rerun()
    with col4:
        if st.button("Easy (3)\nInstant", use_container_width=True):
            grade_word_and_next(3)
            st.rerun()
