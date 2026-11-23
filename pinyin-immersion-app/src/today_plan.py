# src/today_plan.py
"""
Today's plan: two sessions a day - morning and evening - instead of one long
sitting. Splitting the day's study in two means the morning's new words are
met again hours later, which is what turns them from something seen into
something kept, without the day being chopped into pieces.

    🌅 Morning    Learn         reviews (after a night's sleep), then today's
                                new words; tones; grammar
    🌙 Evening    Use & keep    today's new and missed words once more, then
                                sentences built on them to hear and to say;
                                writing and reading

Each session is about 25 minutes. The evening opens at its hour and no
sooner than SESSION_GAP_HOURS after the morning finished (config.
SESSION_OPENS, SESSION_GAP_HOURS); it can always be started early, or
skipped.

build_day() is pure (it decides what goes in each session). The rest keeps
track of the session in progress as you move from page to page: each page
asks active(key) to know it should start straight away with the plan's
limits, and calls session_done() at its summary. The session in progress is
saved with each change, so it survives a dropped connection.
"""

import json
import logging
import math
import time
from datetime import datetime, timedelta

import clock
from config import (GRAMMAR_NEW_PER_DAY, HANDWRITING_NEW_PER_DAY, PLAN_GRAMMAR_STRUCTURES, PLAN_HANDWRITING_REVIEWS,
                    PLAN_READING_SENTENCES, PLAN_RECAP_WORDS, PLAN_SENTENCES_LISTEN,
                    PLAN_SENTENCES_SPEAK, SESSION_GAP_HOURS, SESSION_OPENS, SOUND_NEW_PER_DAY,
                    VOCAB_BACKLOG_SOFT, VOCAB_NEW_PER_DAY, VOCAB_NEW_PER_SESSION,
                    VOCAB_SESSION_REVIEWS)

STEPS = {
    "words": ("📚", "Words", "views/1_Words.py"),
    "tones": ("🎵", "Tones", "views/4_Sound_and_Pairing.py"),
    "grammar": ("🧩", "Grammar", "views/7_Grammar.py"),
    "sentences": ("🎧", "Listen & speak", "views/9_Sentences.py"),
    "handwriting": ("✍️", "Handwriting", "views/2_Handwriting.py"),
    "reading": ("📖", "Reading", "views/6_Reading.py"),
}
SESSIONS = {
    "morning": ("🌅", "Morning", "Learn",
                "Reviews first, while yesterday's words have had a night's sleep to settle; "
                "then today's new words, tones and grammar."),
    "evening": ("🌙", "Evening", "Use & keep",
                "This morning's new and missed words once more, hours later; then sentences "
                "built on them, heard and said, and writing and reading."),
}
SLOTS = list(SESSIONS)
SESSIONS_PER_WEEK = 7 * len(SLOTS)
TODAY_PAGE = "views/0_Today.py"
GAMES_PAGE = "views/8_Games.py"

GRAMMAR_MIN_KNOWN = 20        # grammar drills are built only from words you know
SENTENCES_MIN_WORDS = 8       # sentence practice needs a few introduced words
READING_MIN_CHARACTERS = 8    # reading opens once you can write a few characters
TONE_GROUPS_PER_SESSION = 5


# ======================================================================
# What goes in (pure)
# ======================================================================
def _n(count, one, many=None):
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _step(slot, key, detail, minutes, params, done):
    icon, title, page = STEPS[key]
    return {"slot": slot, "key": key, "icon": icon, "title": title, "page": page,
            "detail": detail, "minutes": max(1, math.ceil(minutes)), "params": params,
            "done": f"{slot}:{key}" in done}


def _words(state, done):
    w = state.get("words")
    if not w:
        return []
    reviews = min(w["due"], VOCAB_SESSION_REVIEWS)
    new = min(w["new_room"], w["new_available"])
    if not (reviews or new or "morning:words" in done):
        return []
    parts = [_n(reviews, "review")] if reviews else []
    parts += [_n(new, "new word")] if new else []
    if w["due"] > VOCAB_BACKLOG_SOFT:
        parts.append("new words held back until reviews come down")
    return [_step("morning", "words", " · ".join(parts) or "nothing due",
                  0.4 * reviews + 1.5 * new,
                  {"reviews": VOCAB_SESSION_REVIEWS, "new": new, "unlocks": True}, done)]


