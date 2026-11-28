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

On the HSK track two more (hsk_sentences, db_manager):
  • Sentences: official HSK example sentences written from their English and
    pinyin - the characters you can write; the rest filled in. Longer as you
    can write more. A character missed in a sentence comes back tomorrow.
  • Welcome-back check: after AWAY_DAYS without writing, write each started
    character once, 20 at a time; the ones you can't are forgotten - back
    into learning, RELEARN_PER_DAY a day - and the rest keep their progress.
"""

import datetime
import time
import uuid

import streamlit as st

import clock
import db_manager as db
import hsk
import hsk_sentences as hs
import today_plan as tp
from auth import on_hsk_track, require_login, sidebar_user_badge
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
    get_hsk_writing_progress,
)

st.set_page_config(page_title="Handwriting", page_icon="✍️", layout="centered")

USER = require_login()
USER_ID = USER["id"]
S = st.session_state
HSK = on_hsk_track(USER)
SESSION_KEYS = ("hw_payload", "hw_sid", "hw_processed", "hw_done", "hw_final",
                "hw_state_seed", "hw_plan", "hw_t0", "hw_logged", "hw_plan_empty", "hw_day",
                "hw_kind", "hw_sentences", "hw_step")
SOURCES = {
    "vocab": "Characters from my vocabulary",
    "frequency": "500 most common characters",
    "herbs": "本草 Herb names",
}


def end_session():
    for k in SESSION_KEYS:
        S.pop(k, None)


if (S.get("hw_plan") or S.get("hw_plan_empty")) and S.get("hw_day") != clock.today().isoformat():
    end_session()                   # yesterday's plan left open in the tab

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("handwriting", end_session)
    tp.sidebar("write_sentences", end_session)


# ----------------------------------------------------------------------
# RESULT INTAKE — incremental, per-attempt, handles repeated characters
# ----------------------------------------------------------------------
def process_results(value):
    if not value or value.get("session_id") != S.get("hw_sid"):
        return
    results = value.get("results", [])
    done_before = S.hw_processed
    kind = S.get("hw_kind", "chars")
    for r in results[done_before:]:
        ch, grade, mistakes = r["character"], int(r["grade"]), int(r.get("mistakes", 0))
        if kind == "sentence":
            # writing it in a sentence doesn't move its schedule on; not
            # managing it brings its review forward
            if grade == 0:
                db.handwriting_missed_in_sentence(USER_ID, ch)
            db.log_activity(USER_ID, "write", ch, grade, mistakes)
            continue
        # Fetch the character's *current* stored state each time so the
        # recent-grade / recent-mistake windows roll correctly even when a
        # character is drilled several times in one session.
        state = get_char_state(USER_ID, ch) or S.hw_state_seed.get(ch, {})
        if kind == "check":
            db.hw_recheck_result(USER_ID, ch, grade, mistakes, state)
        else:
            update_handwriting_progress(USER_ID, ch, grade, state, mistakes=mistakes)
    S.hw_processed = len(results)
    if value.get("done"):
        S.hw_done = True
        S.hw_final = results
        if kind == "sentence":          # each sentence right or not, for next time
            i = 0
            for sent in S.get("hw_sentences") or []:
                part = results[i:i + sent["n"]]
                i += sent["n"]
                sent["right"] = hs.outcome(part)
                db.record_game_item(USER_ID, hs.FAMILY, sent["zh"], sent["right"])


def launch(chars, mode, in_plan=False, rerun=True, kind="chars", sentences=None, step=None):
    S.hw_kind, S.hw_step = kind, step or ("handwriting" if in_plan else None)
    S.hw_sentences = [{"zh": x["zh"], "en": x["en"], "py": x["py"], "n": x["n"]}
                      for x in sentences or []]
    S.hw_payload = {"session_id": str(uuid.uuid4()), "chars": chars, "mode": mode}
    S.hw_sid = S.hw_payload["session_id"]
    S.hw_processed = 0
    S.hw_done = False
    S.hw_plan, S.hw_t0, S.hw_day = in_plan, time.time(), clock.today().isoformat()
    S.pop("hw_logged", None)
    # seed states so the first grade of each char has its SRS/history context
    S.hw_state_seed = {c["character"]: c for c in chars}
    if rerun:
        st.rerun()


# ----------------------------------------------------------------------
# TODAY'S PLAN: start straight away
# ----------------------------------------------------------------------
if "hw_payload" not in S and tp.active("write_sentences") and not S.get("hw_plan_empty"):
    entries, chosen = db.sentence_writing_session(USER_ID, tp.params("write_sentences").get("n", 2))
    if entries:
        launch(entries, "sentence", in_plan=True, kind="sentence", sentences=chosen,
               step="write_sentences")
    S.hw_plan_empty, S.hw_day = True, clock.today().isoformat()
    tp.session_done(USER_ID, "handwriting", time.time(), step="write_sentences")
    st.success("No sentences to write yet.")
    tp.continue_ui(end_session)
    st.stop()

if "hw_payload" not in S and (tp.active("handwriting") or S.get("hw_plan_empty")):
    if not S.get("hw_plan_empty"):
        p_ = tp.params("handwriting")
        if p_.get("check"):                 # back from a break: the check first
            if not db.hsk_writing_status(USER_ID)["recheck"]:
                db.hw_recheck_start(USER_ID)
            chars = db.hw_recheck_session(USER_ID, p_["check"])
            if chars:
                launch(chars, "check", in_plan=True, kind="check")
        else:
            due, _avail = handwriting_due_and_new(USER_ID)
            new = min(p_.get("new", 0), handwriting_new_allowance(USER_ID, due))
            chars = handwriting_session_for(USER_ID, new, max_reviews=p_.get("reviews"))
            if chars:
                launch(chars, "standard", in_plan=True)
        S.hw_plan_empty, S.hw_day = True, clock.today().isoformat()
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
def hsk_progress_ui(p):
    """The 400 characters to write for HSK 1-4, band by band."""
    st.metric("HSK 1–4 characters started", f"{p['started']} / {p['total']}")
    for band, b in p["bands"].items():
        st.progress(min(1.0, b["started"] / b["total"]) if b["total"] else 0.0,
                    text=f"{hsk.BAND_NAMES[band]} · {b['started']}/{b['total']} started · "
                         f"{b['known']} known")
    st.caption("Known = next review a week or more away. HSK 1–2 comes first, then 3, then "
               "4; within each, the parts of a character before the characters built from "
               "them (女 'woman' before 好 'good' and 妈 'mum').")


if "hw_payload" not in S:
    # herb names stay a separate thing on the HSK track: Play's herb game
    # opens this page in herb mode, with a way back to the HSK characters
    HERBS = HSK and S.get("hw_herbs", False)
    st.title("✍️ Write — herb names" if HERBS else "✍️ Write — HSK 1–4" if HSK
             else "✍️ Handwriting")
    if HERBS and st.button("← Back to HSK 1–4 characters", key="hw_herbs_off"):
        S.hw_herbs = False
        st.rerun()

    status = db.hsk_writing_status(USER_ID) if HSK and not HERBS else {}
    check = status.get("recheck")

    def welcome_back():
        """The check after a break: offered, in progress, or just finished."""
        if check:
            left = len(check["todo"])
            st.info(f"**Welcome-back check** — {left} of {check['total']} characters left · "
                    f"kept {check['kept']} · forgotten {check['forgotten']}. Write each once; "
                    "the ones you can't go back to learning.")
            if st.button(f"✍️ Check the next {min(db.RECHECK_CHUNK, left)}", type="primary",
                         width="stretch", key="hw_check_go"):
                launch(db.hw_recheck_session(USER_ID), "check", kind="check")
        elif status.get("offer"):
            st.info(f"**You haven't written for {status['away']} days.** Check what you still "
                    f"know: write each of the {status['started']} characters you'd started, once, "
                    f"{db.RECHECK_CHUNK} at a time. The ones you can't write go back to learning "
                    f"({db.RELEARN_PER_DAY} a day); the rest keep their progress.")
            c1, c2 = st.columns(2)
            if c1.button("✍️ Start the check", type="primary", width="stretch",
                         key="hw_check_start"):
                db.hw_recheck_start(USER_ID)
                launch(db.hw_recheck_session(USER_ID), "check", kind="check")
            if c2.button("Not now", width="stretch", key="hw_check_skip"):
                db.hw_recheck_dismiss(USER_ID)
                st.rerun()
        elif status.get("last_check") and status["last_check"].get("done", "") >= \
                (clock.today() - datetime.timedelta(days=7)).isoformat():
            lc = status["last_check"]
            st.caption(f"Welcome-back check done: kept {lc['kept']} of {lc['total']}, "
                       f"{lc['forgotten']} back in learning.")

    if HSK and not HERBS:
        welcome_back()
        tab_review, tab_sent, tab_weak, tab_focus, tab_mine = st.tabs(
            ["📆 Review", "📝 Sentences", "🎯 Weak", "🔍 A word", "📖 Mine"])
    else:
        tab_sent = None
        tab_review, tab_weak, tab_focus, tab_mine = st.tabs(
            ["📆 Review", "🎯 Weak characters", "🔍 A word", "📖 My characters"])

    if tab_sent is not None:
        with tab_sent:
            n = status.get("writable", 0)
            lo, hi = hs.tier(n)
            if n < hs.MIN_WRITABLE:
                st.info(f"Sentences start once you can write {hs.MIN_WRITABLE} characters — "
                        f"you can write {n}. (Can write = written at least twice.)")
            else:
                st.caption(f"Official HSK example sentences, written from their English and "
                           f"pinyin. You can write {n} characters, so each sentence asks for "
                           f"{lo}–{hi} of them; any you haven't learnt are filled in. Longer "
                           "sentences come as you can write more. Sentences you get wrong "
                           "come back; a character you miss comes back for review tomorrow.")
                c1, c2 = st.columns(2)
                for col, k in ((c1, 2), (c2, 5)):
                    if col.button(f"✍️ Write {k} sentences", type="primary" if k == 2 else
                                  "secondary", width="stretch", key=f"hw_sent_{k}",
                                  disabled=bool(check)):
                        entries, chosen = db.sentence_writing_session(USER_ID, k)
                        if entries:
                            launch(entries, "sentence", kind="sentence", sentences=chosen)
                        else:
                            st.warning("No sentences fit what you can write yet.")
                if check:
                    st.caption("After the welcome-back check.")

    # --- standard review session ---
    with tab_review:
        source = "herbs" if HERBS else get_handwriting_source(USER_ID)
        if not HSK:                 # the HSK track has one path, no choice
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
            elif source == "hsk":
                p_ = get_hsk_writing_progress(USER_ID)
                nxt_band = (p_["next"] or {}).get("band")
                st.progress(min(1.0, p_["started"] / p_["total"]),
                            text=f"{p_['started']} of {p_['total']} started"
                                 + (f" · now on {hsk.BAND_NAMES[nxt_band]}" if nxt_band else
                                    " · all 400 started"))
                st.caption(
                    "The 400 characters HSK 1–4 asks you to write by hand, in order. The "
                    "cue is an HSK word with the character blanked (＿字 míng zi, "
                    "'name'): write the missing one. New characters run watch → trace → "
                    "write; reviews go straight to writing.")
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
            if check:
                st.caption("New characters and reviews wait until the welcome-back check is "
                           "done (above).")
            if st.button("▶️ Start", type="primary", width="stretch",
                         disabled=(due + room == 0) or bool(check)):
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
        if HSK and not HERBS:
            hsk_progress_ui(get_hsk_writing_progress(USER_ID))
        elif get_handwriting_source(USER_ID) == "frequency":
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
        if not HSK:
            st.metric("Characters in your vocab", total)
        if total and not HSK:
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

mode_label = {"struggle": "struggle loop", "sentence": "sentences",
              "check": "welcome-back check"}.get(S.hw_payload["mode"], "review")
st.caption(f"💾 {S.hw_processed} attempts saved · {mode_label}")

if S.get("hw_done"):
    counts = [0, 0, 0, 0]
    for r in S.get("hw_final", []):
        counts[int(r["grade"])] += 1
    kind = S.get("hw_kind", "chars")
    if kind == "sentence":
        for sent in S.get("hw_sentences") or []:
            st.markdown(("✅ " if sent.get("right") else "❌ ") + f"**{sent['zh']}**  \n"
                        f"{sent['py']} — {sent['en']}")
    elif kind == "check":
        st_ = db.hsk_writing_status(USER_ID)
        c_ = st_["recheck"] or st_["last_check"] or {}
        if c_:
            left = len(c_.get("todo") or [])
            st.success(f"Kept {c_['kept']} · forgotten {c_['forgotten']}"
                       + (f" · {left} still to check" if left else " · check done"))
    else:
        st.success(
            f"Session saved — Easy {counts[3]} · Good {counts[2]} · "
            f"Hard {counts[1]} · Again {counts[0]}")
    if kind == "chars" and tp.active("handwriting") and not (HSK and S.get("hw_herbs")):
        S.hw_plan, S.hw_step = True, "handwriting"   # a Library session counts if the plan
                                    # is waiting on it (herb names don't stand in for the HSK
                                    # characters)
    in_plan = S.get("hw_plan")
    tp.session_done(USER_ID, "handwriting", S.get("hw_t0"), items=len(S.get("hw_final", [])),
                    step=S.get("hw_step") if in_plan else None, once_key="hw_logged")
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
                            step=S.get("hw_step") if S.get("hw_plan") else None,
                            once_key="hw_logged")
            end_session()
            st.rerun()
