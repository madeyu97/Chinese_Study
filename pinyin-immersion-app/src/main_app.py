# src/main_app.py

import streamlit as st
import os
import random

# Import our custom modules
from srs_engine import get_todays_quiz_batch, process_review
from ai_prompter import generate_dictation_exercise
from audio_engine import create_audio_file
from db_manager import flag_word_in_database, get_progress_stats

# ==========================================
# 1. APP CONFIGURATION & STATE MANAGEMENT
# ==========================================
st.set_page_config(page_title="Pinyin Immersion", page_icon="🎧", layout="centered")

# Initialize Session State variables
if 'words_due' not in st.session_state:
    st.session_state.words_due = get_todays_quiz_batch()
    st.session_state.current_index = 0
    st.session_state.current_exercise = None
    st.session_state.audio_path = None
    
    # New Multi-Stage UI trackers
    st.session_state.stage = 1 # Stage 1: Pinyin, Stage 2: MCQ, Stage 3: Grading
    st.session_state.shuffled_options = []
    st.session_state.user_pinyin = ""

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def grade_word_and_next(grade):
    """Saves the score and completely resets the UI state for the next word."""
    current_word = st.session_state.words_due[st.session_state.current_index]
    
    process_review(
        word_id=current_word['id'],
        current_interval=current_word['interval'],
        current_ease=current_word['ease_factor'],
        grade=grade
    )
    
    # Move to the next word and reset all trackers
    st.session_state.current_index += 1
    st.session_state.current_exercise = None
    st.session_state.audio_path = None
    st.session_state.stage = 1
    st.session_state.shuffled_options = []
    st.session_state.user_pinyin = ""

def advance_to_stage_2():
    st.session_state.stage = 2

def advance_to_stage_3():
    st.session_state.stage = 3

# ==========================================
# 3. THE MAIN USER INTERFACE
# ==========================================
st.title("🎧 Pinyin Immersion Study")

# ==========================================
# 3.5 THE PROGRESS SIDEBAR
# ==========================================
# ==========================================
# 3.5 THE PROGRESS SIDEBAR
# ==========================================
with st.sidebar:
    st.header("📊 Global Progress")
    stats = get_progress_stats()
    
    if stats['total'] > 0:
        # Calculate percentages
        unseen_pct = int((stats['unseen'] / stats['total']) * 100)
        learning_pct = int((stats['learning'] / stats['total']) * 100)
        mastered_pct = int((stats['mastered'] / stats['total']) * 100)
        
        # Display the total prominently
        st.metric("Total CSV Vocabulary", stats['total'])
        st.markdown("---")
        
        # Unseen Tracker
        st.write(f"**👀 Unseen:** {stats['unseen']} words ({unseen_pct}%)")
        st.progress(stats['unseen'] / stats['total'])
        
        # Learning Tracker
        st.write(f"**🧠 Learning:** {stats['learning']} words ({learning_pct}%)")
        st.progress(stats['learning'] / stats['total'])
        
        # Mastered Tracker
        st.write(f"**🏆 Mastered:** {stats['mastered']} words ({mastered_pct}%)")
        st.progress(stats['mastered'] / stats['total'])
        
        st.markdown("---")
        st.caption("Mastered = successfully pushed 21+ days into the future.")
    else:
        st.write("No vocabulary found. Please check your CSV.")

if st.session_state.current_index >= len(st.session_state.words_due):
    st.success("🎉 You're all caught up for today! Great job.")
    st.balloons()
    st.stop()

current_word = st.session_state.words_due[st.session_state.current_index]

# Display Progress
total_words = len(st.session_state.words_due)
st.progress((st.session_state.current_index) / total_words)
st.caption(f"Reviewing word {st.session_state.current_index + 1} of {total_words}")

st.markdown("---")

# ==========================================
# 4. GENERATING THE EXERCISE
# ==========================================
if st.session_state.current_exercise is None:
    with st.spinner("Generating localized audio scenario..."):
        exercise_data = generate_dictation_exercise(current_word)
        
        if exercise_data:
            st.session_state.current_exercise = exercise_data
            st.session_state.audio_path = create_audio_file(exercise_data['chinese'])
            
            # Combine the correct answer and distractors, then shuffle them
            options = exercise_data['english_distractors'] + [exercise_data['english_correct']]
            random.shuffle(options)
            st.session_state.shuffled_options = options
        else:
            st.error("Failed to generate exercise. Check your API connection.")
            st.stop()

# ==========================================
# 5. STAGE 1: PINYIN DICTATION
# ==========================================
st.subheader("Listen & Transcribe:")
if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
    st.audio(st.session_state.audio_path, format="audio/mp3")

if st.session_state.stage == 1:
    st.text_input("Type the Pinyin you hear:", key="pinyin_input")
    if st.button("Submit Pinyin", type="primary", use_container_width=True):
        st.session_state.user_pinyin = st.session_state.pinyin_input
        advance_to_stage_2()
        st.rerun()

# ==========================================
# 6. STAGE 2: MULTIPLE CHOICE MEANING
# ==========================================
if st.session_state.stage >= 2:
    st.success(f"**Your Pinyin:** {st.session_state.user_pinyin}")
    
if st.session_state.stage == 2:
    st.markdown("### What does the sentence mean?")
    st.info("Select the most accurate, nuanced translation:")
    
    # Render the 5 shuffled options as a radio button list
    selected_meaning = st.radio("Choose translation:", st.session_state.shuffled_options, index=None, label_visibility="collapsed")
    
    if st.button("Submit Meaning", type="primary", use_container_width=True, disabled=(selected_meaning is None)):
        advance_to_stage_3()
        st.rerun()

# ==========================================
# 7. STAGE 3: THE REVIEW PHASE & DICTIONARY
# ==========================================
if st.session_state.stage == 3:
    st.markdown("---")
    st.markdown("### The Solution")
    
    st.success(f"**Correct Pinyin:** {st.session_state.current_exercise['pinyin']}")
    st.info(f"**Correct English:** {st.session_state.current_exercise['english_correct']}")
    st.caption(f"*(Characters: {st.session_state.current_exercise['chinese']})*")
    
    # --- Grammar Point ---
    gp = st.session_state.current_exercise.get('grammar_point')
    if gp and gp.get('structure'):
        st.markdown("#### 🧠 Grammar Point")
        st.warning(f"**{gp['structure']}**: {gp['explanation']}")

    # --- Dictionary Breakdown ---
    st.markdown("#### 📖 Dictionary Breakdown")
    st.write("Click on any Pinyin word below to reveal its meaning and character.")
    
    words = st.session_state.current_exercise.get('word_breakdown', [])
    
    cols_per_row = 3
    for i in range(0, len(words), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(words):
                word = words[i + j]
                
                # --- FIXED: Re-added the missing char variable and URL logic ---
                char = word.get('chinese', word.get('hanzi', '?'))
                pleco_url = f"plecoapi://x-callback-url/s?q={char}"
                mdbg_url = f"https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb={char}"
                
                with col:
                    with st.expander(f"{word.get('pinyin', '')}"):
                        st.write(f"**{word.get('english', '')}**")
                        st.caption(f"Char: {char}")
                        
                        # --- The Flag Button ---
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