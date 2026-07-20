# src/pages/2_✍️_Handwriting.py
"""
Handwriting drill — full rebuild.

The entire drill runs inside one bidirectional component (src/hw_component):
semantic recall cues (word context + pinyin, never the character itself),
gold ink on a dark 米字格 board, a watch→trace→write ladder for new
characters, objective auto-grading from stroke mistakes, and zero page
reloads. Results stream back incrementally and are saved to the SRS as you
go, so nothing is lost even if you close mid-session.
"""

import uuid

import streamlit as st

from hanzi_component import hanzi_drill
from db_manager import (
    get_handwriting_session,
    get_focus_session,
    get_handwriting_counts,
    update_handwriting_progress,
    get_handwriting_stats,
)

st.set_page_config(page_title="Handwriting", page_icon="✍️", layout="centered")

GRADE_NAMES = ["Again", "Hard", "Good", "Easy"]

# ----------------------------------------------------------------------
# SIDEBAR — stats only, no settings clutter
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("✍️ Handwriting")
    hw_stats = get_handwriting_stats()
    total = hw_stats["total_chars_available"]
    st.metric("Characters in your vocab", total)
    if total:
        st.write(f"**✏️ Practiced:** {hw_stats['practiced']}")
        st.progress(hw_stats["practiced"] / total)
        st.write(f"**🏆 Mastered:** {hw_stats['mastered']}")
        st.progress(hw_stats["mastered"] / total)
        st.caption("Mastered = review pushed 21+ days out.")

# ----------------------------------------------------------------------
# RESULT INTAKE — incremental, idempotent
# ----------------------------------------------------------------------
def process_results(value):
    if not value or value.get("session_id") != st.session_state.get("hw_sid"):
        return
    results = value.get("results", [])
    done_before = st.session_state.hw_processed
    by_char = {c["character"]: c for c in st.session_state.hw_payload["chars"]}
    for r in results[done_before:]:
        state = by_char.get(r["character"])
        if state is not None:
            update_handwriting_progress(r["character"], int(r["grade"]), state)
    st.session_state.hw_processed = len(results)
    if value.get("done"):
        st.session_state.hw_done = True
        st.session_state.hw_final = results

# ----------------------------------------------------------------------
# SETUP SCREEN
# ----------------------------------------------------------------------
if "hw_payload" not in st.session_state:
    st.title("✍️ Handwriting Drill")
    due, new_available = get_handwriting_counts()
    c1, c2 = st.columns(2)
    c1.metric("Due for review", due)
    c2.metric("New available", new_available)

    new_count = st.slider("New characters this session", 0, 15, 5)
    st.caption(
        "During the drill you'll see the **word, its pinyin and meaning** as "
        "the cue — never the character itself. New characters run "
        "watch → trace → write; reviews go straight to writing from memory.")

    if st.button("▶️ Start session", type="primary", use_container_width=True,
                 disabled=(due + min(new_count, new_available) == 0)):
        chars = get_handwriting_session(new_count=new_count)
        if chars:
            st.session_state.hw_payload = {
                "session_id": str(uuid.uuid4()), "chars": chars}
            st.session_state.hw_sid = st.session_state.hw_payload["session_id"]
            st.session_state.hw_processed = 0
            st.session_state.hw_done = False
            st.rerun()
        else:
            st.info("Nothing to drill yet — study some vocabulary first.")

    with st.expander("🎯 Focus mode — drill one word's characters"):
        focus = st.text_input(
            "Word or phrase (hanzi)", "",
            placeholder="e.g. 巴刹 — drills each character, due or not")
        if st.button("Start focus session", use_container_width=True,
                     disabled=not focus.strip()):
            chars = get_focus_session(focus.strip())
            if chars:
                st.session_state.hw_payload = {
                    "session_id": str(uuid.uuid4()), "chars": chars}
                st.session_state.hw_sid = st.session_state.hw_payload["session_id"]
                st.session_state.hw_processed = 0
                st.session_state.hw_done = False
                st.rerun()
            else:
                st.warning("No Chinese characters found in that text.")

    if due + new_available == 0:
        st.info("Study vocabulary on the main page first — its characters "
                "become your handwriting queue.")
    st.stop()

# ----------------------------------------------------------------------
# ACTIVE DRILL — one component, constant args, no remounts
# ----------------------------------------------------------------------
value = hanzi_drill(session=st.session_state.hw_payload,
                    key=f"drill_{st.session_state.hw_sid}", default=None)
process_results(value)

saved = st.session_state.hw_processed
queued = len(st.session_state.hw_payload["chars"])
st.caption(f"💾 {saved}/{queued} results saved to SRS")

if st.session_state.get("hw_done"):
    counts = [0, 0, 0, 0]
    for r in st.session_state.get("hw_final", []):
        counts[int(r["grade"])] += 1
    st.success(
        f"Session saved — Easy {counts[3]} · Good {counts[2]} · "
        f"Hard {counts[1]} · Again {counts[0]}")
    if st.button("🔄 New session", type="primary", use_container_width=True):
        for k in ("hw_payload", "hw_sid", "hw_processed", "hw_done", "hw_final"):
            st.session_state.pop(k, None)
        st.rerun()
else:
    with st.expander("End session early"):
        st.caption("Progress so far is already saved.")
        if st.button("🏁 End now", use_container_width=True):
            for k in ("hw_payload", "hw_sid", "hw_processed", "hw_done", "hw_final"):
                st.session_state.pop(k, None)
            st.rerun()
