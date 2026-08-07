# src/pages/5_Together.py
"""
Together - side-by-side progress and nudges.

Both apps read the same database, so each of you can see what the other has
been doing without any messaging service in between.

A deliberate design choice: this compares EFFORT, not lifetime totals.
One of you has months of head start, so a raw leaderboard would be
permanently discouraging for one and meaningless for the other. What's
shown instead is this week's cards, streaks, consistency and accuracy -
things either person can win on any given day.
"""

import streamlit as st

import db_manager as db
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Together", page_icon="🏆", layout="centered")

USER = require_login()
USER_ID = USER["id"]

with st.sidebar:
    sidebar_user_badge()

st.title("🏆 Together")

others = db.other_users(USER_ID)
if not others:
    st.info("No one else is set up on this database yet.")
    st.stop()
other = others[0]
OTHER_ID = other["id"]

# ----------------------------------------------------------------------
# NUDGES WAITING FOR YOU
# ----------------------------------------------------------------------
pending = db.unseen_nudges(USER_ID)
if pending:
    for n in pending:
        st.success(f"💬 **{n['display_name']}**: {n['message']}")
    if st.button("Got it", use_container_width=True):
        db.mark_nudges_seen(USER_ID)
        st.rerun()
    st.markdown("---")

# ----------------------------------------------------------------------
# THIS WEEK, SIDE BY SIDE
# ----------------------------------------------------------------------
me = db.activity_totals(USER_ID)
them = db.activity_totals(OTHER_ID)
my_streak = db.activity_streak(USER_ID)
their_streak = db.activity_streak(OTHER_ID)

st.subheader("This week")
c1, c2 = st.columns(2)
for col, name, tot, streak in (
        (c1, USER["display_name"], me, my_streak),
        (c2, other["display_name"], them, their_streak)):
    with col:
        st.markdown(f"### {name}")
        st.metric("Cards this week", tot["week_total"],
                  delta=f"{tot['today']} today")
        st.metric("Day streak", f"{streak} 🔥" if streak else "0")
        if tot["accuracy"] is not None:
            st.metric("Accuracy", f"{tot['accuracy']}%")

lead = me["week_total"] - them["week_total"]
if lead > 0:
    st.info(f"You're ahead by **{lead}** cards this week.")
elif lead < 0:
    st.warning(f"{other['display_name']} is ahead by **{abs(lead)}** cards "
               f"this week.")
else:
    st.info("Dead level this week.")

# ----------------------------------------------------------------------
# BY SKILL
# ----------------------------------------------------------------------
st.markdown("---")
st.subheader("By skill, last 7 days")
rows = []
for key, label in db.ACTIVITY_KINDS.items():
    rows.append({
        "Skill": label,
        USER["display_name"]: me["by_kind"].get(key, 0),
        other["display_name"]: them["by_kind"].get(key, 0),
    })
st.dataframe(rows, hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------
# THE WRITING RACE
# ----------------------------------------------------------------------
st.markdown("---")
st.subheader("✍️ The 500 characters")
try:
    mine = db.get_curriculum_progress(USER_ID)
    theirs = db.get_curriculum_progress(OTHER_ID)
    c1, c2 = st.columns(2)
    for col, name, cp in ((c1, USER["display_name"], mine),
                          (c2, other["display_name"], theirs)):
        with col:
            st.markdown(f"**{name}**")
            _tot = cp.get("total", 500) or 500
            _st = cp.get("started", cp.get("furthest_rank", 0))
            st.progress(min(1.0, _st / _tot))
            _c = cp.get("text_coverage")
            st.caption(f"{_st}/{_tot} characters"
                       + (f" - ~{_c}% of running text" if _c is not None else ""))
    st.caption("Counts every one of the 500 most common characters either "
               "of you has practised, and what share of ordinary written "
               "Chinese those characters account for.")
except Exception:
    st.caption("Curriculum progress unavailable.")

# ----------------------------------------------------------------------
# ACTIVITY OVER TIME
# ----------------------------------------------------------------------
st.markdown("---")
st.subheader("Last 14 days")
my_series = db.daily_series(USER_ID, 14)
their_series = db.daily_series(OTHER_ID, 14)
chart = {
    "day": [d.strftime("%d %b") for d, _ in my_series],
    USER["display_name"]: [n for _, n in my_series],
    other["display_name"]: [n for _, n in their_series],
}
st.line_chart(chart, x="day", use_container_width=True)

# ----------------------------------------------------------------------
# SEND A NUDGE
# ----------------------------------------------------------------------
st.markdown("---")
st.subheader(f"💬 Send {other['display_name']} a nudge")
PRESETS = [
    "加油! Your turn.",
    f"I did {me['today']} cards today. Beat that.",
    "Streak's looking shaky...",
    "Handwriting race? First to 100 characters.",
    "Well done - you're ahead of me this week!",
]
choice = st.selectbox("Quick message", PRESETS + ["Write my own..."])
message = choice
if choice == "Write my own...":
    message = st.text_input("Your message", max_chars=280)
if st.button("Send", type="primary", use_container_width=True,
             disabled=not message or message == "Write my own..."):
    db.send_nudge(USER_ID, OTHER_ID, message)
    st.success(f"Sent to {other['display_name']}. She'll see it next time "
               f"she opens the app.")

# ----------------------------------------------------------------------
# RECENT ACTIVITY FEED
# ----------------------------------------------------------------------
st.markdown("---")
with st.expander("Recent activity"):
    feed = db.recent_activity(limit=15)
    if not feed:
        st.caption("Nothing logged yet.")
    for f in feed:
        label = db.ACTIVITY_KINDS.get(f["kind"], f["kind"])
        st.write(f"**{f['display_name']}** - {f['n']} {label.lower()} cards "
                 f"on {f['day'].strftime('%d %b')}")