def _tones(state, done):
    t = state.get("tones")
    if not t:
        return []
    new = min(t["new_room"], t["fresh"], max(0, TONE_GROUPS_PER_SESSION - t["due"]))
    due = min(t["due"], TONE_GROUPS_PER_SESSION)
    if not (due or new or "morning:tones" in done):
        return []
    parts = [_n(due, "group") + " due"] if due else []
    parts += [_n(new, "new group")] if new else []
    return [_step("morning", "tones", " · ".join(parts) or "nothing due",
                  0.8 * (due + new), {"new": new}, done)]


def _grammar(state, done):
    g = state.get("grammar")
    if not (g and g["known"] >= GRAMMAR_MIN_KNOWN):
        return []
    if len(g["due"]) >= PLAN_GRAMMAR_STRUCTURES:            # catching up: reviews only
        picked = [(sid, name, "review") for sid, name in g["due"][:PLAN_GRAMMAR_STRUCTURES]]
    elif g["due"]:
        picked = [(sid, name, "review") for sid, name in g["due"][:1]]
    else:
        picked = [(sid, name, "new") for sid, name in g["fresh"][:1]]
    if not (picked or "morning:grammar" in done):
        return []
    return [_step("morning", "grammar",
                  " · ".join(f"{name} ({kind})" for _s, name, kind in picked) or "nothing due",
                  8 * len(picked), {"ids": [sid for sid, _nm, _k in picked]}, done)]


def _morning(state, done):
    return _words(state, done) + _tones(state, done) + _grammar(state, done)


def _evening(state, done):
    steps = []
    recap = (state.get("recap") or {}).get("count", 0)
    w = state.get("words") or {}
    # before the morning session, its new words are tonight's recap
    morning_new = 0 if "morning:words" in done else min(w.get("new_room", 0),
                                                         w.get("new_available", 0))
    if recap or morning_new or "evening:words" in done:
        n = min(recap, PLAN_RECAP_WORDS)
        detail = (f"{_n(n, 'word')} from today, once more" if n else
                  "today's new and missed words, once more")
        steps.append(_step("evening", "words", detail, 0.4 * max(n, 5),
                           {"recap": True, "cap": PLAN_RECAP_WORDS}, done))
    h = state.get("handwriting")
    # the HSK app teaches writing from the start; the original waits until
    # writing has been started from the Handwriting page
    writing = bool(h and (h["started"] or state.get("hsk_track")))
    s = state.get("sentences")
    if s and s["words"] >= SENTENCES_MIN_WORDS:
        # no writing yet: more listening in its place
        listen = PLAN_SENTENCES_LISTEN + (0 if writing else 2)
        speak = PLAN_SENTENCES_SPEAK
        steps.append(_step("evening", "sentences",
                           f"{listen} to understand by ear · {speak} to say — "
                           "today's new words first", listen + 1.5 * speak,
                           {"listen": listen, "speak": speak}, done))
    if writing:
        # the HSK track has 400 characters to get through: the whole daily
        # allowance in the evening, not three of it
        new = min(HANDWRITING_NEW_PER_DAY if state.get("hsk_track") else 3,
                  h["new_room"], h["new_available"])
        due = min(h["due"], PLAN_HANDWRITING_REVIEWS)
        if due or new or "evening:handwriting" in done:
            parts = [_n(due, "character") + " to review"] if due else []
            parts += [_n(new, "new character")] if new else []
            steps.append(_step("evening", "handwriting", " · ".join(parts) or "nothing due",
                               0.5 * due + 1.5 * new,
                               {"reviews": PLAN_HANDWRITING_REVIEWS, "new": new}, done))
        if (state.get("reading") or {}).get("characters", 0) >= READING_MIN_CHARACTERS:
            steps.append(_step("evening", "reading",
                               f"{PLAN_READING_SENTENCES} sentences from characters you can write",
                               PLAN_READING_SENTENCES, {"sentences": PLAN_READING_SENTENCES},
                               done))
    return steps


