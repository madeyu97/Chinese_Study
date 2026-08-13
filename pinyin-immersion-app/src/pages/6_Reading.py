# src/pages/6_Reading.py
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
"""

import streamlit as st

import db_manager as db
from auth import require_login, sidebar_user_badge
from reading_engine import annotate, generate_sentence, analyse
from config import GENERATION_MODEL

# How many readable sentences must exist before the page starts revisiting
# old ones instead of generating something new.
REVISIT_AFTER = 15

st.set_page_config(page_title="Reading", page_icon="📖", layout="centered")

USER = require_login()
USER_ID = USER["id"]

with st.sidebar:
    sidebar_user_badge()
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
if len(known) < 8:
    st.info(
        f"You've written **{len(known)}** characters so far. Reading practice "
        f"opens up at about 8 - drill a few more in the handwriting section "
        f"and sentences will start appearing here.")
    st.stop()

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

col1, col2 = st.columns(2)
if col1.button("📖 Next sentence", type="primary", use_container_width=True):
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
        st.rerun()
    else:
        st.session_state.reading_current = "GENERATE"
        st.rerun()

topic = col2.text_input("Topic (optional)", placeholder="food, weather…")

if st.button("✨ Write me a new one", use_container_width=True):
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
        st.caption(report)
        st.rerun()
    else:
        st.warning(report)
        st.session_state.reading_current = None

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
        if st.button("Show all pinyin", use_container_width=True):
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
