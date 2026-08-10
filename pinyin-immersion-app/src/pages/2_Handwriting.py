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

from auth import require_login, sidebar_user_badge
from hanzi_component import hanzi_drill
from db_manager import (
    get_herb_session,
    herb_character_counts,
    import_herbs_from_csv,
    list_studied_characters,
    get_curriculum_session,
    get_curriculum_progress,
    get_handwriting_source,
    set_handwriting_source,
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

USER = require_login()
USER_ID = USER["id"]

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
with st.sidebar:
    sidebar_user_badge()
    st.header("✍️ Handwriting")

    _SOURCES = {
        "frequency": "500 most common characters",
        "vocab": "Characters from my vocabulary",
        "herbs": "本草 Herb names",
    }
    _src = get_handwriting_source(USER_ID)
    _pick = st.radio("Character source", options=list(_SOURCES),
                     index=list(_SOURCES).index(_src) if _src in _SOURCES else 1,
                     format_func=lambda k: _SOURCES[k], key="hw_source")
    if _pick != _src:
        set_handwriting_source(USER_ID, _pick)
        for k in ("hw_payload", "hw_sid", "hw_processed", "hw_done",
                  "hw_final", "hw_state_seed"):
            st.session_state.pop(k, None)
        st.rerun()

    if _pick == "frequency":
        cp = get_curriculum_progress(USER_ID)
        # Read defensively: a page and its data layer can briefly disagree
        # after a partial deploy, and a missing key should degrade the
        # display rather than take the whole page down.
        _total = cp.get("total", 500) or 500
        _started = cp.get("started", 0)
        _mastered = cp.get("mastered", 0)
        st.metric("Characters studied", f"{_started}/{_total}")
        st.progress(min(1.0, _started / _total))
        _cov = cp.get("text_coverage")
        _mcov = cp.get("mastered_coverage")
        _line = ""
        if _cov is not None:
            _line = (f"Those characters make up ~**{_cov}%** of everything "
                     f"you'll read. ")
        _line += f"{_mastered} mastered"
        _line += f" (~{_mcov}%)." if _mcov is not None else "."
        st.caption(_line)
        _in_order = cp.get("in_order")
        if _in_order is not None and _in_order < _started:
            st.caption(f"Working strictly in order, you're at #{_in_order} "
                       f"- the rest came from vocabulary practice.")
        st.markdown("---")
    hw_stats = get_handwriting_stats(USER_ID)
    total = hw_stats["total_chars_available"]
    st.metric("Characters in your vocab", total)
    if total:
        st.write(f"**✏️ Practiced:** {hw_stats['practiced']}")
        st.progress(min(1.0, hw_stats["practiced"] / total))
        if st.button("View / drill these", key="browse_practiced",
                     use_container_width=True):
            st.session_state.hw_browse = "all"
            st.rerun()
        st.write(f"**🏆 Mastered:** {hw_stats['mastered']}")
        st.progress(min(1.0, hw_stats["mastered"] / total))
        if st.button("View / drill these", key="browse_mastered",
                     use_container_width=True):
            st.session_state.hw_browse = "mastered"
            st.rerun()
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
        state = get_char_state(USER_ID, ch) or st.session_state.hw_state_seed.get(ch, {})
        update_handwriting_progress(
            USER_ID, ch, int(r["grade"]), state, mistakes=int(r.get("mistakes", 0)))
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


def _review_from_vocab():
    """Session built from characters in the words you've studied."""
    due, new_available = get_handwriting_counts(USER_ID)
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
        chars = get_handwriting_session(USER_ID, new_count=new_count)
        if chars:
            launch(chars, "standard")
        else:
            st.info("Nothing to drill yet — study some vocabulary first.")



# ----------------------------------------------------------------------
# CHARACTER BROWSER - reached by clicking a sidebar counter
# ----------------------------------------------------------------------
if st.session_state.get("hw_browse") and "hw_payload" not in st.session_state:
    SCOPES = {
        "all": "Everything I've practised",
        "learning": "Still learning",
        "mastered": "Mastered",
        "due": "Due for review",
        "weak": "Giving me trouble",
    }
    scope = st.session_state.hw_browse
    st.title("📖 My characters")

    scope = st.selectbox("Show", list(SCOPES), format_func=lambda k: SCOPES[k],
                         index=list(SCOPES).index(scope)
                         if scope in SCOPES else 0)
    st.session_state.hw_browse = scope

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
            hide_index=True, use_container_width=True, height=340)

        labels = {e["character"]: f"{e['character']}  {e['pinyin']}  "
                                  f"({e['gloss'][:28]})" for e in chars}
        picked = st.multiselect("Characters to drill",
                                options=[e["character"] for e in chars],
                                format_func=lambda c: labels.get(c, c))
        c1, c2 = st.columns(2)
        if c1.button(f"✍️ Drill selected ({len(picked)})", type="primary",
                     use_container_width=True, disabled=not picked):
            session_chars = get_struggle_session(USER_ID, picked)
            if session_chars:
                st.session_state.pop("hw_browse", None)
                launch(session_chars, "standard")
        if c2.button(f"🔁 Drill all {len(chars)} in this list",
                     use_container_width=True, disabled=not chars):
            session_chars = get_struggle_session(
                USER_ID, [e["character"] for e in chars][:60])
            if session_chars:
                st.session_state.pop("hw_browse", None)
                launch(session_chars, "standard")

    if st.button("← Back", use_container_width=True):
        st.session_state.pop("hw_browse", None)
        st.rerun()
    st.stop()