BUILDERS = {"morning": _morning, "evening": _evening}


HSK_STEPS = ("grammar", "handwriting", "reading")
HSK_SESSIONS = {
    "morning": ("🌅", "Morning", "Learn",
                "New grammar while you're fresh, and the structures due back."),
    "evening": ("🌙", "Evening", "Use & keep",
                "Writing, then reading - characters met in print after writing them."),
}


def build_day(state, hsk_track=False):
    """state (from gather_state) -> the day's sessions, in order:
    {slot, icon, title, theme, why, steps, minutes, done, skipped, finished_at}.
    Each step is {slot, key, icon, title, page, detail, minutes, params, done}.
    A step appears when it has something to do, or was already done today.
    A session is done when it was finished or skipped, or has nothing in it."""
    done = set(state.get("done") or ())
    finished = state.get("finished") or {}
    skipped = set(state.get("skipped") or ())
    day = []
    for slot in SLOTS:
        icon, title, theme, why = (HSK_SESSIONS if hsk_track else SESSIONS)[slot]
        steps = BUILDERS[slot](dict(state, hsk_track=hsk_track), done)
        if hsk_track:               # the HSK app: writing, grammar and reading only
            steps = [s for s in steps if s["key"] in HSK_STEPS]
        left = [s for s in steps if not s["done"]]
        day.append({"slot": slot, "icon": icon, "title": title, "theme": theme, "why": why,
                    "steps": steps, "minutes": sum(s["minutes"] for s in left),
                    "done": slot in finished or slot in skipped or not left,
                    "skipped": slot in skipped, "finished_at": finished.get(slot)})
    return day


def next_session(day):
    return next((s for s in day if not s["done"]), None)


def opens_at(slot, today, last_finished=None):
    """When a session is best started: its hour (local) on the study day,
    and at least SESSION_GAP_HOURS after the last session finished."""
    window = datetime.combine(today, datetime.min.time(), clock.tz()) \
        + timedelta(hours=SESSION_OPENS[slot])
    if last_finished:
        window = max(window, last_finished + timedelta(hours=SESSION_GAP_HOURS))
    return window


def last_finished(day):
    times = [s["finished_at"] for s in day if s["finished_at"]]
    return max(times) if times else None


