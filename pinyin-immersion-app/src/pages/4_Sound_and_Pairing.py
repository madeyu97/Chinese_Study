# src/pages/4_Sound_and_Pairing.py
"""
🔊 Sound & Pairing - tone discrimination and character-to-word association,
built only from words you've already been introduced to.

Tones: characters grouped by syllable (香 xiāng · 想 xiǎng · 像 xiàng), always
shown with a real word they appear in. Hear one and pick it; see one in its
word and pick its tone, then say it and compare with the model.

Pairings: characters that form several of your words (想 → 想要 · 想法 ·
想念). Pick the word for a meaning, complete the pair, or give a word's
meaning - so the character is tied to real vocabulary, not dictionary senses.
"""

import random
from datetime import date

import streamlit as st

import db_manager as db
import sound_drill as sd
import vocab_engine as ve
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Sound & Pairing", page_icon="🔊", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
HIGHLIGHT = "color:#d9480f;font-weight:600"
DRILLS = {"tone": "🎵 Tones", "pair": "🔗 Pairings"}


def reset():
    for k in [k for k in S if k.startswith("sp_")]:
        del S[k]


with st.sidebar:
    sidebar_user_badge()
    st.header("🔊 Sound & Pairing")
    drill = st.radio("Drill", list(DRILLS), format_func=DRILLS.get, key="sound_drill_pick",
                     disabled="sp_items" in S)
    if "sp_items" in S and st.button("End session"):
        reset()
        st.rerun()

st.title("🔊 Sound & Pairing")


def play(text):
    cache = S.setdefault("sound_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def big(html, size="2rem"):
    st.markdown(f"<div style='font-size:{size};line-height:1.5'>{html}</div>",
                unsafe_allow_html=True)


def material(drill):
    words = db.introduced_words(USER_ID)
    if drill == "tone":
        return sd.tone_groups(words)
    chars = {c for w in words for c in w["chinese"]}
    return sd.families(words, db.single_char_words(chars))


# ----------------------------------------------------------------------
# start screen
# ----------------------------------------------------------------------
if "sp_items" not in S:
    mat = material(drill)
    progress = db.drill_progress_get(USER_ID, drill)
    today = date.today().isoformat()
    due = sum(1 for k, t in progress.items() if (t.get("next_review_date") or "") <= today)
    if drill == "tone":
        st.markdown(f"**{len(mat)}** tone groups from your words · **{due}** due")
        st.caption("Characters that share a syllable but not a tone, always shown in a real "
                   "word. Groups appear as you learn words in different tones.")
        if mat:
            st.caption("Most useful: " + " · ".join(
                "/".join(p["entries"][0]["char"] for p in g["patterns"]) for g in mat[:5]))
    else:
        st.markdown(f"**{len(mat)}** character families from your words · **{due}** due")
        st.caption("Characters that form several of your words, drilled through those words. "
                   "Families grow as you learn more words.")
        if mat:
            st.caption("Most useful: " + " · ".join(
                f"{f['char']} ({'、'.join(w['chinese'] for w in f['words'][:3])})" for f in mat[:4]))
    if not mat:
        st.info("Nothing to drill yet — this builds from words you've been introduced to on "
                "the Words page.")
        st.stop()
    if st.button("▶️ Start", type="primary", width="stretch"):
        items = sd.build_session(drill, mat, progress, date.today())
        if not items:
            st.success("Nothing due, and no new groups for today.")
            st.stop()
        S.sp_items, S.sp_i, S.sp_results, S.sp_drill = items, 0, [], drill
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# summary
# ----------------------------------------------------------------------
if S.sp_i >= len(S.sp_items):
    if "sp_saved" not in S:
        by_key = {}
        for r in S.sp_results:
            by_key.setdefault(r["key"], []).append(r["right"])
        progress = db.drill_progress_get(USER_ID, S.sp_drill)
        for key, res in by_key.items():
            track = ve.update_track(progress.get(key, {}), sd.group_result(res))
            db.drill_progress_save(USER_ID, S.sp_drill, key, track)
        S.sp_saved = by_key
    by_key = S.sp_saved
    right = sum(r["right"] for r in S.sp_results)
    st.success(f"Done — {right} of {len(S.sp_results)} right.")
    shaky = [k for k, res in by_key.items() if not all(res)]
    if shaky:
        st.caption("Coming back sooner: " + " · ".join(shaky))
    if st.button("▶️ Another round", type="primary", width="stretch"):
        reset()
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# the current item
# ----------------------------------------------------------------------
item = S.sp_items[S.sp_i]
ans = S.get("sp_ans")
st.progress(S.sp_i / len(S.sp_items), text=f"{S.sp_i + 1} of {len(S.sp_items)}")

if item.get("header"):
    st.caption(item["header"])
if item["type"] == "tone_hear":
    play(item["play"])
    st.caption("Listen — the characters and words below all share a syllable.")
elif item.get("show_word"):
    word_html = item["show_word"]
    if item.get("char"):
        word_html = word_html.replace(item["char"], f"<span style='{HIGHLIGHT}'>{item['char']}</span>", 1)
    big(word_html, "2.4rem")

labels = [o["label"] for o in item["options"]]
choice = st.radio(item["question"], labels, index=None, key=f"sp_mc_{S.sp_i}")
if ans is None:
    if st.button("Check", type="primary", disabled=choice is None):
        picked = item["options"][labels.index(choice)]["value"]
        right = picked == item["answer"]
        w = item["word"]
        db.log_word_attempt(USER_ID, w["id"], "production" if item["type"] == "tone_pick"
                            else "recognition", item["type"], "correct" if right else "wrong",
                            {"kind": "drill", "chose": picked, "answer": item["answer"],
                             "key": item["key"]})
        S.sp_results.append({"key": item["key"], "right": right, "type": item["type"]})
        S.sp_ans = {"right": right, "picked": picked}
        st.rerun()
    st.stop()

answer_label = next(o["label"] for o in item["options"] if o["value"] == item["answer"])
st.markdown("✅ Right." if ans["right"] else f"❌ It was **{answer_label}**")
for line in item["reveal"]:
    st.caption(line)
if item.get("play") and item["type"] != "tone_hear":
    play(item["play"])
elif item["type"] == "tone_hear":
    st.caption(f"You heard: {item['word']['chinese']} {item['word']['pinyin']}")

if item["type"] == "tone_pick":
    # production: say it, then compare your recording with the model
    mic = st.audio_input(f"🎙️ Say {item['show_word']} — then compare", key=f"sp_mic_{S.sp_i}")
    if mic is not None:
        st.caption("You:")
        st.audio(mic)
        if item.get("play"):
            st.caption("Model:")
            play(item["play"])

if st.button("Next ▶️", type="primary", width="stretch"):
    S.sp_i += 1
    S.pop("sp_ans", None)
    st.rerun()