# ----------------------------------------------------------------------
# SETUP SCREEN
# ----------------------------------------------------------------------
if "hw_payload" not in st.session_state:
    st.title("✍️ Handwriting Drill")

    tab_review, tab_weak, tab_focus = st.tabs(
        ["📆 Review session", "🎯 Drill weak characters", "🔍 Focus on a word"])

    # --- standard review session ---
    with tab_review:
        _source = get_handwriting_source(USER_ID)

        # ---- 本草 herb characters ----
        if _source == "herbs":
            hc = herb_character_counts(USER_ID)
            if not hc["herbs"]:
                st.warning("No herb list loaded yet.")
                st.markdown(
                    "Export your Herb Dojo list to "
                    "`pinyin-immersion-app/data/herbs.csv` with at least a "
                    "**Chinese** column (Pinyin, English and Category are "
                    "used if present), then press the button below.")
                if st.button("🔄 Load herbs.csv", use_container_width=True):
                    added, skipped, err = import_herbs_from_csv()
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Imported {added} herbs.")
                        st.rerun()
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Herbs", hc["herbs"])
                c2.metric("Characters", hc["characters"])
                c3.metric("Due", hc["due"])
                if hc.get("tier1_characters"):
                    st.caption(f"Tier-1 herbs alone account for "
                               f"**{hc['tier1_characters']}** characters - "
                               f"the ones worth knowing first.")
                new_count = st.slider("New herbs this session", 0, 12, 4,
                                      key="herb_new")
                st.caption(
                    "Whole herb names, tier-1 herbs first: you write 麻 then "
                    "黃 with 麻黃 on screen throughout, so the name sticks "
                    "rather than two unrelated characters. "
                    "Each card shows the herb it comes from and breaks the "
                    "character into radicals — which for herbs is unusually "
                    "informative: 艹 marks a plant, 木 something woody, "
                    "虫 an insect, 石 a mineral.")
                if st.button("▶️ Start herb session", type="primary",
                             use_container_width=True):
                    chars = get_herb_session(USER_ID, new_count=new_count)
                    if chars:
                        launch(chars, "standard")
                    else:
                        st.success("Nothing due right now.")
                with st.expander("Reload herb list"):
                    if st.button("🔄 Re-import herbs.csv",
                                 use_container_width=True):
                        added, skipped, err = import_herbs_from_csv()
                        if err:
                            st.error(err)
                        else:
                            st.success(f"Imported {added} new herbs.")

        # ---- 500 most common characters ----
        elif _source == "frequency":
            cp = get_curriculum_progress(USER_ID)
            preview = get_curriculum_session(USER_ID, new_count=0)
            c1, c2 = st.columns(2)
            c1.metric("Due for review", len(preview))
            c2.metric("Not yet started",
                      cp.get("total", 500) - cp.get("started", 0))
            new_count = st.slider("New characters this session", 0, 15, 5,
                                  key="freq_new")
            st.caption(
                "Working through the 500 most common characters in frequency "
                "order. Anything due comes first, then the next new ones. "
                "Where no word of yours contains a character, its own pinyin "
                "and meaning are used as the cue.")
            if st.button("▶️ Start review", type="primary",
                         use_container_width=True):
                chars = get_curriculum_session(USER_ID, new_count=new_count)
                if chars:
                    launch(chars, "standard")
                else:
                    st.success("Nothing due, and the curriculum is complete!")

        # ---- characters from my vocabulary ----
        else:
            _review_from_vocab()

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
                           use_container_width=True, disabled=not picked):
                chars = get_struggle_session(USER_ID, [weak[i]["character"] for i in picked])
                launch(chars, "struggle")
            if colb.button("🔥 Drill top 10", use_container_width=True,
                           disabled=len(weak) == 0):
                chars = get_struggle_session(USER_ID, [w["character"] for w in weak[:10]])
                launch(chars, "struggle")

    # --- focus on a word ---
    with tab_focus:
        st.caption("Drill every character in a specific word or phrase, "
                   "regardless of due dates.")
        focus = st.text_input("Word or phrase (hanzi)", "",
                              placeholder="e.g. 巴刹")
        if st.button("Start focus session", use_container_width=True,
                     disabled=not focus.strip()):
            chars = get_focus_session(USER_ID, focus.strip())
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
