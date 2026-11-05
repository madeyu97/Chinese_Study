# src/views/4_Affixes.py
"""
🧬 Affixes - one root, many words, built only from words you've met.

A family is a root with three or more forms you know (main → bermain ·
pemain · permainan). Each family gets three short items from four drills:
which form means X, root + affix = ? (typed, for the meN-/peN- sound
changes), the right form for a gap in a real sentence, and what the affix
adds. Families are spaced like words: right every time and they come back
later; shaky and they come back sooner.

New families are capped per day. As a step of today's plan the round starts
straight away. A round in progress is saved as you go, so leaving the app
picks up at the same item.
"""

import time
from datetime import date

import streamlit as st

import affix_drill as ad
import db_manager as db
import session_store as store
import today_plan as tp
import vocab_engine as ve
import word_content as wc
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from config import AFFIX_NEW_PER_DAY

st.set_page_config(page_title="Affixes", page_icon="🧬", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
HIGHLIGHT = "color:#d9480f;font-weight:600"

SAVED = ("af_items", "af_i", "af_results", "af_plan", "af_date", "af_ans", "af_saved",
         "af_logged")


def reset():
    for k in [k for k in S if k.startswith("af_") and k != "af_audio"]:
        del S[k]
    store.drop(USER_ID, "affixes")


if S.get("af_plan") and S.get("af_date") != date.today().isoformat():
    reset()                         # yesterday's plan left open in the tab
if "af_items" not in S:
    store.resume(USER_ID, "affixes", SAVED, clock="af_t0")
if "af_items" in S and S.af_i < len(S.af_items):
    store.keep(USER_ID, "affixes", SAVED, clock="af_t0")

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("affixes", reset)
    if "af_items" in S and not S.get("af_plan") and st.button("End session"):
        reset()
        st.rerun()

st.title("🧬 Affixes")
store.notice()


def new_allowed():
    return max(0, AFFIX_NEW_PER_DAY - db.drill_new_today(USER_ID, ad.DRILL))


def begin(new_cap, in_plan=False):
    words = db.introduced_words(USER_ID)
    progress = db.drill_progress_get(USER_ID, ad.DRILL)
    new_cap = min(new_cap, ad.MAX_NEW_PER_SESSION)
    keys = ad.pick_keys([f["key"] for f in ad.families(words)], progress, date.today(),
                        new_cap=new_cap)
    fams = [f for f in ad.families(words, db.family_forms(keys)) if f["key"] in keys]
    forms = [w for f in fams for w in f["met"]]
    sentences = ad.gap_sentences(forms, db.affix_sentences(USER_ID, forms))
    items = ad.build_session(fams, progress, date.today(), sentences, new_cap=new_cap)
    reset()
    S.af_items, S.af_i, S.af_results = items, 0, []
    S.af_plan, S.af_t0, S.af_date = in_plan, time.time(), date.today().isoformat()


def play(text):
    cache = S.setdefault("af_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def big(html, size="2rem"):
    st.markdown(f"<div style='font-size:{size};line-height:1.5'>{html}</div>",
                unsafe_allow_html=True)


if "af_items" not in S and tp.active("affixes"):
    begin(min(tp.params("affixes").get("new", 0), new_allowed()), in_plan=True)
    st.rerun()


# ----------------------------------------------------------------------
# start screen
# ----------------------------------------------------------------------
if "af_items" not in S:
    fams = ad.families(db.introduced_words(USER_ID))
    progress = db.drill_progress_get(USER_ID, ad.DRILL)
    today = date.today().isoformat()
    due = sum(1 for f in fams if f["key"] in progress
              and (progress[f["key"]].get("next_review_date") or "") <= today)
    st.markdown(f"**{len(fams)}** affix families from your words · **{due}** due")
    st.caption("A family is a root with three or more forms you've met: main → bermain · "
               "pemain · permainan. Families grow as you learn words.")
    if not fams:
        st.info("Nothing to drill yet. A family needs three forms of one root among the words "
                "you've met on the Words page; the first usually appear after a few hundred words.")
        st.stop()
    def forms_of(f):
        forms = [w["malay"] for w in f["met"] if w["malay"] != f["key"]]
        return ", ".join(forms[:3]) + (" …" if len(forms) > 3 else "")
    st.caption("Most useful: " + " · ".join(f"{f['key']} ({forms_of(f)})" for f in fams[:4]))
    room = new_allowed()
    st.caption(f"New families still allowed today: {room} of {AFFIX_NEW_PER_DAY}.")
    if st.button("▶️ Start", type="primary", width="stretch"):
        begin(room)
        if not S.af_items:
            reset()
            st.success("Nothing due, and no new families for today.")
            st.stop()
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# summary
# ----------------------------------------------------------------------
if S.af_i >= len(S.af_items):
    if "af_saved" not in S:
        by_key = {}
        for r in S.af_results:
            by_key.setdefault(r["key"], []).append(r["right"])
        progress = db.drill_progress_get(USER_ID, ad.DRILL)
        for key, res in by_key.items():
            track = ve.update_track(progress.get(key, {}), ad.family_result(res))
            db.drill_progress_save(USER_ID, ad.DRILL, key, track)
        S.af_saved = by_key
    if tp.active("affixes"):
        S.af_plan = True            # a Library round counts if the plan is waiting on affixes
    in_plan = S.get("af_plan")
    tp.session_done(USER_ID, "affixes", S.get("af_t0"), items=len(S.af_results),
                    step="affixes" if in_plan else None, once_key="af_logged")
    store.drop(USER_ID, "affixes")        # results saved: nothing to pick up
    right = sum(r["right"] for r in S.af_results)
    if S.af_results:
        st.success(f"Done — {right} of {len(S.af_results)} right.")
    else:
        st.success("Nothing due, and no new families for today.")
    shaky = [k for k, res in S.af_saved.items() if not all(res)]
    if shaky:
        st.caption("Coming back sooner: " + " · ".join(shaky))
    if in_plan:
        tp.continue_ui(reset)
    elif st.button("▶️ Another round", type="primary", width="stretch"):
        reset()
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# the current item
# ----------------------------------------------------------------------
item = S.af_items[S.af_i]
ans = S.get("af_ans")
word = item["word"]
st.progress(S.af_i / len(S.af_items), text=f"{S.af_i + 1} of {len(S.af_items)}")


def record(right, chose):
    db.log_word_attempt(USER_ID, word["id"], ad.KIND_SKILL[item["type"]], item["type"],
                        "correct" if right else "wrong",
                        {"kind": "drill", "chose": chose, "answer": item["answer"],
                         "key": item["key"]})
    db.log_activity(USER_ID, "affixes", word["malay"], 2 if right else 0)
    S.af_results.append({"key": item["key"], "right": right, "type": item["type"]})


if item.get("header"):
    big(item["header"], "1.5rem")
if item["type"] == "form_gap":
    big(item["sentence"] if ans is None else wc.marked(item["full"], item["answer"], HIGHLIGHT))
    if item.get("english"):
        st.caption(item["english"])
elif item["type"] == "form_build":
    big(item["question"], "2.2rem")
    st.caption(item["hint"])

if item["type"] == "form_build":
    typed = st.text_input("Type the word", key=f"af_type_{S.af_i}", disabled=ans is not None)
    if ans is None:
        if st.button("Check", type="primary", disabled=not typed.strip()):
            right, message = ad.check_typed(item, typed)
            record(right, typed.strip().lower())
            S.af_ans = {"right": right, "picked": typed.strip(), "message": message}
            st.rerun()
        st.stop()
else:
    labels = [o["label"] for o in item["options"]]
    choice = st.radio(item["question"], labels, index=None, key=f"af_mc_{S.af_i}",
                      disabled=ans is not None)
    if ans is None:
        if st.button("Check", type="primary", disabled=choice is None):
            picked = item["options"][labels.index(choice)]["value"]
            right = picked == item["answer"]
            record(right, picked)
            S.af_ans = {"right": right, "picked": picked}
            st.rerun()
        st.stop()

if ans["right"]:
    st.markdown("✅ Right." + (f" Also right: {', '.join(a for a in item.get('accepted', []) if a != ans['picked'].lower())}."
                              if len(item.get("accepted", [])) > 1 else ""))
else:
    answer_label = item["answer"] if item["type"] == "form_build" else \
        next(o["label"] for o in item["options"] if o["value"] == item["answer"])
    st.markdown(f"❌ It was **{answer_label}**")
    picked = ans["picked"].lower()
    if ans.get("message"):
        st.caption(ans["message"])
    elif picked in item.get("known_forms", {}):
        st.caption(f"{picked} means “{item['known_forms'][picked]}”.")
if item.get("note"):
    st.caption(f"🔤 {item['note']}")
st.caption("  \n".join(item["reveal"]))
play(word["malay"])

if st.button("Next ▶️", type="primary", width="stretch"):
    S.af_i += 1
    S.pop("af_ans", None)
    st.rerun()
