# src/views/12_Penang.py
"""
🏝️ Penang Malay - understanding northern Malay (loghat utara), the everyday
Malay of Penang and Kedah. Recognition only: you learn to follow it, while
everything you say stays standard Malaysian Malay.

Listen: hear a Penang line and pick its meaning, or read one and pick the
standard Malay. Each line is spaced like a word. Words & sounds: the northern
words with their standard partners, and the sound changes that make most of
them guessable (besar -> besaq, kenal -> kenai, panas -> panaih).
"""

import time
from datetime import date

import streamlit as st

import db_manager as db
import session_store as store
import today_plan as tp
import utara as ut
import vocab_engine as ve
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Penang Malay", page_icon="🏝️", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state

SAVED = ("pn_items", "pn_i", "pn_results", "pn_ans", "pn_saved", "pn_logged", "pn_date")


def reset():
    for k in [k for k in S if k.startswith("pn_") and k != "pn_audio"]:
        del S[k]
    store.drop(USER_ID, "penang")


if "pn_items" not in S:
    store.resume(USER_ID, "penang", SAVED, clock="pn_t0")
if "pn_items" in S and S.pn_i < len(S.pn_items):
    store.keep(USER_ID, "penang", SAVED, clock="pn_t0")

progress = db.drill_progress_get(USER_ID, ut.DRILL)
with st.sidebar:
    sidebar_user_badge()
    st.metric("Penang lines met", f"{len(progress)} of {len(ut.SENTENCES)}")
    if "pn_items" in S and st.button("End session"):
        reset()
        st.rerun()

st.title("🏝️ Penang Malay")
st.caption("Northern Malay (loghat utara), as spoken in Penang and Kedah — to understand, not to say.")
store.notice()

known = len(db.introduced_words(USER_ID))
if known < ut.MIN_KNOWN:
    st.info(f"You've met **{known}** words. Penang Malay opens at about {ut.MIN_KNOWN}, "
            "once the standard basics it bends are in place.")
    st.stop()


def play(text):
    cache = S.setdefault("pn_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def new_left():
    return max(0, ut.NEW_PER_DAY - db.drill_new_today(USER_ID, ut.DRILL))


listen, words = st.tabs(["🎧 Listen", "📒 Words & sounds"])

with words:
    st.markdown("**Sound changes** — most northern words are standard words you know")
    for rule, pairs in ut.SOUND_RULES:
        st.markdown(f"- **{rule}**: " + " · ".join(f"{a} → {b}" for a, b in pairs))
    st.markdown("**Northern words**")
    st.dataframe([{"Penang": w, "Standard": s, "English": e} for w, s, e in ut.WORDS],
                 hide_index=True, width="stretch")
    st.caption("The app's voices are standard Malaysian, so the audio gives the words in a "
               "standard accent, not the northern tune.")

with listen:
    if "pn_items" not in S:
        today = date.today().isoformat()
        due = sum(1 for t in progress.values() if (t.get("next_review_date") or "") <= today)
        st.markdown(f"**{due}** lines due · **{len(ut.SENTENCES) - len(progress)}** still new · "
                    f"{new_left()} new allowed today")
        if st.button("▶️ Start", type="primary", width="stretch"):
            items = ut.build_session(progress, date.today(), new_left())
            if not items:
                st.success("Nothing due, and no new lines for today.")
            else:
                reset()
                S.pn_items, S.pn_i, S.pn_results = items, 0, []
                S.pn_t0, S.pn_date = time.time(), date.today().isoformat()
                st.rerun()

    elif S.pn_i >= len(S.pn_items):
        if "pn_saved" not in S:
            for r in S.pn_results:
                track = ve.update_track(progress.get(r["key"], {}), "correct" if r["right"] else "wrong")
                db.drill_progress_save(USER_ID, ut.DRILL, r["key"], track)
            S.pn_saved = True
        tp.session_done(USER_ID, "penang", S.get("pn_t0"), items=len(S.pn_results),
                        once_key="pn_logged")
        store.drop(USER_ID, "penang")
        right = sum(r["right"] for r in S.pn_results)
        st.success(f"Done — {right} of {len(S.pn_results)} right.")
        if st.button("▶️ Another round", type="primary", width="stretch"):
            reset()
            st.rerun()

    else:
        it = S.pn_items[S.pn_i]
        ans = S.get("pn_ans")
        st.progress(S.pn_i / len(S.pn_items), text=f"{S.pn_i + 1} of {len(S.pn_items)}")
        if it["kind"] == "hear":
            play(it["north"])
            if ans is not None:
                st.markdown(f"<div style='font-size:1.8rem'>{it['north']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='font-size:1.8rem'>{it['north']}</div>", unsafe_allow_html=True)
        choice = st.radio(it["question"], it["options"], index=None, key=f"pn_mc_{S.pn_i}",
                          disabled=ans is not None)
        if ans is None:
            if st.button("Check", type="primary", disabled=choice is None):
                right = choice == it["answer"]
                S.pn_results.append({"key": it["key"], "right": right})
                db.log_activity(USER_ID, "listen" if it["kind"] == "hear" else "read",
                                it["north"], 2 if right else 0)
                S.pn_ans = {"right": right}
                st.rerun()
        else:
            st.markdown("✅ Right." if ans["right"] else f"❌ It was **{it['answer']}**")
            st.markdown(f"Standard: **{it['standard']}**  \n_{it['english']}_")
            if it["words"]:
                st.caption("  \n".join(f"{w} = {s} — {e}" for w, s, e in it["words"]))
            if it["kind"] == "read":
                play(it["north"])
            if st.button("Next ▶️", type="primary", width="stretch"):
                S.pn_i += 1
                S.pop("pn_ans", None)
                st.rerun()