# ======================================================================
# Reading the queues (database)
# ======================================================================
def gather_state(user_id, also=()):
    """Counts from every queue, for build_day. A queue that can't be read is
    left out of today's sessions rather than breaking the page. The reads
    don't depend on each other, so they go out at the same time: the page
    waits for the slowest, not for all of them one after another.

    `also` is more zero-argument reads to send in the same batch (the Today
    page's streak and nudges); with it the result is (state, their results),
    None standing for one that failed."""
    import db_manager as db
    import vocab_engine as ve
    today = clock.today()
    failed = object()

    def safely(name, fn):
        def run():
            try:
                return fn()
            except Exception as e:
                logging.warning(f"[PLAN] {name} unavailable: {e}")
                return failed
        return run

    def due_():
        db.sync_word_skills(user_id)
        return db.count_due(user_id)

    def handwriting_():
        started = db.handwriting_started(user_id)
        h = {"started": started, "due": 0, "new_room": 0, "new_available": 0}
        if started:
            h["due"], h["new_available"] = db.handwriting_due_and_new(user_id)
            h["new_room"] = db.handwriting_new_allowance(user_id, h["due"])
        return h

    (prog, due, introduced, recap, words, tone_prog, tone_new, g_progress, g_new, g_known,
     hand, characters, *extra) = db.in_parallel(
        safely("progress", lambda: db.day_progress(user_id)),
        safely("words", due_),
        safely("words", lambda: db.introduced_today(user_id)),
        safely("recap", lambda: db.recap_count(user_id)),
        safely("tones", lambda: db.introduced_words(user_id)),
        safely("tones", lambda: db.drill_progress_get(user_id, "tone")),
        safely("tones", lambda: db.drill_new_today(user_id, "tone")),
        safely("grammar", lambda: db.grammar_progress(user_id)),
        safely("grammar", lambda: db.grammar_new_today(user_id)),
        safely("grammar", lambda: db.grammar_known_vocab(user_id)),
        safely("handwriting", handwriting_),
        safely("reading", lambda: db.known_characters(user_id)),
        *[safely("extra", fn) for fn in also])

    def ok(*values):
        return all(v is not failed for v in values)

    state = {"done": set(), "finished": {}, "skipped": set()}
    if ok(prog):
        state.update(done=prog["done"], finished=prog["finished"], skipped=prog["skipped"])
    if ok(due, introduced):
        try:
            room = ve.new_word_allowance(due, introduced, VOCAB_NEW_PER_SESSION,
                                         VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT)
            lessons, frequency = db.new_word_candidates(user_id, limit=max(room, 1))
            state["words"] = {"due": due, "new_room": room,
                              "new_available": len(lessons) + len(frequency)}
        except Exception as e:
            logging.warning(f"[PLAN] words unavailable: {e}")
    if ok(recap):
        state["recap"] = {"count": recap}
    if ok(words, tone_prog, tone_new):
        try:
            import sound_drill as sd
            keys = [g["key"] for g in sd.tone_groups(words)]
            state["tones"] = {
                "due": sum(1 for k in keys if k in tone_prog
                           and (tone_prog[k].get("next_review_date") or "") <= today.isoformat()),
                "fresh": sum(1 for k in keys if k not in tone_prog),
                "new_room": max(0, SOUND_NEW_PER_DAY - tone_new)}
        except Exception as e:
            logging.warning(f"[PLAN] tones unavailable: {e}")
    state["sentences"] = {"words": len(words) if ok(words) else 0}
    if ok(g_progress, g_new, g_known):
        try:
            import grammar_curriculum as gc
            import grammar_drills as gd
            queue = gd.todays_queue(gc.learning_order(), g_progress, today, g_new,
                                    GRAMMAR_NEW_PER_DAY)
            state["grammar"] = {
                "known": len(g_known),
                "due": [(s.id, s.name) for s in queue if s.id in g_progress],
                "fresh": [(s.id, s.name) for s in queue if s.id not in g_progress]}
        except Exception as e:
            logging.warning(f"[PLAN] grammar unavailable: {e}")
    if ok(hand):
        state["handwriting"] = hand
        if hand["started"] and ok(characters):
            state["reading"] = {"characters": len(characters)}
    if also:
        return state, [None if x is failed else x for x in extra]
    return state


# ======================================================================
# A session in progress (session state)
# ======================================================================
def _S():
    import streamlit as st
    return st.session_state


def _today():
    return clock.today().isoformat()


def _uid():
    return (_S().get("user") or {}).get("id")


def _save_plan():
    import db_manager as db
    uid = _uid()
    if uid and _S().get("tp"):
        try:
            db.background(db.saved_session_put, uid, "plan",
                          json.dumps(_S()["tp"], ensure_ascii=False))     # no waiting
        except Exception as e:
            logging.warning(f"[PLAN] not saved: {e}")


def start(session):
    """Begin (or resume) one of today's sessions from its first unfinished
    step. Returns that step, or None if there's nothing left in it."""
    todo = [s for s in session["steps"] if not s["done"]]
    _S()["tp"] = {"date": _today(), "slot": session["slot"],
                  "order": [s["key"] for s in todo],
                  "params": {s["key"]: s["params"] for s in todo},
                  "done": [], "skipped": []}
    _save_plan()
    return todo[0] if todo else None


def plan():
    """The session in progress today, if any."""
    S = _S()
    if "tp" not in S and not S.get("_tp_restored"):
        # a new browser session: pick up today's session if one was under way
        S["_tp_restored"] = True
        uid = _uid()
        if uid:
            import db_manager as db
            db.flush_background()
            row = db.saved_session_get(uid, "plan", same_day=True)
            if row and isinstance(row["state"], dict):
                S["tp"] = row["state"]
    tp = S.get("tp")
    return tp if tp and tp.get("date") == _today() and tp.get("slot") in SESSIONS else None


