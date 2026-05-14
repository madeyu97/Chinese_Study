# src/main_app.py

import streamlit as st
import os
import random
import json
from datetime import date

from srs_engine import get_todays_quiz_batch, process_review
from ai_prompter import generate_dictation_exercise
from audio_engine import create_audio_file
from db_manager import (
    flag_word_in_database, get_progress_stats, undo_word_progress,
    get_more_words, delete_word_from_db, update_word_in_db,
)
from speech_engine import transcribe_audio, grade_speech, GRADE_MAP
from config import LISTENING_PCT, MAX_REVIEWS_PER_DAY

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
        "modes": st.session_state.modes,
        "current_index": st.session_state.current_index,
        "current_exercise": st.session_state.current_exercise,
        "audio_path": st.session_state.audio_path,
        "stage": st.session_state.stage,
        "shuffled_options": st.session_state.shuffled_options,
        "user_pinyin": st.session_state.user_pinyin,
        "mcq_correct": st.session_state.mcq_correct,
        "exercise_history": st.session_state.exercise_history,
        "audio_history": st.session_state.audio_history,
        "recall_result": st.session_state.recall_result,
        "recall_history": st.session_state.recall_history,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)

def clear_cached_session():
    """Delete the on-disk cache so the next run starts from setup."""
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass

# ==========================================
# 2. APP CONFIGURATION
# ==========================================
st.set_page_config(page_title="Pinyin Immersion", page_icon="🎧", layout="centered")

def assign_modes(words):
    """Assign each card 'listen' or 'recall', then shuffle."""
    n = len(words)
    listening_count = round(n * LISTENING_PCT)
    modes = ['listen'] * listening_count + ['recall'] * (n - listening_count)
    random.shuffle(modes)
    return modes

# Midnight reset
if 'session_date' in st.session_state and st.session_state.session_date != str(date.today()):
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# ==========================================
# 3. SESSION INITIALISATION — restore from cache OR show setup screen
# ==========================================
if 'words_due' not in st.session_state:
    cached_state = load_cached_session()
    if cached_state:
        # Resume an in-progress session
        for key, value in cached_state.items():
            if key != "date":
                st.session_state[key] = value
        if 'modes' not in st.session_state or not st.session_state.modes:
            st.session_state.modes = assign_modes(st.session_state.words_due)
        if 'recall_result' not in st.session_state:
            st.session_state.recall_result = None
        if 'recall_history' not in st.session_state:
            st.session_state.recall_history = {}
        st.session_state.session_date = str(date.today())
    else:
        # No cache — show the setup screen
        st.title("🎧 Pinyin Immersion Study")
        stats = get_progress_stats()
        st.markdown(f"You have **{stats['total']}** words in your vocabulary database.")
        st.markdown("### How long should today's session be?")

        with st.form("session_setup"):
            session_size = st.number_input(
                "Number of questions",
                min_value=1,
                max_value=max(1, stats['total']) if stats['total'] > 0 else 100,
                value=min(MAX_REVIEWS_PER_DAY, stats['total']) if stats['total'] > 0 else MAX_REVIEWS_PER_DAY,
                step=1,
                help=f"Pick anywhere from 1 to {stats['total']} (your full vocabulary).",
            )
            listen_count = round(session_size * LISTENING_PCT)
            recall_count = session_size - listen_count
            st.caption(
                f"That's roughly **🎧 {listen_count} listening + 🎤 {recall_count} recall** "
                f"based on your {int(LISTENING_PCT*100)}/{int((1-LISTENING_PCT)*100)} mix."
            )
            start = st.form_submit_button("▶️ Start Session", type="primary", use_container_width=True)

        if not start:
            st.stop()

        # User clicked Start — build the session
        with st.spinner("Building your session..."):
            st.session_state.words_due = get_todays_quiz_batch(session_size=int(session_size))
            st.session_state.modes = assign_modes(st.session_state.words_due)
            st.session_state.current_index = 0
            st.session_state.current_exercise = None
            st.session_state.audio_path = None
            st.session_state.stage = 1
            st.session_state.shuffled_options = []
            st.session_state.user_pinyin = ""
            st.session_state.mcq_correct = None
            st.session_state.exercise_history = {}
            st.session_state.audio_history = {}
            st.session_state.recall_result = None
            st.session_state.recall_history = {}
            st.session_state.session_date = str(date.today())
            save_cached_session()
        st.rerun()

