# src/views/11_Clinic.py
"""
🩺 Clinic role-play - you're the practitioner, the patient speaks Malay.

Pick a patient. They open with their complaint; you take the history, explain
the treatment, tell them how to lie or breathe, check they're comfortable,
and give advice to take home. Speak each line (or type it). Every line is
graded - correct, close or wrong, with how a Malaysian would say it - and
the patient answers from the facts of their case.

The goal list in the sidebar ticks off as you cover each part of the
consultation; "Stuck?" shows phrases for the next one. A consultation in
progress is saved as you go.
"""

import time

import streamlit as st

import db_manager as db
import roleplay as rp
import session_store as store
import today_plan as tp
import vocab_engine as ve
import word_content as wc
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from malay import normalise
from speech_engine import transcribe_audio

st.set_page_config(page_title="Clinic role-play", page_icon="🩺", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
ICON = {"correct": "✅", "close": "🟡", "wrong": "❌"}

SAVED = ("rp_case", "rp_turns", "rp_met", "rp_over", "rp_logged")


def reset():
    for k in [k for k in S if k.startswith("rp_") and k not in ("rp_audio", "rp_english", "rp_gloss")]:
        del S[k]
    store.drop(USER_ID, "clinic")


if "rp_case" not in S:
    store.resume(USER_ID, "clinic", SAVED, clock="rp_t0")
if "rp_case" in S and not S.get("rp_over"):
    store.keep(USER_ID, "clinic", SAVED, clock="rp_t0")

with st.sidebar:
    sidebar_user_badge()
    st.toggle("Show English", value=True, key="rp_english")
    if "rp_case" in S:
        st.markdown("**The consultation**")
        for g in rp.GOALS:
            st.caption(("✅ " if g["id"] in S.rp_met else "⬜ ") + g["task"])

st.title("🩺 Clinic role-play")
store.notice()


def play(text, voice):
    cache = S.setdefault("rp_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text, voice=voice)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def word_by_word(text):
    cache = S.setdefault("rp_gloss", {})
    toks = [t for t in normalise.tokens(text) if t not in cache]
    if toks:
        try:
            got = db.glosses_for(toks)
        except Exception:
            got = {}
        for t in toks:
            cache[t] = got.get(t, "")
        cache.update({k: v for k, v in got.items() if k not in cache})
    with st.expander("Word by word"):
        for tok, parts, gloss in wc.breakdown(text, cache):
            st.markdown(f"**{tok}**" + (f" · `{parts}`" if parts else "") + (f" — {gloss}" if gloss else ""))


# ----------------------------------------------------------------------
# choosing a patient
# ----------------------------------------------------------------------
if "rp_case" not in S:
    st.write("You're the practitioner and the patient speaks Malay. Take the history, explain "
             "the treatment, position them, check they're comfortable and give advice. "
             "Speak each line, or type it.")
    case = st.selectbox("Patient", rp.CASES, format_func=lambda c: f"{c['title']} — {c['who']}")
    if st.button("▶️ Start the consultation", type="primary", width="stretch"):
        reset()
        S.rp_case, S.rp_met, S.rp_t0 = case["id"], [], time.time()
        S.rp_turns = [{"who": "patient", "malay": case["opening"][0], "english": case["opening"][1]}]
        st.rerun()
    st.stop()


case = rp.BY_CASE[S.rp_case]
turns = S.rp_turns
st.caption(f"{case['title']} · {case['who']} · say **{case['address']}** to them")

# ----------------------------------------------------------------------
# the conversation so far
# ----------------------------------------------------------------------
last_patient = max((i for i, t in enumerate(turns) if t["who"] == "patient"), default=None)
for i, t in enumerate(turns):
    if t["who"] == "patient":
        with st.chat_message("patient", avatar="🧑"):
            st.markdown(f"<div style='font-size:1.3rem'>{t['malay']}</div>", unsafe_allow_html=True)
            if S.get("rp_english", True) and t.get("english"):
                st.caption(t["english"])
            if i == last_patient:
                play(t["malay"], case["voice"])
                word_by_word(t["malay"])
    else:
        with st.chat_message("you", avatar="🩺"):
            st.markdown(f"{ICON.get(t.get('verdict'), '')} {t['malay']}")
            if t.get("feedback"):
                st.caption(t["feedback"])
            if t.get("better") and t.get("verdict") != "correct":
                st.caption(f"Better: **{t['better']}**")

# ----------------------------------------------------------------------
# finished
# ----------------------------------------------------------------------
mine = [t for t in turns if t["who"] == "you"]
if S.get("rp_over") or len(mine) >= rp.MAX_TURNS or len(S.rp_met) == len(rp.GOALS):
    if not S.get("rp_over"):
        S.rp_over = True
    tp.session_done(USER_ID, "clinic", S.get("rp_t0"), items=len(mine), once_key="rp_logged")
    store.drop(USER_ID, "clinic")
    counts, fixes = rp.summary(turns)
    st.success(f"Consultation over — {len(S.rp_met)} of {len(rp.GOALS)} parts covered · "
               f"{counts['correct']} lines right, {counts['close']} close, {counts['wrong']} wrong.")
    missed = [g["task"] for g in rp.GOALS if g["id"] not in S.rp_met]
    if missed:
        st.caption("Not covered this time: " + "; ".join(missed).lower() + ".")
    if fixes:
        st.markdown("**Say it like this next time**")
        for said, better in fixes:
            st.markdown(f"- ~~{said}~~ → **{better}**")
    if st.button("🩺 Another patient", type="primary", width="stretch"):
        reset()
        st.rerun()
    st.stop()

# ----------------------------------------------------------------------
# your turn
# ----------------------------------------------------------------------
goal = rp.next_goal(S.rp_met)
with st.expander("💡 Stuck?" + (f" Next: {goal['task'].lower()}" if goal else "")):
    for g in ([goal] if goal else []) + [x for x in rp.GOALS if x["id"] not in S.rp_met and x is not goal][:2]:
        st.markdown(f"**{g['task']}**")
        for ms, en in g["phrases"]:
            st.markdown(f"- {ms} — _{en}_")

n = len(mine)
mic = st.audio_input("🎙️ Say your line", key=f"rp_mic_{n}")
typed = st.text_input("…or type it", key=f"rp_type_{n}")
c1, c2 = st.columns([3, 1])
if c1.button("Send", type="primary", width="stretch", disabled=not (mic or typed.strip())):
    spoken = mic is not None and not typed.strip()
    said = typed.strip()
    if spoken:
        with st.spinner("Listening…"):
            heard = transcribe_audio(mic.getvalue())
        said = (heard or {}).get("text", "").strip()
    if not said:
        st.warning("Nothing was heard — try again, or type it.")
        st.stop()
    with st.spinner("The patient is thinking…"):
        result = rp.take_turn(case, turns, said, S.rp_met, spoken)
    if result is None:
        st.error("Couldn't reach the language model just now. Your line is still here — "
                 "press Send again in a moment.")
        st.stop()
    turns.append({"who": "you", "malay": said, "verdict": result["verdict"],
                  "feedback": result["feedback"], "better": result["better"], "spoken": spoken})
    if result["patient_malay"]:
        turns.append({"who": "patient", "malay": result["patient_malay"],
                      "english": result["patient_english"]})
    S.rp_met = S.rp_met + [g for g in result["goals_met"] if g not in S.rp_met]
    if result["patient_done"]:
        S.rp_over = True
    db.log_activity(USER_ID, "speak" if spoken else "type", said[:80], ve.GRADES[result["verdict"]])
    st.rerun()
if c2.button("End", help="Finish the consultation here"):
    S.rp_over = True
    st.rerun()