def current():
    tp = plan()
    return tp["order"][0] if tp and tp["order"] else None


def active(key):
    """Is this page's step the one the session is on?"""
    return current() == key


def params(key):
    tp = plan()
    return (tp or {}).get("params", {}).get(key, {})


def _close_session(user_id, tp):
    """The session's last step is done: record it, and the whole day when
    all of them are (a skipped session means the day's plan wasn't done; a
    session with nothing in it is counted by the Today page)."""
    import db_manager as db
    db.mark_session_complete(user_id, tp["slot"])
    prog = db.day_progress(user_id)
    if all(s in prog["finished"] for s in SLOTS):
        db.mark_plan_complete(user_id)


def finish(key, user_id, seconds, items=0):
    """Mark a plan step done: logged in the ledger as part of today's
    session, and the session moves on. Doing it twice changes nothing."""
    import db_manager as db
    tp = plan()
    if not tp or key not in tp["order"]:
        return
    tp["order"].remove(key)
    tp["done"].append(key)
    _save_plan()
    db.log_study_session(user_id, key, seconds, in_plan=True, items=items, slot=tp["slot"])
    if not tp["order"]:
        _close_session(user_id, tp)


def session_done(user_id, activity, t0, items=0, step=None, once_key=None):
    """Log a finished page session exactly once: as the plan step `step` if
    it was started as one, otherwise as Library practice."""
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


def skip(key, user_id=None):
    tp = plan()
    if tp and key in tp["order"]:
        tp["order"].remove(key)
        tp["skipped"].append(key)
        _save_plan()
        if not tp["order"] and (user_id or _uid()):
            _close_session(user_id or _uid(), tp)


def _go(page, reset=None):
    import streamlit as st
    if reset:
        reset()
    st.switch_page(page)


def _clock_time(moment):
    return moment.astimezone(clock.tz()).strftime("%H:%M")


def continue_ui(reset=None, key="tp_continue"):
    """After a plan step: one button on to the next step of this session, or,
    when the session is done, when the next one opens."""
    import streamlit as st
    nxt = current()
    if nxt:
        icon, title, page = STEPS[nxt]
        if st.button(f"Continue ▶  {icon} {title}", type="primary", width="stretch", key=key):
            _go(page, reset)
        return
    tp = plan() or {}
    slot = tp.get("slot")
    later = SLOTS[SLOTS.index(slot) + 1:] if slot in SLOTS else []
    if later:
        icon, title = SESSIONS[later[0]][:2]
        at = opens_at(later[0], clock.today(), clock.now())
        when = "whenever you're ready" if at <= clock.now() else f"from {_clock_time(at)}"
        st.success(f"🎉 {SESSIONS[slot][1]} session done. Next: {icon} {title.lower()} "
                   f"session, {when}.")
    else:
        st.success("🎉 That's both sessions for today. Anything more is a bonus.")
    c1, c2 = st.columns(2)
    if c1.button("🏠 Back to Today", width="stretch", key=key + "_home"):
        _go(TODAY_PAGE, reset)
    if c2.button("🎮 Play a game", width="stretch", key=key + "_play"):
        _go(GAMES_PAGE, reset)


def sidebar(key, reset=None):
    """Inside `with st.sidebar:` on a page running a plan step: which
    session, which step, and a way to skip the step."""
    import streamlit as st
    tp = plan()
    if not tp or not active(key):
        return
    total = len(tp["done"]) + len(tp["skipped"]) + len(tp["order"])
    n = len(tp["done"]) + len(tp["skipped"]) + 1
    icon, title = SESSIONS[tp["slot"]][:2]
    st.caption(f"{icon} {title} session · step {n} of {total}")
    if st.button("⏭️ Skip this step", key="tp_skip", width="stretch"):
        skip(key)
        nxt = current()
        _go(STEPS[nxt][2] if nxt else TODAY_PAGE, reset)
