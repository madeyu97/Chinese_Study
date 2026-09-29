# src/pages/0_Today.py
"""
🏠 Today - the day's plan, built from everything that's due, with one Start
button. The only choices here are about the day, not the method: a full or
a short day, or a game instead of scrolling.
"""

import streamlit as st

import db_manager as db
import today_plan as tp
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Today", page_icon="🏠", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state

with st.sidebar:
    sidebar_user_badge()

st.title("今天 Today")

# A nudge from the other person shows the moment you open the app.
try:
    pending = db.unseen_nudges(USER_ID)
    if pending:
        for n in pending:
            st.info(f"💬 **{n['display_name']}**: {n['message']}")
        if st.button("Got it 👍", key="ack_nudges"):
            db.mark_nudges_seen(USER_ID)
            st.rerun()
except Exception:
    pass

try:
    streak = db.activity_streak(USER_ID)
    week = db.study_minutes(USER_ID, 7)
    bits = []
    if streak:
        bits.append(f"🔥 {streak}-day streak")
    if week["total"]:
        bits.append(f"{week['total']} min this week")
    if week["plan_days"]:
        bits.append(f"plan done {week['plan_days']} of the last 7 days")
    if bits:
        st.caption(" · ".join(bits))
except Exception:
    pass

LENGTHS = {"full": "Full day", "short": "Short day (~10 min)"}
_was_short = bool((tp.plan() or {}).get("short"))
length = st.radio("How much today?", list(LENGTHS), format_func=LENGTHS.get,
                  index=1 if _was_short else 0, horizontal=True, key="tp_length",
                  label_visibility="collapsed")
short = length == "short"

with st.spinner("Working out today's plan…"):
    state = tp.gather_state(USER_ID)
# steps finished or skipped earlier in this visit count as done too
cur = tp.plan()
if cur:
    state["done"] = set(state["done"]) | set(cur["done"]) | set(cur["skipped"])
steps = tp.build_plan(state, short=short)

if not steps:
    st.success("Nothing is due today and there's nothing new to start. Enjoy the day — "
               "or play a game below.")
else:
    for n, s in enumerate(steps, 1):
        skipped = cur and s["key"] in cur["skipped"]
        mark = "⏭️" if skipped else "✅" if s["done"] else f"**{n}.**"
        detail = "skipped" if skipped else "done" if s["done"] else s["detail"]
        st.markdown(f"{mark} {s['icon']} **{s['title']}** — {detail}")
    left = tp.minutes_left(steps)
    nxt = tp.next_step(steps)
    if nxt:
        began = bool(cur and (cur["done"] or cur["skipped"])) or any(s["done"] for s in steps)
        label = (f"▶️ Continue: {nxt['icon']} {nxt['title']}" if began else "▶️ Start") \
            + f"  ·  about {left} min"
        if st.button(label, type="primary", width="stretch", key="tp_start"):
            tp.start(steps, short)
            st.switch_page(nxt["page"])
        st.caption("Reviews come first while you're fresh; new words, tones and grammar are "
                   "capped so tomorrow's reviews stay manageable; the day ends with listening "
                   "and speaking. A short day still counts.")
    else:
        db.mark_plan_complete(USER_ID)
        st.success("🎉 Today's plan is done. Anything more is a bonus.")

st.divider()
st.subheader("🎮 Play instead of scrolling")
st.caption("Picture games with your words — five minutes here beats five minutes of the feed, "
           "and every round still links a word to its meaning.")
if st.button("🎮 Play a game", width="stretch", key="tp_play"):
    st.switch_page(tp.GAMES_PAGE)
st.caption("Want something specific? Words, grammar, reading and the rest are in the "
           "**Library** in the menu.")
