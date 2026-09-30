# src/today_plan.py
"""
Today's plan: one ordered list of short steps built from the queues the app
already keeps, so opening the app never starts with "which page, in what
order?".

    📚 Words        due reviews first, then a capped number of new words
    🎵 Tones        due tone groups, a few new ones
    🧩 Grammar      at most two structures, at most one of them new
    ✍️ Handwriting  only once you've started it; reviews, a few new
    🎧 Listen & speak  sentences built on words you already know

Reviews run first while you're fresh; new material is capped so tomorrow's
reviews stay manageable; the day ends with listening and speaking. A short
day is a few urgent reviews and a little listening, and still counts.

build_plan() is pure (it decides what goes in). The rest keeps track of a
plan in progress as you move from page to page: each page asks active(key)
to know it should start straight away with the plan's limits, and calls
session_done() at its summary. The plan in progress is saved with each
change, so it survives a dropped connection like the sessions do.
"""

import json
import logging
import math
import time
from datetime import date

from config import (GRAMMAR_NEW_PER_DAY, PLAN_GRAMMAR_STRUCTURES, PLAN_HANDWRITING_REVIEWS,
                    PLAN_SENTENCES_LISTEN, PLAN_SENTENCES_SPEAK, PLAN_SHORT_REVIEWS,
                    SOUND_NEW_PER_DAY, VOCAB_BACKLOG_SOFT, VOCAB_NEW_PER_DAY,
                    VOCAB_NEW_PER_SESSION, VOCAB_SESSION_REVIEWS)

STEPS = {
    "words": ("📚", "Words", "views/1_Words.py"),
    "tones": ("🎵", "Tones", "views/4_Sound_and_Pairing.py"),
    "grammar": ("🧩", "Grammar", "views/7_Grammar.py"),
    "handwriting": ("✍️", "Handwriting", "views/2_Handwriting.py"),
    "sentences": ("🎧", "Listen & speak", "views/9_Sentences.py"),
}
STEP_ORDER = list(STEPS)
TODAY_PAGE = "views/0_Today.py"
GAMES_PAGE = "views/8_Games.py"

GRAMMAR_MIN_KNOWN = 20        # grammar drills are built only from words you know
SENTENCES_MIN_WORDS = 8       # sentence practice needs a few introduced words
TONE_GROUPS_PER_SESSION = 5


# ======================================================================
# What goes in (pure)
# ======================================================================
def _n(count, one, many=None):
    return f"{count} {one if count == 1 else (many or one + 's')}"


def build_plan(state, short=False):
    """state (from gather_state) -> ordered steps:
    {key, icon, title, page, detail, minutes, params, done}.
    A step is included when it has something to do today, or when it was
    already done today (so progress stays visible)."""
    done = set(state.get("done") or ())
    steps = []

    def add(key, detail, minutes, params):
        icon, title, page = STEPS[key]
        steps.append({"key": key, "icon": icon, "title": title, "page": page,
                      "detail": detail, "minutes": max(1, math.ceil(minutes)),
                      "params": params, "done": key in done})

    w = state.get("words")
    if w:
        cap = PLAN_SHORT_REVIEWS if short else VOCAB_SESSION_REVIEWS
        reviews = min(w["due"], cap)
        new = 0 if short else min(w["new_room"], w["new_available"])
        if reviews or new or "words" in done:
            parts = [_n(reviews, "review")] if reviews else []
            parts += [_n(new, "new word")] if new else []
            if w["due"] > VOCAB_BACKLOG_SOFT and not short:
                parts.append("new words held back until reviews come down")
            add("words", " · ".join(parts) or "nothing due",
                0.4 * reviews + 1.5 * new,
                {"reviews": cap, "new": new, "unlocks": not short})

    t = state.get("tones")
    if t and (not short or "tones" in done):
        new = min(t["new_room"], t["fresh"], max(0, TONE_GROUPS_PER_SESSION - t["due"]))
        due = min(t["due"], TONE_GROUPS_PER_SESSION)
        if due or new or "tones" in done:
            parts = [_n(due, "group") + " due"] if due else []
            parts += [_n(new, "new group")] if new else []
            add("tones", " · ".join(parts) or "nothing due", 0.8 * (due + new), {"new": new})

    g = state.get("grammar")
    if g and g["known"] >= GRAMMAR_MIN_KNOWN and (not short or "grammar" in done):
        picked = [(sid, name, "review") for sid, name in g["due"][:PLAN_GRAMMAR_STRUCTURES]]
        if len(picked) < PLAN_GRAMMAR_STRUCTURES and g["fresh"]:
            sid, name = g["fresh"][0]            # at most one new structure a day
            picked.append((sid, name, "new"))
        if picked or "grammar" in done:
            add("grammar", " · ".join(f"{name} ({kind})" for _sid, name, kind in picked)
                or "nothing due", 8 * len(picked), {"ids": [sid for sid, _n_, _k in picked]})

    h = state.get("handwriting")
    if h and h["started"] and (not short or "handwriting" in done):
        new = min(3, h["new_room"], h["new_available"])
        due = min(h["due"], PLAN_HANDWRITING_REVIEWS)
        if due or new or "handwriting" in done:
            parts = [_n(due, "character") + " to review"] if due else []
            parts += [_n(new, "new character")] if new else []
            add("handwriting", " · ".join(parts) or "nothing due", 0.5 * due + 1.5 * new,
                {"reviews": PLAN_HANDWRITING_REVIEWS, "new": new})

    s = state.get("sentences")
    if s and s["words"] >= SENTENCES_MIN_WORDS:
        listen = PLAN_SENTENCES_LISTEN
        speak = 0 if short else PLAN_SENTENCES_SPEAK
        detail = f"{_n(listen, 'sentence')} to understand by ear"
        if speak:
            detail += f" · {speak} to say"
        add("sentences", detail + ", all with words you know", listen + 1.5 * speak,
            {"listen": listen, "speak": speak})

    return sorted(steps, key=lambda st_: STEP_ORDER.index(st_["key"]))


