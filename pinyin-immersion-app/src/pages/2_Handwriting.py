# src/pages/2_Handwriting.py
"""
Handwriting drill.

Runs inside one bidirectional component (src/hw_component): semantic recall
cues (word context + pinyin, never the character itself), gold ink on a dark
米字格 board, a watch→trace→write ladder for new characters, objective
auto-grading, and zero page reloads. Results stream back and save to the SRS
per attempt.

Struggle-aware drilling:
  • Standard sessions requeue a character later in the same session after
    >3 mistakes, and pin its next review to tomorrow.
  • A dedicated "Drill my weak characters" mode ranks characters by recent
    mistake rate; pick any and loop each until written clean twice in a row.
"""

import uuid

import streamlit as st

from hanzi_component import hanzi_drill
from db_manager import (
    get_handwriting_session,
    get_focus_session,
    get_struggle_session,
    get_weak_characters,
    get_handwriting_counts,
    update_handwriting_progress,
    get_handwriting_stats,
    get_char_state,
)

st.set_page_config(page_title="Handwriting", page_icon="✍️", layout="centered")

# ----------------------------------------------------------------------
# SIDEBAR
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
# RESULT INTAKE — incremental, per-attempt, handles repeated characters
# ----------------------------------------------------------------------
def process_results(value):
    if not value or value.get("session_id") != st.session_state.get("hw_sid"):
        return
    results = value.get("results", [])
    done_before = st.session_state.hw_processed
    for r in results[done_before:]:
        ch = r["character"]
        # Fetch the character's *current* stored state each time so the
        # recent-grade / recent-mistake windows roll correctly even when a
        # character is drilled several times in one session.
        state = get_char_state(ch) or st.session_state.hw_state_seed.get(ch, {})
        update_handwriting_progress(
            ch, int(r["grade"]), state, mistakes=int(r.get("mistakes", 0)))
    st.session_state.hw_processed = len(results)
    if value.get("done"):
        st.session_state.hw_done = True
        st.session_state.hw_final = results


def launch(chars, mode):
    st.session_state.hw_payload = {
        "session_id": str(uuid.uuid4()), "chars": chars, "mode": mode}
    st.session_state.hw_sid = st.session_state.hw_payload["session_id"]
    st.session_state.hw_processed = 0
    st.session_state.hw_done = False
    # seed states so the first grade of each char has its SRS/history context
    st.session_state.hw_state_seed = {c["character"]: c for c in chars}
    st.rerun()


# ----------------------------------------------------------------------
# SETUP SCREEN
# ----------------------------------------------------------------------
if "hw_payload" not in st.session_state:
    st.title("✍️ Handwriting Drill")

    tab_review, tab_weak, tab_focus = st.tabs(
        ["📆 Review session", "🎯 Drill weak characters", "🔍 Focus on a word"])

    # --- standard review session ---
    with tab_review:
        due, new_available = get_handwriting_counts()
        c1, c2 = st.columns(2)
        c1.metric("Due for review", due)
        c2.metric("New available", new_available)
        new_count = st.slider("New characters this session", 0, 15, 5)
        st.caption(
            "Cue = word, pinyin and meaning — never the character itself. "
            "New characters run watch → trace → write; reviews go straight to "
            "writing. Miss a character more than 3× and it comes back later in "
            "the session, with its next review pulled to tomorrow.")
        if st.button("▶️ Start review", type="primary", use_container_width=True,
                     disabled=(due + min(new_count, new_available) == 0)):
            chars = get_handwriting_session(new_count=new_count)
            if chars:
                launch(chars, "standard")
            else:
                st.info("Nothing to drill yet — study some vocabulary first.")

    # --- weakness drill ---
    with tab_weak:
        st.caption("Characters you've been missing most, worst first "
                   "(ranked by recent mistake rate). Pick any to loop — each "
                   "repeats until you write it clean twice in a row.")
        weak = get_weak_characters(limit=40)
        if not weak:
            st.info("No struggle data yet. Do a few review sessions and the "
                    "characters you miss will show up here.")
        else:
            labels = [
                f"{w['character']}  ·  {w['char_pinyin']}  ·  "
                f"avg {w['recent_mistake_rate']} miss  ·  {w['word_english'][:24]}"
                for w in weak
            ]
            picked = st.multiselect(
                "Select characters to drill", options=list(range(len(weak))),
                format_func=lambda i: labels[i],
                default=list(range(min(5, len(weak)))))
            cola, colb = st.columns(2)
            if cola.button("🔁 Drill selected", type="primary",
                           use_container_width=True, disabled=not picked):
                chars = get_struggle_session([weak[i]["character"] for i in picked])
                launch(chars, "struggle")
            if colb.button("🔥 Drill top 10", use_container_width=True,
                           disabled=len(weak) == 0):
                chars = get_struggle_session([w["character"] for w in weak[:10]])
                launch(chars, "struggle")

    # --- focus on a word ---
    with tab_focus:
        st.caption("Drill every character in a specific word or phrase, "
                   "regardless of due dates.")
        focus = st.text_input("Word or phrase (hanzi)", "",
                              placeholder="e.g. 巴刹")
        if st.button("Start focus session", use_container_width=True,
                     disabled=not focus.strip()):
            chars = get_focus_session(focus.strip())
            if chars:
                launch(chars, "standard")
            else:
                st.warning("No Chinese characters found in that text.")

    st.stop()

# ----------------------------------------------------------------------
# ACTIVE DRILL
# ----------------------------------------------------------------------
value = hanzi_drill(session=st.session_state.hw_payload,
                    key=f"drill_{st.session_state.hw_sid}", default=None)
process_results(value)

mode_label = "struggle loop" if st.session_state.hw_payload["mode"] == "struggle" else "review"
st.caption(f"💾 {st.session_state.hw_processed} attempts saved · {mode_label}")

if st.session_state.get("hw_done"):
    counts = [0, 0, 0, 0]
    for r in st.session_state.get("hw_final", []):
        counts[int(r["grade"])] += 1
    st.success(
        f"Session saved — Easy {counts[3]} · Good {counts[2]} · "
        f"Hard {counts[1]} · Again {counts[0]}")
    if st.button("🔄 New session", type="primary", use_container_width=True):
        for k in ("hw_payload", "hw_sid", "hw_processed", "hw_done",
                  "hw_final", "hw_state_seed"):
            st.session_state.pop(k, None)
        st.rerun()
else:
    with st.expander("End session early"):
        st.caption("Progress so far is already saved.")
        if st.button("🏁 End now", use_container_width=True):
            for k in ("hw_payload", "hw_sid", "hw_processed", "hw_done",
                      "hw_final", "hw_state_seed"):
                st.session_state.pop(k, None)
            st.rerun()
