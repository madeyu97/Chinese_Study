# src/views/2_Handwriting.py
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

New characters are capped per day across every source (and held back while
reviews pile up). As a step of today's plan, a review session from your
chosen source starts straight away.
"""

import time
import uuid
from datetime import date

import streamlit as st

import today_plan as tp
from auth import require_login, sidebar_user_badge
from config import HANDWRITING_NEW_PER_DAY
from hanzi_component import hanzi_drill
from db_manager import (
    herb_character_counts,
    import_herbs_from_csv,
    list_studied_characters,
    get_curriculum_progress,
    get_handwriting_source,
    set_handwriting_source,
    get_focus_session,
    get_struggle_session,
    get_weak_characters,
    handwriting_due_and_new,
    handwriting_new_allowance,
    handwriting_session_for,
    update_handwriting_progress,
    get_handwriting_stats,
    get_char_state,
)

st.set_page_config(page_title="Handwriting", page_icon="✍️", layout="centered")

USER = require_login()
USER_ID = USER["id"]
S = st.session_state
SESSION_KEYS = ("hw_payload", "hw_sid", "hw_processed", "hw_done", "hw_final",
                "hw_state_seed", "hw_plan", "hw_t0", "hw_logged", "hw_plan_empty", "hw_day")
SOURCES = {
    "vocab": "Characters from my vocabulary",
    "frequency": "500 most common characters",
    "herbs": "本草 Herb names",
}


def end_session():
    for k in SESSION_KEYS:
        S.pop(k, None)


if (S.get("hw_plan") or S.get("hw_plan_empty")) and S.get("hw_day") != date.today().isoformat():
    end_session()                   # yesterday's plan left open in the tab

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("handwriting", end_session)


# ----------------------------------------------------------------------
# RESULT INTAKE — incremental, per-attempt, handles repeated characters
# ----------------------------------------------------------------------
def process_results(value):
    if not value or value.get("session_id") != S.get("hw_sid"):
        return
    results = value.get("results", [])
    done_before = S.hw_processed
    for r in results[done_before:]:
        ch = r["character"]
        # Fetch the character's *current* stored state each time so the
        # recent-grade / recent-mistake windows roll correctly even when a
        # character is drilled several times in one session.
        state = get_char_state(USER_ID, ch) or S.hw_state_seed.get(ch, {})
        update_handwriting_progress(
            USER_ID, ch, int(r["grade"]), state, mistakes=int(r.get("mistakes", 0)))
    S.hw_processed = len(results)
    if value.get("done"):
        S.hw_done = True
        S.hw_final = results


def launch(chars, mode, in_plan=False, rerun=True):
    S.hw_payload = {"session_id": str(uuid.uuid4()), "chars": chars, "mode": mode}
    S.hw_sid = S.hw_payload["session_id"]
    S.hw_processed = 0
    S.hw_done = False
    S.hw_plan, S.hw_t0, S.hw_day = in_plan, time.time(), date.today().isoformat()
    S.pop("hw_logged", None)
    # seed states so the first grade of each char has its SRS/history context
    S.hw_state_seed = {c["character"]: c for c in chars}
    if rerun:
        st.rerun()


# ----------------------------------------------------------------------
# TODAY'S PLAN: start straight away
# ----------------------------------------------------------------------
if "hw_payload" not in S and (tp.active("handwriting") or S.get("hw_plan_empty")):
    if not S.get("hw_plan_empty"):
        p_ = tp.params("handwriting")
        due, _avail = handwriting_due_and_new(USER_ID)
        new = min(p_.get("new", 0), handwriting_new_allowance(USER_ID, due))
        chars = handwriting_session_for(USER_ID, new, max_reviews=p_.get("reviews"))
        if chars:
            launch(chars, "standard", in_plan=True)
        S.hw_plan_empty, S.hw_day = True, date.today().isoformat()
        tp.session_done(USER_ID, "handwriting", time.time(), step="handwriting")
    st.success("Nothing to write today.")
    tp.continue_ui(end_session)
    st.stop()


# ----------------------------------------------------------------------
# CHARACTER BROWSER - reached from "My characters"
# ----------------------------------------------------------------------
if S.get("hw_browse") and "hw_payload" not in S:
    SCOPES = {
        "all": "Everything I've practised",
        "learning": "Still learning",
        "mastered": "Mastered",
        "due": "Due for review",
        "weak": "Giving me trouble",
    }
    scope = S.hw_browse
    st.title("📖 My characters")

    scope = st.selectbox("Show", list(SCOPES), format_func=lambda k: SCOPES[k],
                         index=list(SCOPES).index(scope) if scope in SCOPES else 0)
    S.hw_browse = scope

    chars = list_studied_characters(USER_ID, scope)
    if not chars:
        st.info("Nothing here yet.")
    else:
        sort_by = st.radio(
            "Order", ["Most common first", "Most mistakes first",
                      "Least precise first", "Due soonest"],
            horizontal=True)
        if sort_by == "Most mistakes first":
            chars.sort(key=lambda e: (-e["total_mistakes"], e["rank"] or 10**6))
        elif sort_by == "Least precise first":
            chars.sort(key=lambda e: (e["precision_level"], e["rank"] or 10**6))
        elif sort_by == "Due soonest":
            chars.sort(key=lambda e: (e["next_review_date"] or "9999"))

        st.caption(f"{len(chars)} characters. Tick any to drill them together.")
        st.dataframe(
            [{"": e["character"], "Pinyin": e["pinyin"],
              "Frequency": e["freq_label"], "Precision": f"{e['precision_level']}/10",
              "Reviews": e["review_count"], "Mistakes": e["total_mistakes"],
              "Due": e["next_review_date"] or "-",
              "Meaning": e["gloss"][:60]} for e in chars],
            hide_index=True, width="stretch", height=340)

        labels = {e["character"]: f"{e['character']}  {e['pinyin']}  "
                                  f"({e['gloss'][:28]})" for e in chars}
        picked = st.multiselect("Characters to drill",
                                options=[e["character"] for e in chars],
                                format_func=lambda c: labels.get(c, c))
        c1, c2 = st.columns(2)
        if c1.button(f"✍️ Drill selected ({len(picked)})", type="primary",
                     width="stretch", disabled=not picked):
            session_chars = get_struggle_session(USER_ID, picked)
            if session_chars:
                S.pop("hw_browse", None)
                launch(session_chars, "standard")
        if c2.button(f"🔁 Drill all {len(chars)} in this list",
                     width="stretch", disabled=not chars):
            session_chars = get_struggle_session(
                USER_ID, [e["character"] for e in chars][:60])
            if session_chars:
                S.pop("hw_browse", None)
                launch(session_chars, "standard")

    if st.button("← Back", width="stretch"):
        S.pop("hw_browse", None)
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# SETUP SCREEN
# ----------------------------------------------------------------------
if "hw_payload" not in S:
    st.title("✍️ Handwriting")

    tab_review, tab_weak, tab_focus, tab_mine = st.tabs(
        ["📆 Review", "🎯 Weak characters", "🔍 A word", "📖 My characters"])

    # --- standard review session ---
    with tab_review:
        source = get_handwriting_source(USER_ID)
        picked_source = st.selectbox(
            "Characters from", list(SOURCES), format_func=SOURCES.get,
            index=list(SOURCES).index(source) if source in SOURCES else 0, key="hw_source")
        if picked_source != source:
            set_handwriting_source(USER_ID, picked_source)
            source = picked_source

        if source == "herbs" and not herb_character_counts(USER_ID)["herbs"]:
            st.warning("No herb list loaded yet.")
            st.markdown(
                "Export your Herb Dojo list to "
                "`pinyin-immersion-app/data/herbs.csv` with at least a "
                "**Chinese** column (Pinyin, English and Category are "
                "used if present), then press the button below.")
            if st.button("🔄 Load herbs.csv", width="stretch"):
                added, skipped, err = import_herbs_from_csv()
                if err:
                    st.error(err)
                else:
                    st.success(f"Imported {added} herbs.")
                    st.rerun()
        else:
            due, available = handwriting_due_and_new(USER_ID, source)
            room = min(handwriting_new_allowance(USER_ID, due), available)
            c1, c2 = st.columns(2)
            c1.metric("Due for review", due)
            c2.metric("New today", f"{room} of {HANDWRITING_NEW_PER_DAY}")
            if due and not room and available:
                st.caption("New characters wait while reviews catch up, or until tomorrow.")
            if source == "herbs":
                hc = herb_character_counts(USER_ID)
                if hc.get("tier1_characters"):
                    st.caption(f"{hc['herbs']} herbs · {hc['characters']} characters. Tier-1 "
                               f"herbs alone account for **{hc['tier1_characters']}** characters "
                               f"- the ones worth knowing first.")
                st.caption(
                    "Whole herb names, tier-1 herbs first: you write 麻 then 黃 with 麻黃 "
                    "on screen throughout, so the name sticks rather than two unrelated "
                    "characters. Each card breaks the character into radicals — 艹 marks a "
                    "plant, 木 something woody, 虫 an insect, 石 a mineral.")
            elif source == "frequency":
                st.caption(
                    "Working through the 500 most common characters in frequency order. "
                    "Anything due comes first, then the next new ones. Where no word of "
                    "yours contains a character, its own pinyin and meaning are the cue.")
            else:
                st.caption(
                    "Cue = word, pinyin and meaning — never the character itself. New "
                    "characters run watch → trace → write; reviews go straight to writing. "
                    "Miss a character more than 3× and it comes back later in the session, "
                    "with its next review pulled to tomorrow.")
            if st.button("▶️ Start", type="primary", width="stretch",
                         disabled=(due + room == 0)):
                chars = handwriting_session_for(USER_ID, room, source=source)
                if chars:
                    launch(chars, "standard")
                else:
                    st.success("Nothing due right now.")
            if source == "herbs":
                with st.expander("Reload herb list"):
                    if st.button("🔄 Re-import herbs.csv", width="stretch"):
                        added, skipped, err = import_herbs_from_csv()
                        if err:
                            st.error(err)
                        else:
                            st.success(f"Imported {added} new herbs.")

    # --- weakness drill ---
    with tab_weak:
        st.caption("Characters you've been missing most, worst first "
                   "(ranked by recent mistake rate). Pick any to loop — each "
                   "repeats until you write it clean twice in a row.")
        weak = get_weak_characters(USER_ID, limit=40)
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
                           width="stretch", disabled=not picked):
                chars = get_struggle_session(USER_ID, [weak[i]["character"] for i in picked])
                launch(chars, "struggle")
            if colb.button("🔥 Drill top 10", width="stretch",
                           disabled=len(weak) == 0):
                chars = get_struggle_session(USER_ID, [w["character"] for w in weak[:10]])
                launch(chars, "struggle")

    # --- focus on a word ---
    with tab_focus:
        st.caption("Drill every character in a specific word or phrase, "
                   "regardless of due dates.")
        focus = st.text_input("Word or phrase (hanzi)", "",
                              placeholder="e.g. 巴刹")
        if st.button("Start focus session", width="stretch",
                     disabled=not focus.strip()):
            chars = get_focus_session(USER_ID, focus.strip())
            if chars:
                launch(chars, "standard")
            else:
                st.warning("No Chinese characters found in that text.")

    # --- my characters ---
    with tab_mine:
        if get_handwriting_source(USER_ID) == "frequency":
            cp = get_curriculum_progress(USER_ID)
            _total = cp.get("total", 500) or 500
            _started = cp.get("started", 0)
            st.metric("Of the 500 most common", f"{_started}/{_total}")
            st.progress(min(1.0, _started / _total))
            _cov = cp.get("text_coverage")
            if _cov is not None:
                st.caption(f"Those characters make up ~**{_cov}%** of everything you'll "
                           f"read · {cp.get('mastered', 0)} mastered.")
        hw_stats = get_handwriting_stats(USER_ID)
        total = hw_stats["total_chars_available"]
        st.metric("Characters in your vocab", total)
        if total:
            st.write(f"**✏️ Practised:** {hw_stats['practiced']}")
            st.progress(min(1.0, hw_stats["practiced"] / total))
            st.write(f"**🏆 Mastered:** {hw_stats['mastered']}")
            st.progress(min(1.0, hw_stats["mastered"] / total))
            st.caption("Mastered = review pushed 21+ days out.")
        c1, c2 = st.columns(2)
        if c1.button("View / drill practised", key="browse_practiced", width="stretch"):
            S.hw_browse = "all"
            st.rerun()
        if c2.button("View / drill mastered", key="browse_mastered", width="stretch"):
            S.hw_browse = "mastered"
            st.rerun()

    st.stop()

# ----------------------------------------------------------------------
# ACTIVE DRILL
# ----------------------------------------------------------------------
value = hanzi_drill(session=S.hw_payload, key=f"drill_{S.hw_sid}", default=None)
process_results(value)

mode_label = "struggle loop" if S.hw_payload["mode"] == "struggle" else "review"
st.caption(f"💾 {S.hw_processed} attempts saved · {mode_label}")

if S.get("hw_done"):
    counts = [0, 0, 0, 0]
    for r in S.get("hw_final", []):
        counts[int(r["grade"])] += 1
    st.success(
        f"Session saved — Easy {counts[3]} · Good {counts[2]} · "
        f"Hard {counts[1]} · Again {counts[0]}")
    if tp.active("handwriting"):
        S.hw_plan = True            # a Library session counts if the plan is waiting on it
    in_plan = S.get("hw_plan")
    tp.session_done(USER_ID, "handwriting", S.get("hw_t0"), items=len(S.get("hw_final", [])),
                    step="handwriting" if in_plan else None, once_key="hw_logged")
    if in_plan:
        tp.continue_ui(end_session)
    elif st.button("🔄 New session", type="primary", width="stretch"):
        end_session()
        st.rerun()
else:
    with st.expander("End session early"):
        st.caption("Progress so far is already saved.")
        if st.button("🏁 End now", width="stretch"):
            tp.session_done(USER_ID, "handwriting", S.get("hw_t0"), items=S.get("hw_processed", 0),
                            step="handwriting" if S.get("hw_plan") else None, once_key="hw_logged")
            end_session()
            st.rerun()