def minutes_left(steps):
    return sum(s["minutes"] for s in steps if not s["done"])


def next_step(steps):
    return next((s for s in steps if not s["done"]), None)


# ======================================================================
# Reading the queues (database)
# ======================================================================
def gather_state(user_id):
    """Counts from every queue, for build_plan. A queue that can't be read
    is left out of today's plan rather than breaking the page."""
    import db_manager as db
    import vocab_engine as ve
    today = date.today()
    state = {"done": set()}
    try:
        state["done"] = db.plan_done_today(user_id)
    except Exception as e:
        logging.warning(f"[PLAN] done steps unavailable: {e}")

    try:
        db.sync_word_skills(user_id)
        due = db.count_due(user_id)
        room = ve.new_word_allowance(due, db.introduced_today(user_id), VOCAB_NEW_PER_SESSION,
                                     VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT)
        lessons, frequency = db.new_word_candidates(user_id, limit=max(room, 1))
        state["words"] = {"due": due, "new_room": room,
                          "new_available": len(lessons) + len(frequency)}
    except Exception as e:
        logging.warning(f"[PLAN] words unavailable: {e}")

    words = []
    try:
        import sound_drill as sd
        words = db.introduced_words(user_id)
        groups = sd.tone_groups(words)
        prog = db.drill_progress_get(user_id, "tone")
        keys = [g["key"] for g in groups]
        state["tones"] = {
            "due": sum(1 for k in keys if k in prog
                       and (prog[k].get("next_review_date") or "") <= today.isoformat()),
            "fresh": sum(1 for k in keys if k not in prog),
            "new_room": max(0, SOUND_NEW_PER_DAY - db.drill_new_today(user_id, "tone"))}
    except Exception as e:
        logging.warning(f"[PLAN] tones unavailable: {e}")
    state["sentences"] = {"words": len(words)}

    try:
        import grammar_curriculum as gc
        import grammar_drills as gd
        progress = db.grammar_progress(user_id)
        queue = gd.todays_queue(gc.learning_order(), progress, today,
                                db.grammar_new_today(user_id), GRAMMAR_NEW_PER_DAY)
        state["grammar"] = {
            "known": len(db.grammar_known_vocab(user_id)),
            "due": [(s.id, s.name) for s in queue if s.id in progress],
            "fresh": [(s.id, s.name) for s in queue if s.id not in progress]}
    except Exception as e:
        logging.warning(f"[PLAN] grammar unavailable: {e}")

    try:
        started = db.handwriting_started(user_id)
        h = {"started": started, "due": 0, "new_room": 0, "new_available": 0}
        if started:
            h["due"], h["new_available"] = db.handwriting_due_and_new(user_id)
            h["new_room"] = db.handwriting_new_allowance(user_id, h["due"])
        state["handwriting"] = h
    except Exception as e:
        logging.warning(f"[PLAN] handwriting unavailable: {e}")
    return state


