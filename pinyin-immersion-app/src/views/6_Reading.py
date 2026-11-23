# src/views/6_Reading.py
"""
读 Reading - recognising, in ordinary type, the characters you can write.

Sentences are bounded by your own handwriting progress: only characters you
have drilled appear, apart from a small allowance where a natural sentence
is otherwise impossible. Those few always show their pinyin; the ones you
have studied show nothing unless you ask, because the point is to recall
them rather than read a transcription.

Deliberately rendered in a plain screen font rather than the calligraphic
face used in the writing drill - recognising printed type is a different
skill from writing, and the one you need for signs, menus and messages.

As a step of the evening session it reads a set number of sentences
(the first one appears straight away), then moves on.
"""

import time

import streamlit as st

import clock
import db_manager as db
import today_plan as tp
from auth import on_hsk_track, require_login, sidebar_user_badge
from reading_engine import annotate, generate_sentence, analyse
from config import GENERATION_MODEL

# How many readable sentences must exist before the page starts revisiting
# old ones instead of generating something new.
REVISIT_AFTER = 15
# Time on one sentence counted towards the ledger, at most.
MAX_SECONDS_PER_SENTENCE = 300


def shown(chinese):
    """A new sentence is on screen: log it as reading, and the time spent on
    the previous one (in a plan step, the step logs its own time)."""
    now = time.time()
    rp = st.session_state.get("reading_plan")
    if rp:
        rp["read"] += 1
    else:
        last = st.session_state.get("reading_t")
        if last:
            db.log_study_session(USER_ID, "reading", min(now - last, MAX_SECONDS_PER_SENTENCE),
                                 items=1)
        st.session_state.reading_t = now
    db.log_activity(USER_ID, "read", chinese)


def reset_plan():
    for k in ("reading_plan", "reading_current", "reading_revealed", "reading_logged"):
        st.session_state.pop(k, None)

st.set_page_config(page_title="Reading", page_icon="📖", layout="centered")

USER = require_login()
USER_ID = USER["id"]

# the HSK track reads graded passages instead (reading_hsk_page)
if on_hsk_track(USER):
    with st.sidebar:
        sidebar_user_badge()
    import reading_hsk_page
    reading_hsk_page.run(USER)
    st.stop()

S = st.session_state
if S.get("reading_plan") and S.reading_plan.get("date") != clock.today().isoformat():
    reset_plan()                    # yesterday's plan left open in the tab
if "reading_plan" not in S and tp.active("reading"):
    S.reading_plan = {"n": tp.params("reading").get("sentences", 4), "read": 0,
                      "t0": time.time(), "date": clock.today().isoformat()}
    S.reading_current = None
PLAN = S.get("reading_plan")

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("reading", reset_plan)
    st.header("📖 Reading")
    stats = db.reading_stats(USER_ID)
    st.metric("Characters you can write", stats["known_characters"])
    st.caption(f"They make up ~**{stats['coverage']}%** of everyday text. "
               f"This grows as you write more - new characters become "
               f"available here the moment you drill them.")
    st.caption(f"{stats['sentences_read']} of {stats['sentences_in_bank']} "
               f"sentences read.")

st.title("📖 Reading")

# Re-read every run: a character drilled a minute ago is usable here
# immediately, and the set only ever grows.
known = db.known_characters(USER_ID)
focus = [c for c in db.recent_characters(USER_ID, 12) if c in known]
if len(known) < tp.READING_MIN_CHARACTERS:
    st.info(
        f"You've written **{len(known)}** characters so far. Reading practice "
        f"opens up at about {tp.READING_MIN_CHARACTERS} - drill a few more in the "
        f"handwriting section and sentences will start appearing here.")
    if PLAN:
        tp.session_done(USER_ID, "reading", PLAN["t0"], step="reading", once_key="reading_logged")
        tp.continue_ui(reset_plan)
    st.stop()

if PLAN:
    max_unknown = 3                 # the plan reads at the usual level; no setting to choose
    st.progress(min(PLAN["read"], PLAN["n"]) / PLAN["n"],
                text=f"Sentence {max(1, min(PLAN['read'], PLAN['n']))} of {PLAN['n']}")
else:
    max_unknown = st.slider(
        "New characters allowed per sentence", 0, 6, 3,
        help="Characters you haven't written yet. They always show their pinyin. "
             "Set to 0 for sentences built purely from what you know.")

# ----------------------------------------------------------------------
# THE SENTENCE
# ----------------------------------------------------------------------
if "reading_current" not in st.session_state:
    st.session_state.reading_current = None
    st.session_state.reading_revealed = set()

# Changing the allowance should visibly change what you get, so drop a
# sentence that no longer fits the new setting.
if st.session_state.get("reading_allowance") != max_unknown:
    st.session_state.reading_allowance = max_unknown
    cur_card = st.session_state.get("reading_current")
    if isinstance(cur_card, dict):
        still_ok = len([c for c in cur_card["chinese"]
                        if c not in known and "\u4e00" <= c <= "\u9fff"]
                       ) <= max_unknown
        if not still_ok:
            st.session_state.reading_current = None

if focus:
    st.caption("Recently learned, so sentences will lean on these: "
               + " ".join(focus[:10]))

