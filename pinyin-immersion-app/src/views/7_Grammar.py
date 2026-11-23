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

import ahead
import clock
import db_manager as db
import grammar_curriculum as gc
import grammar_build as gb
import grammar_drills as gd
import hsk
import hsk_grammar as hg
import session_store as store
import today_plan as tp
import quiz
import word_content as wc
from audio_engine import create_audio_file, warm
from auth import on_hsk_track, require_login, sidebar_user_badge
from speech_engine import transcribe_audio
from ai_prompter import _force_simplified
from config import GRAMMAR_NEW_PER_DAY

MIN_KNOWN = tp.GRAMMAR_MIN_KNOWN
PINYIN_GOES = 2          # practised this many times: pinyin waits behind a tap

st.set_page_config(page_title="Grammar", page_icon="🧩", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state

HSK = on_hsk_track(USER)
known, progress, _new_today, _levels = db.in_parallel(          # one wait, not four
    lambda: db.grammar_known_vocab(USER_ID), lambda: db.grammar_progress(USER_ID),
    lambda: db.grammar_new_today(USER_ID),
    lambda: db.get_hsk_levels(USER_ID) if HSK else None)
# the HSK track: HSK 1's structures first, up to the grammar level (or the
# listening level before grammar was tested)
HSK_UPTO = hsk.grammar_upto(_levels) if HSK else None
order = hg.learning_order(HSK_UPTO) if HSK else gc.learning_order()
queue = gd.todays_queue(order, progress, clock.today(), _new_today, GRAMMAR_NEW_PER_DAY)


SAVED = ("gr_sid", "gr_set", "gr_stages", "gr_stage", "gr_item", "gr_results", "gr_ans",
         "gr_saved", "gr_fresh", "gr_pinyin_open", "gr_plan", "gr_plan_logged", "gr_adopted",
         "gr_recent")


def reset_all():
    for k in [k for k in S if k.startswith("gr_") and k != "gr_audio"]:
        del S[k]
    store.drop(USER_ID, "grammar")


if S.get("gr_plan") and S.gr_plan.get("date") != clock.today().isoformat():
    reset_all()                     # yesterday's plan left open in the tab
if "gr_sid" not in S and "gr_plan" not in S:
    store.resume(USER_ID, "grammar", SAVED, clock="gr_t0")
if "gr_sid" in S and not ("gr_stages" in S and S.gr_stage >= len(S.gr_stages)):
    store.keep(USER_ID, "grammar", SAVED, clock="gr_t0")


with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("grammar", reset_all)
    st.metric("Words to build from", len(known))
    st.caption(f"{sum(1 for s_ in order if s_.id in progress)} of {len(order)} structures "
               f"practised{f' (HSK 1–{HSK_UPTO})' if HSK else ''} · {len(queue)} ready today")

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
    if ahead.running(("grammar", USER_ID, structure.id)):
        # already being written in the background: wait for that copy
        with st.spinner("Finishing the drills for this structure…"):
            ahead.wait_grammar(USER_ID, structure.id)
    picked = None if S.get("gr_fresh") else \
        db.grammar_pick_set(USER_ID, structure.id, len(known))
    if picked and gd.stored_set_ok(picked["payload"], structure):
        db.background(db.grammar_mark_served, picked["id"])
        warm(gd.sentences_in(picked["payload"]))
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
    if payload:
        warm(gd.sentences_in(payload))
    return payload


# On the HSK track a Build stage sits between hearing a structure and saying
# it: the identify sentences, rebuilt from shuffled word tiles (grammar_build)
STAGE_ORDER = gd.STAGES[:1] + ("build",) + gd.STAGES[1:]
STAGE_TITLES = {**gd.STAGE_TITLES, "build": "Build the sentence"}


def stages_of(payload):
    return [s for s in STAGE_ORDER if items_of(payload, s)]


def items_of(payload, stage):
    items = (payload.get("contrast") or {}).get("items", []) if stage == "contrast" \
        else payload.get(stage, [])
    if stage in ("identify", "contrast"):    # a stored set may predate the option checks
        items = [it for it in items or [] if gd.mcq_problem(it) is None]
    if stage == "conversation":
        # questions written before each came with a cue were often answered
        # with a reply that didn't fit them: those are left out
        items = [it for it in items or [] if str(it.get("cue") or "").strip()]
    return items or []


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
    S.gr_plan = {"ids": ids, "i": 0, "t0": time.time(), "date": clock.today().isoformat()}
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
        if HSK:
            levels_ = hg.structure_level()
            options = order
            pick = st.selectbox("Structure", options,
                                format_func=lambda s_: f"HSK {levels_.get(s_.id)} · "
                                                       f"{s_.name}  ·  {s_.pattern}")
        else:
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


def learn_card(card):
    """How the structure works, the usual mistake, and official HSK examples
    with audio. Before the first drill it's the whole screen; after that a
    tap away."""
    st.markdown(f"**How it works.** {card['how']}")
    st.markdown(f"**Watch out.** {card['trap']}")
    for ex in card["examples"]:
        with st.container(border=True):
            st.markdown(f"<div style='font-size:1.4rem;line-height:1.5'>{ex['chinese']}</div>",
                        unsafe_allow_html=True)
            st.caption(f"{ex['pinyin']} — {ex['english']}")
            play(ex["chinese"])
    st.caption(f"HSK {card['hsk']}"
               + (" · examples from the HSK syllabus" if card["examples"] else ""))


# HSK track: a structure met for the first time is explained before it's drilled
card_ = hg.card(structure.id) if HSK else None
if card_ and structure.id not in progress and S.get("gr_learned") != structure.id:
    ahead.grammar(USER_ID, [structure.id])      # its drills are written while you read
    st.subheader(structure.name)
    st.markdown(f"<div style='font-size:1.5rem'>{structure.pattern}</div>",
                unsafe_allow_html=True)
    st.caption(structure.purpose)
    learn_card(card_)
    if st.button("Got it — start the drills", type="primary", width="stretch",
                 key="gr_learned_btn"):
        S.gr_learned = structure.id
        st.rerun()
    st.stop()

if "gr_set" not in S:
    payload = load_set(structure)
    # while this one is drilled, the next one's drills are written
    gp_ids = (S.get("gr_plan") or {}).get("ids") or [s_.id for s_ in queue]
    ahead.grammar(USER_ID, [i for i in gp_ids if i != structure.id][:1])
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
    if HSK:
        payload = {**payload, "build": gb.items(payload, structure)}
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
if card_:
    with st.expander("How it works"):
        learn_card(card_)
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
        db.background(db.log_activity, USER_ID, "grammar", structure.id, grade)
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
            text=f"{S.gr_stage + 1}. {STAGE_TITLES[stage]} · "
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
                      index=None, key=f"mc_{key}", format_func=wc.md_safe)
    if ans is None:
        pressed = quiz.buttons(choice is not None)
        if pressed:
            dont_know = pressed == "dont_know"
            S.gr_ans = {"correct": not dont_know and item["options"].index(choice) == item["answer"],
                        "dont_know": dont_know}
            record(S.gr_ans["correct"])
            st.rerun()
        return
    right = item["options"][item["answer"]]
    st.markdown("✅ Right." if ans["correct"] else
                f"{'🤷' if ans.get('dont_know') else '❌'} It was: **{right}**")
    big(item["hanzi"], item.get("pinyin", ""))
    st.caption(f"{item.get('english', '')} — {item.get('explain', '')}")
    if st.button("Next ▶️", type="primary"):
        next_item()
        st.rerun()