# ======================================================================
# A plan in progress (session state)
# ======================================================================
def _S():
    import streamlit as st
    return st.session_state


def _today():
    return date.today().isoformat()


def _uid():
    return (_S().get("user") or {}).get("id")


def _save_plan():
    import db_manager as db
    uid = _uid()
    if uid and _S().get("tp"):
        try:
            db.saved_session_put(uid, "plan", json.dumps(_S()["tp"], ensure_ascii=False))
        except Exception as e:
            logging.warning(f"[PLAN] not saved: {e}")


def start(steps, short=False):
    """Begin (or resume) today's plan from its first unfinished step.
    Returns that step, or None if everything is done."""
    todo = [s for s in steps if not s["done"]]
    _S()["tp"] = {"date": _today(), "short": short,
                  "order": [s["key"] for s in todo],
                  "params": {s["key"]: s["params"] for s in todo},
                  "done": [], "skipped": []}
    _save_plan()
    return todo[0] if todo else None


def plan():
    S = _S()
    if "tp" not in S and not S.get("_tp_restored"):
        # a new browser session: pick up today's plan if one was under way
        S["_tp_restored"] = True
        uid = _uid()
        if uid:
            import db_manager as db
            row = db.saved_session_get(uid, "plan", same_day=True)
            if row and isinstance(row["state"], dict):
                S["tp"] = row["state"]
    tp = S.get("tp")
    return tp if tp and tp.get("date") == _today() else None


def current():
    tp = plan()
    return tp["order"][0] if tp and tp["order"] else None


def active(key):
    """Is this page's step the one the plan is on?"""
    return current() == key


def params(key):
    tp = plan()
    return (tp or {}).get("params", {}).get(key, {})


def finish(key, user_id, seconds, items=0):
    """Mark a plan step done: logged in the ledger as part of the plan, and
    the plan moves on. Doing it twice changes nothing."""
    import db_manager as db
    tp = plan()
    if not tp or key not in tp["order"]:
        return
    tp["order"].remove(key)
    tp["done"].append(key)
    _save_plan()
    db.log_study_session(user_id, key, seconds, in_plan=True, items=items)
    if not tp["order"]:
        db.mark_plan_complete(user_id)


def session_done(user_id, activity, t0, items=0, step=None, once_key=None):
    """Log a finished session exactly once: as the plan step `step` if the
    session was started as one, otherwise as Library practice."""
    import db_manager as db
    S = _S()
    if once_key:
        if S.get(once_key):
            return
        S[once_key] = True
    seconds = time.time() - (t0 or time.time())
    tp = plan()
    if step and tp and step in tp["order"]:
        finish(step, user_id, seconds, items)
    else:
        db.log_study_session(user_id, activity, seconds, in_plan=False, items=items)


def skip(key):
    tp = plan()
    if tp and key in tp["order"]:
        tp["order"].remove(key)
        tp["skipped"].append(key)
        _save_plan()


def _go(page, reset=None):
    import streamlit as st
    if reset:
        reset()
    st.switch_page(page)


def continue_ui(reset=None, key="tp_continue"):
    """After a plan step: one button on to the next step, or, when the plan
    is done, back to Today or a game."""
    import streamlit as st
    nxt = current()
    if nxt:
        icon, title, page = STEPS[nxt]
        if st.button(f"Continue ▶  {icon} {title}", type="primary", width="stretch", key=key):
            _go(page, reset)
        return
    st.success("🎉 That's today's plan done. Anything more is a bonus.")
    c1, c2 = st.columns(2)
    if c1.button("🏠 Back to Today", width="stretch", key=key + "_home"):
        _go(TODAY_PAGE, reset)
    if c2.button("🎮 Play a game", width="stretch", key=key + "_play"):
        _go(GAMES_PAGE, reset)


def sidebar(key, reset=None):
    """Inside `with st.sidebar:` on a page running a plan step: where you
    are in the plan, and a way to skip the step."""
    import streamlit as st
    tp = plan()
    if not tp or not active(key):
        return
    total = len(tp["done"]) + len(tp["skipped"]) + len(tp["order"])
    n = len(tp["done"]) + len(tp["skipped"]) + 1
    st.caption(f"📅 Today's plan · step {n} of {total}")
    if st.button("⏭️ Skip this step", key="tp_skip", width="stretch"):
        skip(key)
        nxt = current()
        _go(STEPS[nxt][2] if nxt else TODAY_PAGE, reset)
