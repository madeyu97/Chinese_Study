# src/views/6_Reading.py
"""
📖 Reading - short passages in standard Malay where at least 95% of the
words are ones you know.

Tap any word for its root, affixes and meaning. Words you haven't met are
highlighted; tick them and they become your next new words on the Words
page. A passage ends with two or three questions in English, so reading is
checked as understanding, not translation.

Passages are shared between both learners: one written for either of you is
shown to the other once it fits their vocabulary. When nothing fits and no
passage can be written, the page offers short reads from Tatoeba instead.
"""

import time

import streamlit as st

import db_manager as db
import reading_engine as rd
import session_store as store
import today_plan as tp
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from malay import normalise

st.set_page_config(page_title="Reading", page_icon="📖", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state

SAVED = ("rd_payload", "rd_id", "rd_answers", "rd_sent", "rd_note", "rd_listen")


def reset():
    for k in [k for k in S if k.startswith("rd_") and k not in ("rd_audio", "rd_gloss", "rd_seen")]:
        del S[k]
    store.drop(USER_ID, "reading")


if "rd_payload" not in S:
    store.resume(USER_ID, "reading", SAVED, clock="rd_t0")
if "rd_payload" in S:
    store.keep(USER_ID, "reading", SAVED, clock="rd_t0")

stats = db.reading_stats(USER_ID)
with st.sidebar:
    sidebar_user_badge()
    st.metric("Passages read", stats["read"])
    if stats["score"] is not None:
        st.caption(f"Questions right: {round(stats['score'] * 100)}% on average")
    st.caption(f"{stats['bank']} passages written so far, shared by both of you.")

st.title("📖 Reading")
store.notice()

words = db.introduced_words(USER_ID)
known = [w["malay"] for w in sorted(words, key=lambda w: w.get("freq_rank") or 10 ** 6)]
if len(known) < rd.MIN_KNOWN:
    st.info(f"You've met **{len(known)}** words. Reading opens at about {rd.MIN_KNOWN}, "
            "so passages can be almost entirely words you know.")
    st.stop()
allowed = rd.allowed_for(known)


def start(payload, reading_id, note=""):
    reset()
    S.rd_payload, S.rd_id, S.rd_t0 = payload, reading_id, time.time()
    if note:
        S.rd_note = note
    if payload.get("source") == "tatoeba":
        S.setdefault("rd_seen", []).extend(s["malay"] for s in payload["sentences"])


def play(text):
    cache = S.setdefault("rd_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def glosses(text):
    cache = S.setdefault("rd_gloss", {})
    toks = [t for t in normalise.tokens(text) if t not in cache]
    if toks:
        try:
            got = db.glosses_for(toks)
        except Exception:
            got = {}
        for t in toks:
            cache[t] = got.get(t, "")
        cache.update({k: v for k, v in got.items() if k not in cache})
    return cache


# ----------------------------------------------------------------------
# choosing a passage
# ----------------------------------------------------------------------
if "rd_payload" not in S:
    st.write("Short passages in standard Malay, at least 95% words you know. "
             "Tap any word for its parts and meaning.")
    topic = st.selectbox("Topic, if a new passage is written", ["Any topic"] + list(rd.TOPICS))
    topic = "" if topic == "Any topic" else topic
    if st.button("📖 Next passage", type="primary", width="stretch"):
        stored = db.reading_candidates()
        if topic:
            stored = [c for c in stored if c["payload"].get("topic") == topic] or stored
        picked = rd.pick_passage(stored, allowed, db.reading_read_ids(USER_ID))
        if picked:
            start(picked["payload"], picked["id"])
            st.rerun()
        with st.spinner("Writing a passage from your words and checking it…"):
            payload = rd.generate(known, db.recent_words(USER_ID), topic)
        if payload:
            # a passage the reviewer couldn't check is shown once, never stored
            rid = db.reading_save(payload, len(known)) if payload.get("reviewed", True) else None
            start(payload, rid)
            st.rerun()
        import tatoeba
        payload = rd.short_reads(tatoeba.pairs(), allowed, db.recent_words(USER_ID),
                                 exclude=S.get("rd_seen", []))
        if payload:
            start(payload, None, "No passage could be written just now, so here are short "
                                 "sentences you can read instead.")
            st.rerun()
        st.warning("Nothing to read yet that fits your words. Learn a few more and try again.")
    st.stop()


# ----------------------------------------------------------------------
# the passage
# ----------------------------------------------------------------------
payload = S.rd_payload
text = rd.passage_text(payload)
if S.get("rd_note"):
    st.caption(S.rd_note)
st.subheader(payload.get("title") or "")
if payload.get("title_english"):
    st.caption(payload["title_english"])

# a new word's meaning in this passage beats the list's general gloss (roti bakar: toasted)
in_passage = {w["malay"]: w["english"] for w in payload.get("new_words", [])}
if payload.get("source") == "tatoeba":
    for s in payload["sentences"]:
        st.markdown(rd.render(rd.annotate(s["malay"], allowed, glosses(s["malay"]))),
                    unsafe_allow_html=True)
else:
    st.markdown(rd.render(rd.annotate(text, allowed, {**glosses(text), **in_passage})),
                unsafe_allow_html=True)
cov = rd.coverage(text, allowed)
st.caption(f"{cov['total']} words · {len(cov['unknown'])} new to you (highlighted) · "
           "tap a word for its parts and meaning")

if st.button("🔊 Listen"):
    S.rd_listen = True
if S.get("rd_listen"):
    play(text)

with st.expander("English"):
    for s in payload["sentences"]:
        st.markdown(f"{s['malay']}  \n_{s['english']}_")
if payload.get("source") == "tatoeba":
    st.caption("Sentences from [Tatoeba](https://tatoeba.org), CC BY 2.0 FR: " + ", ".join(
        f"#{s.get('tatoeba_id')} by {s.get('author') or 'unknown'}" for s in payload["sentences"]))

# ---- questions ----
questions = payload.get("questions") or []
answers = S.get("rd_answers")
if questions:
    st.markdown("**Did you follow it?**")
    picks = []
    for i, q in enumerate(questions):
        picks.append(st.radio(q["question"], q["options"], index=None, key=f"rd_q_{i}",
                              disabled=answers is not None))
        if answers is not None:
            right = answers[i] == q["answer"]
            st.caption(("✅ Right." if right else f"❌ It was: {q['options'][q['answer']]}"))
    if answers is None and st.button("Check answers", type="primary",
                                     disabled=any(p_ is None for p_ in picks)):
        S.rd_answers = [q["options"].index(p_) for q, p_ in zip(questions, picks)]
        st.rerun()

# ---- new words ----
if cov["unknown"]:
    st.markdown("**New words here**")
    sent = S.get("rd_sent")
    chosen = []
    for word, meaning in rd.gloss_new_words(payload, cov["unknown"], glosses(text)):
        label = f"{word} — {meaning}" if meaning else word
        if st.checkbox(label, value=True, key=f"rd_new_{word}", disabled=sent is not None):
            chosen.append((word, meaning))
    if sent is None:
        if st.button("➕ Learn these next", disabled=not chosen):
            declared = {w["malay"]: w["english"] for w in payload.get("new_words", [])}
            n = db.request_words(USER_ID, [(w, declared.get(w) or m) for w, m in chosen])
            S.rd_sent = [w for w, _m in chosen][:n] if n else []
            st.rerun()
    elif sent:
        st.success("They'll come up first as new words on the Words page: " + ", ".join(sent))
    else:
        st.caption("Those are already on their way.")

# ---- finish ----
st.divider()
c1, c2 = st.columns([3, 1])
if c1.button("✅ Done — next passage", type="primary", width="stretch",
             disabled=bool(questions) and answers is None):
    score = (sum(a == q["answer"] for a, q in zip(answers, questions)) / len(questions)
             if questions and answers else None)
    if S.get("rd_id"):
        db.reading_mark(USER_ID, S.rd_id, score)
    db.log_activity(USER_ID, "read", payload.get("title") or text[:40], None if score is None
                    else round(score * 2))
    tp.session_done(USER_ID, "reading", S.get("rd_t0"), items=len(payload["sentences"]))
    reset()
    st.rerun()
if S.get("rd_id") and c2.button("🚩 Wrong", help="Retire this passage: it won't be shown again."):
    db.reading_retire(S.rd_id)
    reset()
    st.rerun()