# ==========================================
# 4. HELPERS
# ==========================================
def reset_card_state():
    st.session_state.current_exercise = None
    st.session_state.audio_path = None
    st.session_state.stage = 1
    st.session_state.shuffled_options = []
    st.session_state.user_pinyin = ""
    st.session_state.mcq_correct = None
    st.session_state.recall_result = None

def grade_word_and_next(grade):
    current_word = st.session_state.words_due[st.session_state.current_index]
    process_review(
        word_id=current_word['id'],
        current_interval=current_word['interval'],
        current_ease=current_word['ease_factor'],
        grade=grade
    )
    st.session_state.current_index += 1
    reset_card_state()
    save_cached_session()

def undo_last_grade():
    if st.session_state.current_index > 0:
        prev_index = st.session_state.current_index - 1
        original_word = st.session_state.words_due[prev_index]
        undo_word_progress(
            word_id=original_word['id'],
            old_next_review_date=original_word['next_review_date'],
            old_interval=original_word['interval'],
            old_ease=original_word['ease_factor'],
            old_review_count=original_word['review_count'],
            old_priority=original_word.get('priority_weight', 1)
        )
        st.session_state.current_index = prev_index
        idx_str = str(prev_index)
        st.session_state.current_exercise = st.session_state.exercise_history.get(idx_str)
        st.session_state.audio_path = st.session_state.audio_history.get(idx_str)
        if st.session_state.modes[prev_index] == 'recall':
            st.session_state.recall_result = st.session_state.recall_history.get(idx_str)
            st.session_state.stage = 2
        else:
            st.session_state.stage = 3
        save_cached_session()

def advance_to_stage(n):
    st.session_state.stage = n
    save_cached_session()

def start_new_session():
    """Wipe everything so the user gets the setup screen again."""
    clear_cached_session()
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# ==========================================
# 5. MAIN UI — SHARED HEADER
# ==========================================
st.title("🎧 Pinyin Immersion Study")

# Session-complete screen
if st.session_state.current_index >= len(st.session_state.words_due):
    st.success("🎉 You're all caught up for today! Great job.")
    st.balloons()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("➕ Do 5 More Words", type="secondary", use_container_width=True):
            with st.spinner("Fetching more words..."):
                exclude_ids = [w['id'] for w in st.session_state.words_due]
                extra_words = get_more_words(exclude_ids, amount=5)
                if extra_words:
                    st.session_state.words_due.extend(extra_words)
                    st.session_state.modes.extend(assign_modes(extra_words))
                    save_cached_session()
                    st.rerun()
                else:
                    st.warning("You've completely exhausted your database!")
    with col_b:
        if st.button("🔄 Start New Session", type="primary", use_container_width=True):
            start_new_session()
            st.rerun()
    st.stop()

current_word = st.session_state.words_due[st.session_state.current_index]
current_mode = st.session_state.modes[st.session_state.current_index]

# Header row: progress / mode / undo
total_words = len(st.session_state.words_due)
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.progress((st.session_state.current_index) / total_words)
    st.caption(f"Reviewing word {st.session_state.current_index + 1} of {total_words}")
with col2:
    badge = "🎧 Listen" if current_mode == 'listen' else "🎤 Recall"
    st.caption(f"**{badge}**")
with col3:
    if st.session_state.current_index > 0:
        if st.button("↩️ Undo", use_container_width=True):
            undo_last_grade()
            st.rerun()

st.markdown("---")

# ==========================================
# 5.5 SIDEBAR
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
        st.caption("Mastered = pushed 21+ days into the future.")

        st.markdown("---")
        listen_left = sum(1 for i, m in enumerate(st.session_state.modes)
                          if i >= st.session_state.current_index and m == 'listen')
        recall_left = sum(1 for i, m in enumerate(st.session_state.modes)
                          if i >= st.session_state.current_index and m == 'recall')
        st.caption(f"This session: 🎧 {listen_left} listening · 🎤 {recall_left} recall")

        st.markdown("---")
        if st.button("🔄 End & Start New Session", use_container_width=True):
            start_new_session()
            st.rerun()
    else:
        st.write("No vocabulary found. Please check your CSV.")

