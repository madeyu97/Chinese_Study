# src/views/0_Today.py
"""
🏠 Today - two study sessions of about 25 minutes: morning and
evening. The next session is shown in full with one Start
button; the others are a line each. A session that isn't due yet says when
it opens, and can still be started early or skipped.
"""

import streamlit as st

import ahead
import clock
import db_manager as db
import today_plan as tp
import hsk
from auth import on_hsk_track, require_login, sidebar_user_badge
from config import SESSION_GAP_HOURS

st.set_page_config(page_title="Today", page_icon="🏠", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
HSK = on_hsk_track(USER)
LEVEL_TEST_PAGE = "views/11_Level_test.py"

with st.sidebar:
    sidebar_user_badge()

st.title("今天 Today")

# Everything the page shows is read at the same time (the database is far
# from the app, so each read in a row would be its own wait).
with st.spinner("Working out today's sessions…"):
    state, (pending, streak, week) = tp.gather_state(USER_ID, also=[
        lambda: db.unseen_nudges(USER_ID),
        lambda: db.activity_streak(USER_ID),
        lambda: db.study_minutes(USER_ID, 7)], hsk_track=HSK)
levels = state.get("hsk_levels")

if HSK:
    if levels:
        st.caption(f"🎯 Studying **HSK {levels['listen']}** by ear · "
                   f"**HSK {levels['read']}** in characters · "
                   f"grammar up to **HSK {hsk.grammar_upto(levels)}**")
    else:
        with st.container(border=True):
            st.markdown("🎯 **Find your HSK level first** — about five minutes. Grammar, "
                        "reading and games then start at the right level.")
            if st.button("Take the level test", type="primary", width="stretch",
                         key="tp_level"):
                st.switch_page(LEVEL_TEST_PAGE)

# A nudge from the other person shows the moment you open the app.
if pending:
    for n in pending:
        st.info(f"💬 **{n['display_name']}**: {n['message']}")
    if st.button("Got it 👍", key="ack_nudges"):
        db.mark_nudges_seen(USER_ID)
        st.rerun()

bits = []
if streak:
    bits.append(f"🔥 {streak}-day streak")
if week and week["sessions"]:
    bits.append(f"{week['sessions']} of {tp.SESSIONS_PER_WEEK} sessions this week")
if week and week["total"]:
    bits.append(f"{week['total']} min")
if bits:
    st.caption(" · ".join(bits))

# steps finished or skipped earlier in this visit count as done too
cur = tp.plan()
if cur:
    state["done"] = set(state["done"]) | {f"{cur['slot']}:{k}" for k in cur["done"] + cur["skipped"]}
day = tp.build_day(state, hsk_track=HSK)
ahead.for_day(USER_ID, day)        # write later steps' grammar drills now, in the background
nxt = tp.next_session(day)
now = clock.now()


def at(moment):
    return moment.astimezone(clock.tz()).strftime("%H:%M")


def step_line(n, s_):
    skipped = cur and cur["slot"] == s_["slot"] and s_["key"] in cur["skipped"]
    mark = "⏭️" if skipped else "✅" if s_["done"] else f"**{n}.**"
    detail = "skipped" if skipped else "done" if s_["done"] else s_["detail"]
    st.markdown(f"{mark} {s_['icon']} **{s_['title']}** — {detail}")


if HSK:
    st.caption("Two sessions a day. Splitting it is the point: what you learn in the morning "
               "comes back in the evening, hours later, when remembering it takes real effort.")
else:
    st.caption("Two sessions a day. Splitting it is the point: the morning's new words come "
               "back in the evening, hours later, when remembering them takes real effort.")

for sess in day:
    head = f"{sess['icon']} **{sess['title']}** · {sess['theme']}"
    if sess is nxt:
        with st.container(border=True):
            opens = tp.opens_at(sess["slot"], clock.today(), tp.last_finished(day))
            began = cur and cur["slot"] == sess["slot"] and (cur["done"] or cur["skipped"])
            began = began or any(s_["done"] for s_ in sess["steps"])
            st.markdown(f"{head} · about {sess['minutes']} min")
            st.caption(sess["why"])
            for n, s_ in enumerate(sess["steps"], 1):
                step_line(n, s_)
            first = next(s_ for s_ in sess["steps"] if not s_["done"])
            label = (f"▶️ Continue: {first['icon']} {first['title']}" if began
                     else f"▶️ Start the {sess['title'].lower()} session")
            if opens <= now or began:
                if st.button(label, type="primary", width="stretch", key="tp_start"):
                    tp.start(sess)
                    st.switch_page(first["page"])
            else:
                st.info(f"Best from **{at(opens)}**: a gap of at least {SESSION_GAP_HOURS} hours "
                        f"is what makes this session a real test of memory.")
                if st.button("Start now anyway", width="stretch", key="tp_start"):
                    tp.start(sess)
                    st.switch_page(first["page"])
            if not began and st.button(f"Skip the {sess['title'].lower()} session today",
                                       type="tertiary", key="tp_skip_session"):
                db.mark_session_complete(USER_ID, sess["slot"], skipped=True)
                S.pop("tp", None)
                st.rerun()
    elif sess["done"]:
        if sess["skipped"]:
            st.markdown(f"⏭️ {head} — skipped")
        elif sess["finished_at"]:
            st.markdown(f"✅ {head} — done at {at(sess['finished_at'])}")
        else:
            st.markdown(f"✅ {head} — nothing to do")
    else:
        opens = tp.opens_at(sess["slot"], clock.today())
        prev = tp.SESSIONS[tp.SLOTS[tp.SLOTS.index(sess["slot"]) - 1]][1].lower()
        when = f"from {at(opens)}" if opens > now else f"after the {prev} session"
        st.markdown(f"{head} — {when} · "
                    + " · ".join(f"{s_['icon']} {s_['title']}" for s_ in sess["steps"]))

if nxt is None:
    if any(s_["skipped"] for s_ in day):
        st.success("That's today done. Anything more is a bonus.")
    elif any(s_["finished_at"] for s_ in day):
        db.mark_plan_complete(USER_ID)
        st.success("🎉 All of today's sessions are done. Anything more is a bonus.")
    else:
        st.success("Nothing is due today and there's nothing new to start. Enjoy the day — "
                   "or play a game below.")

st.divider()
st.subheader("🎮 Play instead of scrolling")
st.caption("Picture games with your words — five minutes here beats five minutes of the feed, "
           "and every round still links a word to its meaning.")
if st.button("🎮 Play a game", width="stretch", key="tp_play"):
    st.switch_page(tp.GAMES_PAGE)
if HSK:
    st.caption("Want something specific? Writing, grammar and reading are under **Study** "
               "in the menu.")
else:
    st.caption("Want something specific? Words, grammar, reading and the rest are in the "
               "**Library** in the menu.")
