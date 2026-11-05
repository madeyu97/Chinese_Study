# src/views/9_Sentences.py
"""
🎧 Listen & speak - whole sentences built on words you already know.

Two kinds of card, alternating:
  🎧 Listen  hear a sentence, pick what it means (and, if you like, type
             what you hear to see how much you caught)
  🎤 Say     see what to say in English, then say it (or type it); it is
             graded from what you said, never by you

Sentences come from the bank first, then from Tatoeba (written by real
speakers), and only then from the model, through the writer's gate and a
reviewer. Speech is transcribed by Whisper and normalised before grading:
colloquial and standard forms count the same (tak = tidak), Indonesian forms
don't.

Only words you've already been introduced to appear, so this page adds no
new material. A card moves a word's schedule only if that skill is due -
listening moves recognition, speaking moves production - so practising here
never double-counts the Words page. A session in progress is saved as you
go, so leaving the app picks up at the same card.
"""

import difflib
import os
import random
import re
import time
from datetime import date

import streamlit as st

import ai_prompter as ap
import db_manager as db
import session_store as store
import tatoeba
import today_plan as tp
import vocab_engine as ve
import word_content as wc
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from malay import normalise
from speech_engine import GRADE_MAP, grade_speech, transcribe_audio

st.set_page_config(page_title="Listen & speak", page_icon="🎧", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
LIBRARY_LISTEN, LIBRARY_SPEAK = 3, 3
RESULT_OF_GRADE = {0: "wrong", 1: "close", 2: "correct", 3: "easy"}
ICON = {"correct": "✅", "easy": "✅", "close": "🟡", "wrong": "❌", "ungraded": "⚪"}

SAVED = ("sn_cards", "sn_i", "sn_results", "sn_plan", "sn_date", "sn_ex", "sn_ex_i",
         "sn_opts", "sn_ans", "sn_logged")


def reset():
    for k in [k for k in S if k.startswith("sn_")]:
        del S[k]
    store.drop(USER_ID, "sentences")


if S.get("sn_date") and S.sn_date != str(date.today()):
    reset()
if "sn_cards" not in S and store.resume(USER_ID, "sentences", SAVED, clock="sn_t0"):
    if S.get("sn_ex"):                    # the audio file didn't survive; make it again
        S.sn_audio = create_audio_file(S.sn_ex["malay"])
if "sn_cards" in S and S.sn_i < len(S.sn_cards):
    store.keep(USER_ID, "sentences", SAVED, clock="sn_t0")

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("sentences", reset)
    if "sn_cards" in S and not S.get("sn_plan") and st.button("End session"):
        reset()
        st.rerun()

st.title("🎧 Listen & speak")
store.notice()


# ----------------------------------------------------------------------
# building a session
# ----------------------------------------------------------------------
def build_cards(n_listen, n_speak, rng=None):
    """Listening cards from the words most in need of it; speaking cards
    from words you can say (production due first, then ones you recognise
    reliably). No word appears twice."""
    rng = rng or random.Random()
    today = date.today().isoformat()
    rows = db.sentence_practice_words(USER_ID, limit=60)
    listen = rows[:n_listen]
    used = {w["id"] for w in listen}
    sayable = [w for w in rows if w["id"] not in used and ve.can_produce(w)]
    sayable.sort(key=lambda w: (not (w.get("prod_due") and w["prod_due"] <= today),
                                (w.get("rec_interval") or 0) < 1, rng.random()))
    speak = sayable[:n_speak]
    cards = []
    for i in range(max(len(listen), len(speak))):
        if i < len(listen):
            cards.append({"word": listen[i], "mode": "listen"})
        if i < len(speak):
            cards.append({"word": speak[i], "mode": "speak"})
    return cards


def begin(n_listen, n_speak, in_plan):
    reset()
    S.sn_cards = build_cards(n_listen, n_speak)
    S.sn_i, S.sn_results, S.sn_plan = 0, [], in_plan
    S.sn_t0, S.sn_date = time.time(), str(date.today())


if "sn_cards" not in S:
    if tp.active("sentences"):
        p = tp.params("sentences")
        begin(p.get("listen", LIBRARY_LISTEN), p.get("speak", LIBRARY_SPEAK), True)
        st.rerun()
    words = db.sentence_practice_words(USER_ID, limit=tp.SENTENCES_MIN_WORDS)
    if len(words) < tp.SENTENCES_MIN_WORDS:
        st.info("This builds sentences from words you've already met. Learn a few more on "
                "the Words page first.")
        st.stop()
    st.markdown(f"**{LIBRARY_LISTEN}** sentences to understand by ear and **{LIBRARY_SPEAK}** "
                "to say — each built on a word you already know.")
    st.caption("Listening cards are checked from your answer; speaking cards from what you "
               "say, in either register (tak or tidak). You can type instead of speaking "
               "whenever you need to be quiet.")
    if st.button("▶️ Start", type="primary", width="stretch"):
        begin(LIBRARY_LISTEN, LIBRARY_SPEAK, False)
        st.rerun()
    st.stop()


def items_done():
    return sum(1 for r in S.sn_results if r["result"] != "skipped")


# ----------------------------------------------------------------------
# summary
# ----------------------------------------------------------------------
if S.sn_i >= len(S.sn_cards):
    if tp.active("sentences"):
        S.sn_plan = True            # a Library round counts if the plan is waiting on it
    in_plan = S.sn_plan
    tp.session_done(USER_ID, "sentences", S.sn_t0, items=items_done(),
                    step="sentences" if in_plan else None, once_key="sn_logged")
    store.drop(USER_ID, "sentences")
    heard = [r for r in S.sn_results if r["mode"] == "listen" and r["result"] != "skipped"]
    said = [r for r in S.sn_results if r["mode"] == "speak" and r["result"] not in ("skipped", "ungraded")]
    if not S.sn_results:
        st.info("No sentences to practise right now.")
    else:
        parts = []
        if heard:
            parts.append(f"understood {sum(r['result'] == 'correct' for r in heard)} of {len(heard)}")
        if said:
            parts.append(f"said {sum(r['result'] in ('correct', 'easy') for r in said)} of "
                         f"{len(said)} well")
        st.success("Done — " + (" · ".join(parts) or "nothing graded") + ".")
        missed = sorted({r["malay"] for r in S.sn_results if r["result"] in ("wrong", "close")})
        if missed:
            st.caption("Worth another look: " + " · ".join(missed))
    if in_plan:
        tp.continue_ui(reset)
    elif st.button("▶️ Another round", type="primary", width="stretch"):
        begin(LIBRARY_LISTEN, LIBRARY_SPEAK, False)
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# the current card
# ----------------------------------------------------------------------
card = S.sn_cards[S.sn_i]
word, mode = card["word"], card["mode"]


def load_exercise():
    """A vetted sentence from the bank; else a Tatoeba sentence (listening);
    else one written now. New listening sentences go into the bank."""
    ex = db.bank_get(word["malay"])
    if ex is not None and mode == "listen" and len(ex.get("english_distractors", [])) < 2:
        ex = None
    if ex is not None:
        return ex
    blocked, flagged = db.get_blocklist(), db.get_recent_flags()
    try:
        if mode == "listen":
            ex = tatoeba.exercise_for(word, blocked, flagged)
        if ex is None:
            ex = ap.generate_exercise(word, "listen" if mode == "listen" else "recall",
                                      blocked, flagged)
    except Exception:
        return None
    if ex and ex.get("generation_mode") == "listen":
        db.bank_add(word["malay"], ex)
    return ex


if S.get("sn_ex_i") != S.sn_i:
    with st.spinner("Preparing a sentence…"):
        ex = load_exercise()
    S.sn_ex, S.sn_ex_i, S.sn_ans = ex, S.sn_i, None
    S.sn_audio = create_audio_file(ex["malay"]) if ex else None
    if ex:
        opts = list(ex.get("english_distractors", [])) + [ex["english_correct"]]
        random.shuffle(opts)
        S.sn_opts = opts
ex, ans = S.sn_ex, S.get("sn_ans")

st.progress(S.sn_i / len(S.sn_cards),
            text=f"{S.sn_i + 1} of {len(S.sn_cards)} · "
                 + ("🎧 Listen" if mode == "listen" else "🎤 Say it"))


def next_card():
    S.sn_i += 1
    for k in ("sn_ans", "sn_ex", "sn_ex_i", "sn_audio", "sn_opts"):
        S.pop(k, None)


if not ex:
    st.warning("Couldn't prepare a sentence for this word just now.")
    if st.button("Skip ▶️", type="primary", width="stretch"):
        S.sn_results.append({"malay": word["malay"], "mode": mode, "result": "skipped"})
        next_card()
        st.rerun()
    st.stop()


def play_sentence():
    if S.sn_audio and os.path.exists(S.sn_audio):
        st.audio(S.sn_audio, format="audio/mp3")
    else:
        st.caption("(Audio isn't available for this sentence right now.)")


def record(result, detail, kind):
    """Log the attempt; move the schedule only if this skill is due."""
    vid = word["id"]
    skill = ve.RECOGNITION if mode == "listen" else ve.PRODUCTION
    card_mode = f"sentence_{mode}"
    old = db.word_tracks(USER_ID, [vid]).get((vid, skill))
    scheduled = False
    if result in ve.GRADES and old and (old.get("next_review_date") or "") <= date.today().isoformat():
        new = ve.update_track(old, result)
        new["introduced_on"] = old.get("introduced_on")
        db.save_word_track(USER_ID, vid, skill, new, card_mode)
        scheduled = True
    try:
        db.log_word_attempt(USER_ID, vid, skill, card_mode, result,
                            {**detail, "kind": "sentence", "scheduled": scheduled,
                             "sentence": ex["malay"]})
    except Exception:
        pass
    db.log_activity(USER_ID, kind, ex["malay"], ve.GRADES.get(result))
    S.sn_results.append({"malay": word["malay"], "mode": mode, "result": result})
    S.sn_ans = {"result": result, "scheduled": scheduled, **detail}


def caught(typed, expected):
    """Share of the sentence's letters caught by ear (spaces and
    punctuation ignored; colloquial spellings count as the standard)."""
    a = "".join(normalise.canonical(typed or ""))
    b = "".join(normalise.canonical(expected or ""))
    if not a or not b:
        return None
    return round(100 * difflib.SequenceMatcher(None, a, b).ratio())


def word_by_word():
    if ex.get("grammar_note"):
        st.info(f"🧠 {ex['grammar_note']}")
    cache = S.setdefault("sn_gloss", {})
    toks = [t for t in normalise.tokens(ex["malay"]) if t not in cache]
    if toks:
        try:
            got = db.glosses_for(toks)
        except Exception:
            got = {}
        for t in toks:
            cache[t] = got.get(t, "")
        cache.update({k: v for k, v in got.items() if k not in cache})
    with st.expander("Word by word"):
        for tok, parts, gloss in wc.breakdown(ex["malay"], cache):
            st.markdown(f"**{tok}**" + (f" · `{parts}`" if parts else "")
                        + (f" — {gloss}" if gloss else ""))
    if ex.get("source") == "tatoeba":
        st.caption(f"Sentence from [Tatoeba](https://tatoeba.org/en/sentences/show/{ex.get('tatoeba_id')}) "
                   f"by {ex.get('author') or 'a contributor'}, CC BY 2.0 FR.")
    if st.button("🚩 This sentence is wrong", key=f"sn_flag_{S.sn_i}"):
        db.flag_sentence(ex["malay"])
        st.toast("Sentence retired — it won't be shown again.")
        for k in ("sn_ans", "sn_ex", "sn_ex_i", "sn_audio", "sn_opts"):
            S.pop(k, None)
        st.rerun()


def solution(show_meaning=True):
    st.markdown(f"<div style='font-size:1.9rem;line-height:1.5'>{ex['malay']}</div>",
                unsafe_allow_html=True)
    if show_meaning:
        st.caption(ex["english_correct"])


# ---- 🎧 listening card ------------------------------------------------
if mode == "listen":
    st.subheader("What does it mean?")
    play_sentence()
    if ans is None:
        typed = st.text_input("Type what you hear (optional)", key=f"sn_dict_{S.sn_i}")
        choice = st.radio("Meaning", S.sn_opts, index=None, key=f"sn_mc_{S.sn_i}",
                          label_visibility="collapsed")
        if st.button("Check", type="primary", width="stretch", disabled=choice is None):
            result = "correct" if choice == ex["english_correct"] else "wrong"
            record(result, {"chose": choice, "typed": typed.strip(),
                            "caught": caught(typed, ex["malay"])}, "listen")
            st.rerun()
        st.stop()
    if ans["result"] == "correct":
        st.success("✅ Right.")
    else:
        st.error(f"❌ It means: **{ex['english_correct']}**")
    if ans.get("typed"):
        m = ans.get("caught")
        st.caption(f"You typed: {ans['typed']}"
                   + (f" — about {m}% of the sentence" if m is not None else ""))
    solution()

# ---- 🎤 speaking card -------------------------------------------------
else:
    st.subheader("Say it in Malay")
    st.markdown(f"<div style='font-size:1.3rem;line-height:1.5'>{ex['english_correct']}</div>",
                unsafe_allow_html=True)
    st.caption(f"Use the word for “{wc.short_meaning(word.get('english', ''))}”.")
    if ans is None:
        mic = st.audio_input("🎙️ Say it", key=f"sn_mic_{S.sn_i}")
        typed = st.text_input("…or type it", key=f"sn_type_{S.sn_i}")
        c1, c2 = st.columns(2)
        if c1.button("Check", type="primary", width="stretch",
                     disabled=not (mic or typed.strip())):
            said, spoken = typed.strip(), False
            if mic is not None:
                with st.spinner("Listening…"):
                    t = transcribe_audio(mic.getvalue())
                if t is None:
                    # a service failure is not a wrong answer: nothing recorded
                    st.error("The speech service didn't respond — record again, or type it.")
                    st.stop()
                said, spoken = normalise.clean_transcript(t.get("text", "")), True
            if normalise.same(said, ex["malay"]):
                grading = {"overall_grade": "easy", "feedback": "Exactly right."}
            else:
                with st.spinner("Checking…"):
                    grading = grade_speech(ex["malay"], ex["english_correct"], said)
            result = RESULT_OF_GRADE[GRADE_MAP[grading["overall_grade"]]] if grading else "ungraded"
            record(result, {"said": said, "spoken": spoken, "grading": grading},
                   "speak" if spoken else "type")
            st.rerun()
        if c2.button("Show me", width="stretch"):
            record("wrong", {"said": "", "gave_up": True}, "speak")
            st.rerun()
        st.stop()
    g = ans.get("grading") or {}
    if ans.get("said"):
        st.markdown(f"{ICON[ans['result']]} You {'said' if ans.get('spoken') else 'wrote'}: {ans['said']}")
    else:
        st.markdown(ICON[ans["result"]])
    if ans["result"] == "ungraded":
        st.caption("Couldn't grade this one just now, so it doesn't count either way.")
    if "vocab_score" in g:
        cols = st.columns(3 if ans.get("spoken") else 2)
        cols[0].metric("Words", f"{g['vocab_score']}/10")
        cols[1].metric("Grammar", f"{g['grammar_score']}/10")
        if ans.get("spoken"):
            cols[2].metric("Clarity*", f"{g['pronunciation_score']}/10")
            st.caption("*From how well the transcription matched — an indirect measure.")
    if g.get("feedback"):
        st.caption(g["feedback"])
    st.markdown("**Model answer**")
    solution(show_meaning=False)
    play_sentence()

if ans.get("scheduled"):
    st.caption("This word was due, so this counts as its review.")
word_by_word()
if st.button("Next ▶️", type="primary", width="stretch"):
    next_card()
    st.rerun()