def next_sentence():
    pool = db.reading_bank_for(USER_ID, known, max_unknown, limit=30,
                               focus=focus)
    current = st.session_state.get("reading_current")
    current_id = current.get("id") if isinstance(current, dict) else None
    # Don't serve back the sentence already on screen.
    fresh = [p_ for p_ in pool if p_["id"] != current_id]

    # Generate when there is nothing NEW to read - not merely when the bank
    # is empty. Previously the bank only had to contain one sentence for
    # this branch to keep serving that same sentence forever.
    unseen = [p_ for p_ in fresh if p_["seen_count"] == 0]
    if unseen:
        chosen = unseen[0]
    elif len(fresh) >= REVISIT_AFTER:
        # A decent library exists, so revisit the least-seen rather than
        # spending an API call. Below this, keep writing new material -
        # re-reading the same four sentences isn't practice.
        chosen = fresh[0]
    else:
        chosen = None

    if chosen:
        st.session_state.reading_current = chosen
        st.session_state.reading_revealed = set()
        db.reading_mark_seen(USER_ID, chosen["id"])
        shown(chosen["chinese"])
    else:
        st.session_state.reading_current = "GENERATE"
    st.rerun()


plan_finished = bool(PLAN and (PLAN["read"] >= PLAN["n"] or PLAN.get("failed")))
if PLAN and not plan_finished and S.get("reading_current") is None:
    next_sentence()                 # the plan starts reading straight away
topic = ""
if not plan_finished:
    col1, col2 = st.columns(2)
    if col1.button("📖 Next sentence", type="primary", width="stretch"):
        next_sentence()
    if not PLAN:
        topic = col2.text_input("Topic (optional)", placeholder="food, weather…")
        if st.button("✨ Write me a new one", width="stretch"):
            st.session_state.reading_current = "GENERATE"
            st.rerun()

if st.session_state.reading_current == "GENERATE":
    with st.spinner("Writing a sentence from your characters…"):
        from ai_prompter import client
        sentence, english, report = generate_sentence(
            client, GENERATION_MODEL, known, topic, max_unknown, focus=focus)
    if sentence:
        db.reading_bank_add(sentence, english, known, USER_ID)
        pool = db.reading_bank_for(USER_ID, known, max_unknown, limit=5,
                                   focus=focus)
        st.session_state.reading_current = next(
            (p for p in pool if p["chinese"] == sentence),
            {"id": None, "chinese": sentence, "english": english, "unknown": []})
        st.session_state.reading_revealed = set()
        shown(sentence)
        st.caption(report)
        st.rerun()
    else:
        st.warning(report)
        st.session_state.reading_current = None
        if PLAN:
            PLAN["failed"] = True       # don't keep retrying; the step can still close

card = st.session_state.reading_current
if isinstance(card, dict):
    ann = annotate(card["chinese"], known)
    stats_line = analyse(card["chinese"], known)

    # ---- the sentence, character by character ----
    st.markdown("""<style>
      .rd-row { display:flex; flex-wrap:wrap; justify-content:center;
                gap:2px; margin:26px 0 10px; }
      .rd-cell { text-align:center; min-width:2.1em; }
      .rd-han { font-family: "Noto Sans SC","PingFang SC","Microsoft YaHei",
                sans-serif; font-size:40px; line-height:1.25; }
      .rd-new .rd-han { color:#F5C84C; }
      .rd-py { font-size:13px; color:#7EB6FF; height:1.2em; }
      .rd-py.hidden { color:#2A3242; }
      .rd-punct { font-size:34px; opacity:.7; }
    </style>""", unsafe_allow_html=True)

    cells = []
    for i, a in enumerate(ann):
        if not a["pinyin"]:
            cells.append(f'<div class="rd-cell"><div class="rd-han rd-punct">'
                         f'{a["char"]}</div><div class="rd-py"></div></div>')
            continue
        show = (not a["known"]) or (i in st.session_state.reading_revealed)
        py = a["pinyin"] if show else "·····"
        cls = "rd-cell" + ("" if a["known"] else " rd-new")
        pycls = "rd-py" + ("" if show else " hidden")
        cells.append(f'<div class="{cls}"><div class="rd-han">{a["char"]}</div>'
                     f'<div class="{pycls}">{py}</div></div>')
    st.markdown(f'<div class="rd-row">{"".join(cells)}</div>',
                unsafe_allow_html=True)

    if card.get("unknown"):
        st.caption("🟡 Gold characters are ones you haven't written yet - "
                   "their pinyin is always shown.")

    # ---- reveal controls ----
    st.caption("Tap a character to check its pinyin:")
    han_positions = [i for i, a in enumerate(ann) if a["pinyin"] and a["known"]]
    if han_positions:
        cols = st.columns(min(len(han_positions), 8))
        for n, pos in enumerate(han_positions):
            if cols[n % len(cols)].button(ann[pos]["char"],
                                          key=f"rev_{card.get('id')}_{pos}"):
                st.session_state.reading_revealed.add(pos)
                st.rerun()
        if st.button("Show all pinyin", width="stretch"):
            st.session_state.reading_revealed = set(range(len(ann)))
            st.rerun()

    # ---- meaning ----
    with st.expander("Meaning"):
        st.markdown(f"**{card.get('english') or '(no translation stored)'}**")
        for a in ann:
            if a["pinyin"] and a["gloss"]:
                mark = "" if a["known"] else "🟡 "
                st.write(f"{mark}**{a['char']}** {a['pinyin']} — {a['gloss'][:60]}")

    st.caption(f"{stats_line['total']} characters · "
               f"{stats_line['unknown_count']} new to you")
else:
    st.caption("Press **Next sentence** to begin.")

if PLAN and (PLAN["read"] >= PLAN["n"] or PLAN.get("failed")):
    st.divider()
    tp.session_done(USER_ID, "reading", PLAN["t0"], items=PLAN["read"], step="reading",
                    once_key="reading_logged")
    tp.continue_ui(reset_plan)
