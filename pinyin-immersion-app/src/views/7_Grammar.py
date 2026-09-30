# src/views/7_Grammar.py
"""
语法 Grammar drills - hearing, recognising and saying each structure, built
only from words you already know well.

Every structure runs through five short stages: hear and identify, say it
from a situation, tell it apart from a look-alike, rapid retrieval, and a few
conversational questions. Structures come back on their own spaced-repetition
schedule; the core set comes back most often.

Pinyin shows with the answers for your first couple of goes at a structure,
then waits behind a tap. As a step of today's plan, the plan's structures
(at most two, at most one new) start straight away. A drill in progress is
saved as you go, so leaving the app picks up at the same item.
"""

import time
from datetime import date

import streamlit as st

import db_manager as db
import grammar_curriculum as gc
import grammar_drills as gd
import session_store as store
import today_plan as tp
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from speech_engine import transcribe_audio
from ai_prompter import _force_simplified
from config import GRAMMAR_NEW_PER_DAY

MIN_KNOWN = tp.GRAMMAR_MIN_KNOWN
PINYIN_GOES = 2          # practised this many times: pinyin waits behind a tap

st.set_page_config(page_title="Grammar", page_icon="🧩", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state

known = db.grammar_known_vocab(USER_ID)
progress = db.grammar_progress(USER_ID)
order = gc.learning_order()
queue = gd.todays_queue(order, progress, date.today(),
                        db.grammar_new_today(USER_ID), GRAMMAR_NEW_PER_DAY)


SAVED = ("gr_sid", "gr_set", "gr_stages", "gr_stage", "gr_item", "gr_results", "gr_ans",
         "gr_saved", "gr_fresh", "gr_pinyin_open", "gr_plan", "gr_plan_logged", "gr_adopted",
         "gr_recent")


def reset_all():
    for k in [k for k in S if k.startswith("gr_") and k != "gr_audio"]:
        del S[k]
    store.drop(USER_ID, "grammar")


if S.get("gr_plan") and S.gr_plan.get("date") != date.today().isoformat():
    reset_all()                     # yesterday's plan left open in the tab
if "gr_sid" not in S and "gr_plan" not in S:
    store.resume(USER_ID, "grammar", SAVED, clock="gr_t0")
if "gr_sid" in S and not ("gr_stages" in S and S.gr_stage >= len(S.gr_stages)):
    store.keep(USER_ID, "grammar", SAVED, clock="gr_t0")


with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("grammar", reset_all)
    st.metric("Well-studied words to build from", len(known))
    st.caption(f"{len(progress)} of {len(gc.STRUCTURES)} structures practised · "
               f"{len(queue)} ready today")

st.title("🧩 Grammar drills")
store.notice()

if len(known) < MIN_KNOWN:
    st.info(f"You have **{len(known)}** well-studied words. Grammar drills are built "
            f"only from words you know, so they start at about {MIN_KNOWN}. Keep "
            f"reviewing and they'll open up.")
    st.stop()


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def play(text):
    cache = S.setdefault("gr_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def big(hanzi, pinyin=""):
    st.markdown(f"<div style='font-size:1.9rem;line-height:1.5'>{hanzi}</div>",
                unsafe_allow_html=True)
    if not pinyin:
        return
    if S.get("gr_pinyin_open", True):
        st.caption(pinyin)
    else:
        st.markdown(f"<details><summary style='color:#90a4ae;font-size:0.85rem'>pinyin</summary>"
                    f"<span style='color:#78909c;font-size:0.9rem'>{pinyin}</span></details>",
                    unsafe_allow_html=True)


def start(structure_id):
    for k in [k for k in S if k.startswith("gr_") and k not in ("gr_audio", "gr_plan")]:
        del S[k]
    S.gr_sid, S.gr_t0 = structure_id, time.time()
    S.gr_pinyin_open = (progress.get(structure_id) or {}).get("review_count", 0) < PINYIN_GOES


def load_set(structure):
    picked = None if S.get("gr_fresh") else \
        db.grammar_pick_set(USER_ID, structure.id, len(known))
    if picked:
        db.grammar_mark_served(picked["id"])
        return picked["payload"]
    contrasts = [gc.get(c) for c in structure.contrast if gc.get(c)]
    with st.spinner("Writing drills from your vocabulary and checking them…"):
        payload = gd.generate(structure, known, db.grammar_china_pairs(), contrasts,
                              db.grammar_recent_sentences(USER_ID, structure.id),
                              recent=db.recent_words(USER_ID))
    if payload and payload.get("reviewed", True):
        # sets the reviewer couldn't check are shown once, never stored
        set_id = db.grammar_save_set(USER_ID, structure.id, len(known), payload)
        db.grammar_mark_served(set_id)
    return payload


def stages_of(payload):
    return [s for s in gd.STAGES
            if (payload.get("contrast") or {}).get("items") or s != "contrast"]


def items_of(payload, stage):
    return (payload.get("contrast") or {}).get("items", []) if stage == "contrast" \
        else payload.get(stage, [])


def record(result):
    S.gr_results.append(result)


def next_item():
    S.gr_item += 1
    if S.gr_item >= len(items_of(S.gr_set, S.gr_stages[S.gr_stage])):
        S.gr_stage += 1
        S.gr_item = 0
    S.pop("gr_ans", None)


# ----------------------------------------------------------------------
# choosing a structure
# ----------------------------------------------------------------------
if "gr_sid" not in S and "gr_plan" not in S and tp.active("grammar"):
    ids = [i for i in tp.params("grammar").get("ids", []) if gc.get(i)]
    S.gr_plan = {"ids": ids, "i": 0, "t0": time.time(), "date": date.today().isoformat()}
    if ids:
        start(ids[0])
    st.rerun()

if "gr_sid" not in S:
    if S.get("gr_plan"):                 # the plan's structures are done (or skipped)
        done_n = S.gr_plan.get("done", 0)
        tp.session_done(USER_ID, "grammar", S.gr_plan["t0"], items=done_n, step="grammar",
                        once_key="gr_plan_logged")
        st.success("Grammar done for today." if done_n else "Nothing to drill in grammar today.")
        tp.continue_ui(reset_all)
        st.stop()
    if not queue:
        st.success("All caught up — nothing due today.")
    else:
        st.write(f"**{len(queue)}** structures ready today.")
        for s_ in queue[:6]:
            tag = "new" if s_.id not in progress else "review"
            st.markdown(f"- **{s_.name}** · {s_.pattern} · _{tag}_")
        if st.button("▶️ Start", type="primary", width="stretch"):
            start(queue[0].id)
            st.rerun()
    with st.expander("Choose a structure yourself", expanded=not queue):
        sec = st.selectbox("Section", list(gc.SECTIONS),
                           format_func=lambda n: f"{n}. {gc.SECTIONS[n]}")
        options = gc.in_section(sec)
        pick = st.selectbox("Structure", options,
                            format_func=lambda s_: f"{s_.name}  ·  {s_.pattern}")
        p_ = progress.get(pick.id)
        st.caption("Not practised yet." if not p_ else
                   f"Practised {p_['review_count']}× · next review {p_['next_review_date']}")
        if st.button("▶️ Drill this", width="stretch"):
            start(pick.id)
            st.rerun()
    st.stop()

structure = gc.get(S.gr_sid)
if "gr_set" not in S:
    payload = load_set(structure)
    if not payload:
        st.error("Couldn't build a drill for this structure that passed the checks. "
                 "Try again, or pick another structure.")
        c1, c2 = st.columns(2)
        if c1.button("🔄 Try again"):
            st.rerun()
        if S.get("gr_plan"):
            gp = S.gr_plan
            if c2.button("⏭️ Skip this structure"):
                gp["i"] += 1
                if gp["i"] < len(gp["ids"]):
                    start(gp["ids"][gp["i"]])
                else:
                    del S["gr_sid"]
                    gp["ids"] = []           # nothing left: the step closes below
                st.rerun()
        elif c2.button("⏭️ Choose another"):
            del S["gr_sid"]
            st.rerun()
        st.stop()
    S.gr_set, S.gr_stages, S.gr_stage, S.gr_item, S.gr_results = \
        payload, stages_of(payload), 0, 0, []

payload = S.gr_set

# ----------------------------------------------------------------------
# structure card
# ----------------------------------------------------------------------
st.subheader(structure.name)
st.markdown(f"<div style='font-size:1.5rem'>{structure.pattern}</div>",
            unsafe_allow_html=True)
st.caption(structure.purpose)
recycled = [w for w in S.setdefault("gr_recent", db.recent_words(USER_ID))
            if w in "".join(gd.sentences_in(payload))]
if recycled:
    st.caption("♻️ Recycling your new words: " + " · ".join(recycled))
if payload.get("introduced_words"):
    st.caption("🆕 New in this drill: " + " · ".join(
        f"**{w['hanzi']}** {w.get('pinyin', '')} — {w.get('english', '')}"
        for w in payload["introduced_words"]))

# ----------------------------------------------------------------------
# finished
# ----------------------------------------------------------------------
if S.gr_stage >= len(S.gr_stages):
    if "gr_saved" not in S:
        grade, score = gd.session_grade(S.gr_results)
        prev = progress.get(structure.id) or {}
        interval, ease, nxt = gd.schedule(prev.get("interval") or 0,
                                          prev.get("ease_factor") or 2.5,
                                          grade, core=structure.core)
        db.grammar_save_progress(USER_ID, structure.id, nxt, interval, ease, score)
        try:
            db.log_activity(USER_ID, "grammar", structure.id, grade)
        except Exception:
            pass
        S.gr_saved = (score, nxt)
        if S.get("gr_plan"):
            S.gr_plan["done"] = S.gr_plan.get("done", 0) + 1
        else:
            tp.session_done(USER_ID, "grammar", S.get("gr_t0"), items=1)
        gp_ = S.get("gr_plan")
        if gp_ and gp_["i"] + 1 < len(gp_["ids"]):
            store.keep(USER_ID, "grammar", SAVED, clock="gr_t0")   # saved once, on to the next
        else:
            store.drop(USER_ID, "grammar")
    score, nxt = S.gr_saved
    st.success(f"Done — {round(score * 100)}% · back again on {nxt}")
    if S.get("gr_plan"):
        gp = S.gr_plan
        if gp["i"] + 1 < len(gp["ids"]):
            if st.button("▶️ Next structure", type="primary", width="stretch"):
                gp["i"] += 1
                start(gp["ids"][gp["i"]])
                st.rerun()
        else:
            tp.session_done(USER_ID, "grammar", gp["t0"], items=gp.get("done", 0),
                            step="grammar", once_key="gr_plan_logged")
            tp.continue_ui(reset_all)
        st.stop()
    if tp.active("grammar") or S.get("gr_adopted"):
        # started from the Library, but the plan was waiting on grammar: it counts
        S.gr_adopted = True
        tp.finish("grammar", USER_ID, 0, items=1)
        tp.continue_ui(reset_all)
        st.stop()
    c1, c2 = st.columns(2)
    if c1.button("▶️ Next structure", type="primary", width="stretch"):
        rest = [s_ for s_ in queue if s_.id != structure.id]
        if rest:
            start(rest[0].id)
        else:
            del S["gr_sid"]
        st.rerun()
    if c2.button("🔁 Again, new sentences", width="stretch"):
        start(structure.id)
        S.gr_fresh = True          # skip stored sets and write a new one
        st.rerun()
    st.stop()

stage = S.gr_stages[S.gr_stage]
items = items_of(payload, stage)
item = items[S.gr_item]
st.progress((S.gr_stage + S.gr_item / max(len(items), 1)) / len(S.gr_stages),
            text=f"{S.gr_stage + 1}. {gd.STAGE_TITLES[stage]} · "
                 f"{S.gr_item + 1} of {len(items)}")
key = f"{stage}_{S.gr_item}"
ans = S.get("gr_ans")


# ----------------------------------------------------------------------
# stage renderers
# ----------------------------------------------------------------------
def multiple_choice():
    if stage == "contrast" and payload["contrast"].get("with"):
        st.caption(f"Telling it apart from: {payload['contrast']['with']}")
    if item.get("read"):
        big(item["hanzi"])
    else:
        play(item["hanzi"])
        st.caption("Listen first — the text appears after you answer.")
    choice = st.radio(item.get("question") or "What does it mean?", item["options"],
                      index=None, key=f"mc_{key}")
    if ans is None:
        if st.button("Check", type="primary", disabled=choice is None):
            S.gr_ans = {"correct": item["options"].index(choice) == item["answer"]}
            record(S.gr_ans["correct"])
            st.rerun()
        return
    right = item["options"][item["answer"]]
    st.markdown("✅ Right." if ans["correct"] else f"❌ It was: **{right}**")
    big(item["hanzi"], item.get("pinyin", ""))
    st.caption(f"{item.get('english', '')} — {item.get('explain', '')}")
    if st.button("Next ▶️", type="primary"):
        next_item()
        st.rerun()


def spoken_answer(task, reference, reference_pinyin, reference_english, listen_first=None):
    if listen_first:
        play(listen_first["hanzi"])
        with st.expander("Show the question"):
            big(listen_first["hanzi"], listen_first.get("pinyin", ""))
            st.caption(listen_first.get("english", ""))
    else:
        st.markdown(f"**{task}**")
    if ans is None:
        mic = st.audio_input("🎙️ Say it", key=f"mic_{key}")
        typed = st.text_input("…or type it", key=f"type_{key}")
        c1, c2 = st.columns(2)
        if c1.button("Check", type="primary", disabled=not (mic or typed.strip())):
            said, spoken = typed.strip(), False
            if mic is not None:
                with st.spinner("Listening…"):
                    t = transcribe_audio(mic.getvalue())
                if t is None:
                    # a service failure is not a wrong answer: nothing recorded
                    st.error("The speech service didn't respond — record again, "
                             "or type your answer.")
                    return
                said, spoken = _force_simplified(t.get("text", "")), True
            with st.spinner("Checking…"):
                g = gd.grade_answer(structure, task, reference, said, spoken)
            S.gr_ans = {**g, "said": said}
            if g["verdict"] != "ungraded":
                record(g["verdict"])
            st.rerun()
        if c2.button("Show me"):
            S.gr_ans = {"verdict": "wrong", "feedback": "", "better": reference, "said": ""}
            record("wrong")
            st.rerun()
        return
    icon = {"correct": "✅", "close": "🟡", "wrong": "❌", "ungraded": "⚪"}[ans["verdict"]]
    if ans.get("said"):
        st.markdown(f"{icon} You said: {ans['said']}")
    if ans.get("feedback"):
        st.caption(ans["feedback"])
    if ans.get("better") and ans["better"] != reference:
        st.markdown(f"Better: {ans['better']}")
    st.markdown("**Model answer**")
    big(reference, reference_pinyin)
    play(reference)
    st.caption(reference_english)
    if st.button("Next ▶️", type="primary"):
        next_item()
        st.rerun()


def rapid():
    st.markdown(f"**{item['prompt']}**")
    st.caption("Say it aloud straight away, then check.")
    if ans is None:
        if st.button("Reveal", type="primary"):
            S.gr_ans = {"revealed": True}
            st.rerun()
        return
    big(item["answer_hanzi"], item.get("answer_pinyin", ""))
    play(item["answer_hanzi"])
    # nothing was recorded, so this is the one place you judge yourself:
    # just whether what you said matched
    c1, c2 = st.columns(2)
    for col, label, val in ((c1, "✅ I said that", "got"), (c2, "❌ I didn't", "missed")):
        if col.button(label, width="stretch"):
            record(val)
            next_item()
            st.rerun()


if stage in ("identify", "contrast"):
    multiple_choice()
elif stage == "produce":
    spoken_answer(item["situation"], item["answer_hanzi"], item.get("answer_pinyin", ""),
                  item.get("answer_english", ""))
elif stage == "rapid":
    rapid()
else:
    spoken_answer(f"Answer naturally: {item['question_hanzi']} ({item.get('question_english', '')})",
                  item["sample_hanzi"], item.get("sample_pinyin", ""),
                  item.get("sample_english", ""),
                  listen_first={"hanzi": item["question_hanzi"],
                                "pinyin": item.get("question_pinyin", ""),
                                "english": item.get("question_english", "")})
