# src/views/11_Level_test.py
"""
🎯 HSK level test - which level to study at, by ear and in characters.

Listening first (hear a word, pick its meaning), then reading (see it in
characters, pick its meaning), each level by level from HSK 1 and stopping
at the first level not passed (see placement.py). About five minutes for a
beginner, fifteen at HSK 4. No feedback on each answer - it's a measure,
not a lesson - and "I don't know" is better than a guess.

The result sets the level grammar (listening) and reading and games
(reading) work at. It can be retaken any time, or set by hand.
"""

import streamlit as st

import db_manager as db
import hsk
import placement as pl
from audio_engine import create_audio_file, warm
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="HSK level test", page_icon="🎯", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
TODAY_PAGE = "views/0_Today.py"

with st.sidebar:
    sidebar_user_badge()

st.title("🎯 HSK level test")


def play(text, autoplay=True):
    cache = S.setdefault("lt_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3", autoplay=autoplay)
    else:
        st.warning("The recording didn't load. Tap “I don't know” to move on.")


def start():
    S.lt = {"queue": list(pl.SKILLS), "test": pl.new_test(next(iter(pl.SKILLS))),
            "passed": {}, "scores": {}}
    S.pop("lt_done", None)


def finish_skill(run):
    test = run["test"]
    skill = test["skill"]
    run["passed"][skill] = test["passed"]
    run["scores"][skill] = pl.score_by_level(test)
    try:
        db.save_placement(USER_ID, skill, test["passed"],
                          {"scores": run["scores"][skill], "log": test["log"]})
    except Exception as e:                     # the result still shows; it just isn't kept
        st.warning(f"Couldn't save the {skill} result: {e}")
    run["queue"].pop(0)
    if run["queue"]:
        run["test"] = pl.new_test(run["queue"][0])
        return
    levels = {k: pl.study_level(v) for k, v in run["passed"].items()}
    try:
        db.set_hsk_levels(USER_ID, levels["listen"], levels["read"], by="test")
    except Exception as e:
        st.warning(f"Couldn't save your levels: {e}")
    S.lt_done = {"passed": run["passed"], "scores": run["scores"], "levels": levels}
    S.pop("lt", None)


# ----------------------------------------------------------------------
# A test in progress
# ----------------------------------------------------------------------
run = S.get("lt")
if run:
    test = run["test"]
    item = pl.current(test)
    if item is None:
        finish_skill(run)
        st.rerun()
    icon, name, how = pl.SKILLS[test["skill"]]
    asked = len(test["answers"])
    st.caption(f"{icon} {name} · HSK {test['level']} · question {asked + 1} · {how}")
    st.progress(min(1.0, (test["level"] - 1 + asked / pl.ITEMS) / len(hsk.LEVELS)))

    with st.container(border=True):
        if test["skill"] == "listen":
            play(item["word"])
            # the rest of this level's words, made while this one is answered
            warm([i["word"] for i in test["items"][asked + 1:asked + 4]])
        else:
            st.markdown(f"<div style='font-size:3rem;text-align:center;line-height:1.4'>"
                        f"{item['word']}</div>", unsafe_allow_html=True)
        for n, option in enumerate(item["options"]):
            if st.button(option, width="stretch", key=f"lt_{test['level']}_{asked}_{n}"):
                pl.answer(test, option)
                st.rerun()
        if st.button("🤷 I don't know", type="tertiary", width="stretch",
                     key=f"lt_{test['level']}_{asked}_dk"):
            pl.answer(test, None)
            st.rerun()

    if st.button("Stop the test", type="tertiary", key="lt_stop"):
        S.pop("lt", None)
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# Just finished
# ----------------------------------------------------------------------
done = S.get("lt_done")
if done:
    st.success(f"🎯 Study at **HSK {done['levels']['listen']}** by ear and "
               f"**HSK {done['levels']['read']}** in characters.")
    for skill, (icon, name, _how) in pl.SKILLS.items():
        passed = done["passed"][skill]
        lines = [f"HSK {lv}: {r}/{n}" for lv, (r, n) in sorted(done["scores"][skill].items())]
        st.markdown(f"{icon} **{name}** — "
                    + (f"passed up to HSK {passed}" if passed else "HSK 1 not passed yet")
                    + "  \n" + " · ".join(lines))
    st.caption(f"A level counts as passed at {pl.PASS} of {pl.ITEMS}. Grammar works at your "
               "listening level; reading and games at your reading level.")
    if st.button("🏠 Back to Today", type="primary", width="stretch"):
        S.pop("lt_done", None)
        st.switch_page(TODAY_PAGE)
    st.stop()


# ----------------------------------------------------------------------
# Start, or set by hand
# ----------------------------------------------------------------------
levels = db.get_hsk_levels(USER_ID)
if levels:
    by = "the level test" if levels.get("by") == "test" else "you"
    st.markdown(f"Now: **HSK {levels['listen']}** by ear · **HSK {levels['read']}** in "
                f"characters — set by {by}, {levels.get('at', '')[:10]}.")
else:
    st.markdown("No level yet. The test takes about five minutes if you're new to a level, "
                "up to fifteen if you know a lot.")

st.markdown("**How it works:** words from each HSK level, four meanings to choose from. "
            "🎧 Listening first, then 👁️ reading. Each level stops as soon as it's clear, "
            "and the test stops at the first level you don't pass. Tap **I don't know** "
            "rather than guess — guesses make the result wrong.")
if st.button("▶️ Start the level test", type="primary", width="stretch"):
    start()
    st.rerun()

with st.expander("Set my level myself"):
    cur = levels or {"listen": 1, "read": 1}
    c1, c2 = st.columns(2)
    listen = c1.selectbox("By ear", hsk.LEVELS, index=cur["listen"] - 1,
                          format_func=lambda lv: f"HSK {lv}")
    read = c2.selectbox("In characters", hsk.LEVELS, index=cur["read"] - 1,
                        format_func=lambda lv: f"HSK {lv}")
    if st.button("Save", width="stretch"):
        db.set_hsk_levels(USER_ID, listen, read, by="you")
        st.rerun()

history = db.placement_history(USER_ID)
if history:
    st.divider()
    st.caption("Past tests")
    for h in history:
        icon, name, _how = pl.SKILLS.get(h["skill"], ("", h["skill"], ""))
        st.caption(f"{h['taken_at']:%d %b %Y} · {icon} {name}: passed up to HSK {h['passed']}"
                   if h["passed"] else f"{h['taken_at']:%d %b %Y} · {icon} {name}: HSK 1 not "
                   "passed")