# ==========================================
# 6. EXERCISE GENERATION (shared by both modes)
# ==========================================
if st.session_state.current_exercise is None:
    with st.spinner("Generating localized scenario..."):
        exercise_data = generate_dictation_exercise(current_word)
        if exercise_data:
            st.session_state.current_exercise = exercise_data
            audio_script = exercise_data['chinese']
            st.session_state.audio_path = create_audio_file(audio_script)

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
# Reusable renderers
# ==========================================
def render_breakdown():
    ex = st.session_state.current_exercise
    gp = ex.get('grammar_point')
    if gp and gp.get('structure'):
        st.markdown("#### 🧠 Grammar Point")
        st.info(f"**{gp['structure']}**: {gp['explanation']}")
    pn = ex.get('particle_note')
    if pn and pn.get('particle'):
        st.markdown("#### 🗣️ Local Particle")
        st.warning(f"**{pn['particle']}**: {pn['explanation']}")
    st.markdown("#### 📖 Dictionary Breakdown")
    words = ex.get('word_breakdown', [])
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
                        button_key = f"flag_btn_{st.session_state.current_index}_{i}_{j}_{char}"
                        if st.button("🚩 Needs Practice", key=button_key):
                            flag_word_in_database(char)
                            st.toast(f"Flagged '{char}' for more practice!")
                        st.markdown("---")
                        st.markdown(f"📱 [Open in Pleco]({pleco_url})")
                        st.markdown(f"💻 [Open in Web]({mdbg_url})")

def render_card_settings():
    st.markdown("---")
    with st.expander("⚙️ Card Settings (Edit or Delete)"):
        st.caption("Tweak this word's context to guide the AI, or remove it entirely.")
        edit_col1, edit_col2, edit_col3 = st.columns(3)
        with edit_col1:
            edit_hanzi = st.text_input("Hanzi", current_word.get('chinese', ''))
        with edit_col2:
            edit_pinyin = st.text_input("Pinyin", current_word.get('pinyin', ''))
        with edit_col3:
            edit_english = st.text_input("Meaning (AI Prompt Hint)", current_word.get('english', ''))
        btn_col1, btn_col2 = st.columns([1, 1])
        with btn_col1:
            if st.button("💾 Save & Regenerate Card", use_container_width=True):
                update_word_in_db(current_word['id'], edit_hanzi, edit_pinyin, edit_english)
                st.session_state.words_due[st.session_state.current_index]['chinese'] = edit_hanzi
                st.session_state.words_due[st.session_state.current_index]['pinyin'] = edit_pinyin
                st.session_state.words_due[st.session_state.current_index]['english'] = edit_english
                reset_card_state()
                save_cached_session()
                st.rerun()
        with btn_col2:
            if st.button("🗑️ Delete Word Permanently", type="secondary", use_container_width=True):
                delete_word_from_db(current_word['id'])
                st.session_state.words_due.pop(st.session_state.current_index)
                st.session_state.modes.pop(st.session_state.current_index)
                reset_card_state()
                save_cached_session()
                st.rerun()

def render_grade_buttons(suggested_grade=None):
    st.markdown("---")
    st.markdown("#### Grade yourself (Be honest!):")
    labels = ["Again (0)\nFailed", "Hard (1)\nStruggled", "Good (2)\nSolid", "Easy (3)\nInstant"]
    cols = st.columns(4)
    for i, (col, label) in enumerate(zip(cols, labels)):
        with col:
            btn_type = "primary" if i == suggested_grade else "secondary"
            if st.button(label, use_container_width=True, key=f"grade_{i}", type=btn_type):
                grade_word_and_next(i)
                st.rerun()