def spoken_answer(task, reference, reference_pinyin, reference_english, listen_first=None,
                  cue=None):
    if listen_first:
        play(listen_first["hanzi"])
        with st.expander("Show the question"):
            big(listen_first["hanzi"], listen_first.get("pinyin", ""))
            st.caption(listen_first.get("english", ""))
        if cue:
            st.markdown(f"💬 **{cue}**")
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
                g = gd.grade_answer(structure, task, reference, said, spoken,
                                    question=listen_first and
                                    f"{listen_first['hanzi']} ({listen_first.get('english', '')})")
            S.gr_ans = {**g, "said": said}
            if g["verdict"] != "ungraded":
                record(g["verdict"])
            st.rerun()
        if c2.button(quiz.DONT_KNOW):
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


def build_sentence():
    """Tap the word tiles into order; then the sentence, its pinyin and audio."""
    st.markdown(f"**Build it:** {item.get('english', '')}")
    a = ans or {"picked": []}
    picked = a["picked"]
    tiles = item["tiles"]
    built = [tiles[i] for i in picked]
    st.markdown(f"<div style='font-size:1.9rem;line-height:1.5;min-height:2.9rem'>"
                f"{' '.join(built) or '…'}</div>", unsafe_allow_html=True)
    if "verdict" not in a:
        left = [i for i in range(len(tiles)) if i not in picked]
        cols = st.columns(min(4, max(1, len(left))))
        for n, i in enumerate(left):
            if cols[n % len(cols)].button(tiles[i], key=f"{key}_t{i}", width="stretch"):
                S.gr_ans = {"picked": picked + [i]}
                st.rerun()
        c1, c2, c3 = st.columns(3)
        if c1.button("↩️ Undo", disabled=not picked, key=f"{key}_undo", width="stretch"):
            S.gr_ans = {"picked": picked[:-1]}
            st.rerun()
        if c2.button(quiz.DONT_KNOW, key=f"{key}_dk", width="stretch"):
            S.gr_ans = {"picked": picked, "verdict": "wrong"}
            record("wrong")
            st.rerun()
        if not left and c3.button("Check", type="primary", key=f"{key}_check",
                                  width="stretch"):
            verdict = gb.check(built, item)
            S.gr_ans = {"picked": picked, "verdict": verdict}
            record(verdict)
            st.rerun()
        return
    st.markdown("✅ Right." if a["verdict"] == "correct" else "❌ The order is:")
    big(item["hanzi"], item.get("pinyin", ""))
    play(item["hanzi"])
    if st.button("Next ▶️", type="primary", key=f"{key}_next"):
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
elif stage == "build":
    build_sentence()
elif stage == "produce":
    spoken_answer(item["situation"], item["answer_hanzi"], item.get("answer_pinyin", ""),
                  item.get("answer_english", ""))
elif stage == "rapid":
    rapid()
else:
    spoken_answer(f"Answer naturally: {item['question_hanzi']} ({item.get('question_english', '')})"
                  + (f" - {item['cue']}" if item.get("cue") else ""),
                  item["sample_hanzi"], item.get("sample_pinyin", ""),
                  item.get("sample_english", ""),
                  listen_first={"hanzi": item["question_hanzi"],
                                "pinyin": item.get("question_pinyin", ""),
                                "english": item.get("question_english", "")},
                  cue=item.get("cue"))
