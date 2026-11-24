# src/views/11_Level_test.py
"""
🎯 HSK level test - which level to study at, by ear and in characters.

Listening first (hear a word, pick its meaning), then reading (see it in
characters, pick its meaning), then grammar (put an official HSK sentence's
words in order), each level by level from HSK 1 and stopping at the first
level not passed (see placement.py). About five minutes for a
beginner, fifteen at HSK 4. No feedback on each answer - it's a measure,
not a lesson - and "I don't know" is better than a guess.

The result sets the levels grammar, reading and games work at. It can be
retaken any time (grammar on its own too), or set by hand.
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


def start(skills=None):
    skills = list(skills or pl.SKILLS)
    S.lt = {"queue": skills, "test": pl.new_test(skills[0]), "passed": {}, "scores": {}}
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
    # a grammar-only test keeps the listening and reading levels already set
    before = db.get_hsk_levels(USER_ID) or {}
    levels = {"listen": before.get("listen", 1), "read": before.get("read", 1),
              **({"grammar": before["grammar"]} if "grammar" in before else {}), **levels}
    try:
        db.set_hsk_levels(USER_ID, levels["listen"], levels["read"], by="test",
                          grammar=levels.get("grammar"))
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
    per_level, _need = pl.size(test["skill"])
    st.caption(f"{icon} {name} · HSK {test['level']} · question {asked + 1} · {how}")
    st.progress(min(1.0, (test["level"] - 1 + asked / per_level) / len(hsk.LEVELS)))

    if test["skill"] == "grammar":
        # tap the tiles into order: the sentence that says the English
        qkey = f"lt_g_{test['level']}_{asked}"
        picked = S.setdefault("lt_pick", {}).setdefault(qkey, [])
        with st.container(border=True):
            st.markdown(f"**{item['english']}**")
            built = [item["tiles"][i] for i in picked]
            st.markdown(f"<div style='font-size:1.8rem;line-height:1.5;min-height:2.8rem'>"
                        f"{' '.join(built) or '…'}</div>", unsafe_allow_html=True)
            left = [i for i in range(len(item["tiles"])) if i not in picked]
            cols = st.columns(min(4, max(1, len(left))))
            for n, i in enumerate(left):
                tile = item["tiles"][i]
                label = f"{tile}  \n{item['pinyin'].get(tile, '')}"
                if cols[n % len(cols)].button(label, key=f"{qkey}_t{i}", width="stretch"):
                    picked.append(i)
                    st.rerun()
            c1, c2, c3 = st.columns(3)
            if c1.button("↩️ Undo", disabled=not picked, key=f"{qkey}_undo", width="stretch"):
                picked.pop()
                st.rerun()
            if c2.button("🤷 I don't know", key=f"{qkey}_dk", width="stretch"):
                pl.answer(test, None)
                st.rerun()
            if not left and c3.button("Next ▶️", type="primary", key=f"{qkey}_ok",
                                      width="stretch"):
                pl.answer(test, built)
                st.rerun()
        if st.button("Stop the test", type="tertiary", key="lt_stop"):
            S.pop("lt", None)
            st.rerun()
        st.stop()

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
    lv = done["levels"]
    st.success(f"🎯 Study at **HSK {lv['listen']}** by ear, **HSK {lv['read']}** in "
               f"characters" + (f" and **HSK {lv['grammar']}** in grammar" if "grammar" in lv
                                else "") + ".")
    for skill, (icon, name, _how) in pl.SKILLS.items():
        if skill not in done["passed"]:
            continue
        passed = done["passed"][skill]
        lines = [f"HSK {l_}: {r}/{n}" for l_, (r, n) in sorted(done["scores"][skill].items())]
        st.markdown(f"{icon} **{name}** — "
                    + (f"passed up to HSK {passed}" if passed else "HSK 1 not passed yet")
                    + "  \n" + " · ".join(lines))
    st.caption(f"A level counts as passed at {pl.PASS} of {pl.ITEMS} words, or "
               f"{pl.GRAMMAR_PASS} of {pl.GRAMMAR_ITEMS} sentences. Grammar drills go up to your "
               "grammar level, built from the words of your listening level; reading and games "
               "work at your reading level.")
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
                f"characters · **HSK {hsk.grammar_upto(levels)}** in grammar"
                + ("" if "grammar" in levels else " (from listening — not tested yet)")
                + f" — set by {by}, {levels.get('at', '')[:10]}.")
else:
    st.markdown("No level yet. The test takes about five minutes if you're new to a level, "
                "up to fifteen if you know a lot.")

st.markdown("**How it works:** 🎧 listening and 👁️ reading — words from each HSK level, "
            "four meanings to choose from — then 🧩 grammar: an official HSK sentence's "
            "words as tiles, to put in order. Each level stops as soon as it's clear, and "
            "each part stops at the first level you don't pass. Tap **I don't know** rather "
            "than guess — guesses make the result wrong.")
if st.button("▶️ Start the level test", type="primary", width="stretch"):
    start()
    st.rerun()
if levels and st.button("🧩 Test grammar only", width="stretch"):
    start(["grammar"])
    st.rerun()

with st.expander("Set my level myself"):
    cur = levels or {"listen": 1, "read": 1}
    c1, c2, c3 = st.columns(3)
    listen = c1.selectbox("By ear", hsk.LEVELS, index=cur["listen"] - 1,
                          format_func=lambda lv: f"HSK {lv}")
    read = c2.selectbox("In characters", hsk.LEVELS, index=cur["read"] - 1,
                        format_func=lambda lv: f"HSK {lv}")
    grammar = c3.selectbox("Grammar", hsk.LEVELS, index=hsk.grammar_upto(cur) - 1,
                           format_func=lambda lv: f"HSK {lv}")
    if st.button("Save", width="stretch"):
        db.set_hsk_levels(USER_ID, listen, read, by="you", grammar=grammar)
        st.rerun()

st.divider()
st.markdown("**📚 Anki**")
anki = db.get_anki_words(USER_ID)
st.caption("Grammar drills are built from words you know. Say roughly how many HSK words "
           "you've learnt in Anki (HSK 1 is 300 words, 1–2 is 500, 1–3 is 1,000, 1–4 is "
           "2,000), and update it now and then.")
c1, c2 = st.columns([2, 1])
n = c1.number_input("HSK words learnt in Anki", 0, 2000, value=anki or 0, step=50)
if c2.button("Save", key="anki_save", width="stretch"):
    db.set_anki_words(USER_ID, n)
    st.rerun()
if anki:
    st.caption(f"{anki:,} words cover {len(hsk.recognised_chars(anki)):,} of the "
               f"{len(hsk.recognise_chars(4)):,} characters HSK 1–4 asks you to recognise.")

history = db.placement_history(USER_ID)
if history:
    st.divider()
    st.caption("Past tests")
    for h in history:
        icon, name, _how = pl.SKILLS.get(h["skill"], ("", h["skill"], ""))
        st.caption(f"{h['taken_at']:%d %b %Y} · {icon} {name}: passed up to HSK {h['passed']}"
                   if h["passed"] else f"{h['taken_at']:%d %b %Y} · {icon} {name}: HSK 1 not "
                   "passed")