# ==========================================
# 7A. LISTENING FLOW
# ==========================================
if current_mode == 'listen':
    st.subheader("Listen & Transcribe:")
    if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
        st.audio(st.session_state.audio_path, format="audio/mp3")
    else:
        st.warning("⚠️ The audio engine failed to generate the voice file.")
        if st.button("🔄 Retry Audio", type="primary"):
            with st.spinner("Retrying audio..."):
                audio_script = st.session_state.current_exercise['chinese']
                st.session_state.audio_path = create_audio_file(audio_script)
                st.session_state.audio_history[str(st.session_state.current_index)] = st.session_state.audio_path
                save_cached_session()
                st.rerun()

    if st.session_state.stage == 1:
        st.text_input("Type the Pinyin you hear:", key="pinyin_input")
        if st.button("Submit Pinyin", type="primary", use_container_width=True):
            st.session_state.user_pinyin = st.session_state.pinyin_input
            advance_to_stage(2)
            st.rerun()

    if st.session_state.stage >= 2:
        st.success(f"**Your Pinyin:** {st.session_state.user_pinyin}")

    if st.session_state.stage == 2:
        st.markdown("### What does the sentence mean?")
        st.info("Select the most accurate, nuanced translation:")
        if not st.session_state.shuffled_options or len(st.session_state.shuffled_options) < 2:
            st.error("⚠️ The AI failed to generate the multiple-choice options properly.")
            if st.button("🔄 Regenerate This Word", type="primary"):
                reset_card_state()
                save_cached_session()
                st.rerun()
        else:
            selected_meaning = st.radio("Choose translation:", st.session_state.shuffled_options, index=None, label_visibility="collapsed")
            if st.button("Submit Meaning", type="primary", use_container_width=True, disabled=(selected_meaning is None)):
                st.session_state.mcq_correct = (selected_meaning == st.session_state.current_exercise['english_correct'])
                advance_to_stage(3)
                st.rerun()

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
        render_breakdown()
        render_card_settings()
        render_grade_buttons()


# ==========================================
# 7B. RECALL FLOW
# ==========================================
elif current_mode == 'recall':
    st.subheader("🎤 Speak the Chinese:")
    st.markdown(
        f"**Say this in Chinese:** _{st.session_state.current_exercise['english_correct']}_"
    )
    st.caption(f"Target word meaning: _{current_word.get('english', '')}_")

    if st.session_state.stage == 1:
        st.info("Tap to record, speak the sentence, then submit.")
        audio_value = st.audio_input("🎙️ Your attempt", key=f"mic_{st.session_state.current_index}")

        if audio_value is not None:
            if st.button("✅ Submit Recording", type="primary", use_container_width=True):
                audio_bytes = audio_value.getvalue()
                with st.spinner("Transcribing with Whisper..."):
                    transcription = transcribe_audio(audio_bytes)
                if transcription is None:
                    st.error("Transcription failed — try again.")
                    st.stop()
                with st.spinner("Grading your attempt..."):
                    grading = grade_speech(
                        expected_chinese=st.session_state.current_exercise['chinese'],
                        expected_pinyin=st.session_state.current_exercise['pinyin'],
                        expected_english=st.session_state.current_exercise['english_correct'],
                        transcribed_text=transcription['text'],
                    )
                if grading is None:
                    st.error("Grading failed — try again, or skip to grade yourself manually.")
                    st.stop()
                st.session_state.recall_result = {
                    "transcription": transcription,
                    "grading": grading,
                }
                st.session_state.recall_history[str(st.session_state.current_index)] = st.session_state.recall_result
                advance_to_stage(2)
                st.rerun()

        with st.expander("Can't record right now?"):
            if st.button("⏭️ Skip recording and self-grade"):
                st.session_state.recall_result = None
                advance_to_stage(2)
                st.rerun()

    if st.session_state.stage == 2:
        result = st.session_state.recall_result
        st.markdown("---")
        st.markdown("### The Solution")

        st.info(f"**Correct Chinese:** {st.session_state.current_exercise['chinese']}")
        st.info(f"**Correct Pinyin:** {st.session_state.current_exercise['pinyin']}")
        st.caption(f"*(Meaning: {st.session_state.current_exercise['english_correct']})*")

        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            st.caption("How it should sound:")
            st.audio(st.session_state.audio_path, format="audio/mp3")

        if result is not None:
            grading = result['grading']
            transcription = result['transcription']

            st.markdown("#### 📝 Whisper heard:")
            st.code(transcription['text'] or "(nothing audible)", language=None)

            s1, s2, s3 = st.columns(3)
            with s1: st.metric("Vocab", f"{grading['vocab_score']}/10")
            with s2: st.metric("Grammar", f"{grading['grammar_score']}/10")
            with s3: st.metric("Pronunciation*", f"{grading['pronunciation_score']}/10")
            st.caption("*Pronunciation is inferred from Whisper transcription fidelity — it can't grade tones directly.")

            st.markdown("#### 💬 Feedback")
            st.write(grading['feedback'])

            suggested = GRADE_MAP.get(grading['overall_grade'], 2)
            st.caption(f"Suggested SRS grade: **{grading['overall_grade']}** (you can override below).")
        else:
            suggested = None
            st.caption("No recording submitted — grade yourself below.")

        render_breakdown()
        render_card_settings()
        render_grade_buttons(suggested_grade=suggested)
