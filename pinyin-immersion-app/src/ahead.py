# src/ahead.py
"""
Work done ahead of the learner, so they don't sit waiting for it.

Writing a grammar drill set takes the AI several steps (write, check,
review): ten to thirty seconds if it starts when the Grammar page opens.
The day's plan knows what's coming, though - so as soon as the Today page
has worked out the sessions, the grammar steps' drills and the next new
words' sentences are written in the background, and are waiting in the
database when the learner gets there.

    ahead.grammar(user_id, structure_ids)   start writing sets that aren't ready
    ahead.new_words(user_id, count)         write the next new words' content
    ahead.wait_grammar(user_id, sid)        if one is being written, wait for it
    ahead.for_day(user_id, day)             whatever today's sessions will need

Jobs are keyed, so asking twice starts one job; a job that fails just means
the page writes the set itself, as before.
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor

_EXEC = None
_JOBS = {}
_LOCK = threading.Lock()


def _submit(key, fn, *args):
    """Start fn(*args) unless a job with this key is already running."""
    global _EXEC
    if os.environ.get("NO_BACKGROUND"):
        return None
    with _LOCK:
        job = _JOBS.get(key)
        if job is not None and not job.done():
            return job
        if _EXEC is None:
            _EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ahead")
        job = _JOBS[key] = _EXEC.submit(_safely, key, fn, *args)
        for k in [k for k, j in _JOBS.items() if j.done() and k != key]:
            del _JOBS[k]
        return job


def _safely(key, fn, *args):
    import ai_budget
    try:
        with ai_budget.background():        # never ahead of what's on screen
            return fn(*args)
    except Exception as e:
        logging.warning(f"[AHEAD] {key} not prepared: {e}")
        return None


def running(key):
    with _LOCK:
        job = _JOBS.get(key)
        return job if job is not None and not job.done() else None


# ----------------------------------------------------------------------
# grammar drill sets
# ----------------------------------------------------------------------
def write_grammar_set(user_id, structure_id, hsk=False):
    """Write and store a drill set for the structure unless a usable one is
    stored already (on the HSK track: one with transform items, once those
    exist). Returns True if one is ready afterwards."""
    import db_manager as db
    import grammar_curriculum as gc
    import grammar_drills as gd
    structure = gc.get(structure_id)
    if not structure:
        return False
    known = db.grammar_known_vocab(user_id)
    picked = db.grammar_pick_set(user_id, structure.id, len(known))
    if picked and gd.stored_set_ok(picked["payload"], structure):
        return True
    contrasts = [gc.get(c) for c in structure.contrast if gc.get(c)]
    payload = gd.generate(structure, known, db.grammar_china_pairs(), contrasts,
                          db.grammar_recent_sentences(user_id, structure.id),
                          recent=db.recent_words(user_id), hsk=hsk)
    if payload and payload.get("reviewed", True):
        db.grammar_save_set(user_id, structure.id, len(known), payload)
        try:
            import audio_engine
            audio_engine.warm(gd.sentences_in(payload)[:8])
        except Exception:
            pass
        return True
    return False


_READY = {}          # (user, structure) -> the day a set was found or written


def _grammar_job(user_id, sid, hsk=False):
    import clock
    if write_grammar_set(user_id, sid, hsk):
        _READY[(user_id, sid)] = clock.today()


def grammar(user_id, structure_ids, hsk=False):
    import clock
    for sid in structure_ids or []:
        if _READY.get((user_id, sid)) != clock.today():
            _submit(("grammar", user_id, sid), _grammar_job, user_id, sid, hsk)


def wait_grammar(user_id, structure_id, timeout=150):
    """If this structure's set is being written right now, wait for it
    (rather than starting a second copy). True if there was one."""
    job = running(("grammar", user_id, structure_id))
    if job is None:
        return False
    try:
        job.result(timeout=timeout)
    except Exception:
        pass
    return True


# ----------------------------------------------------------------------
# new words: their sentences, and the clips their cards play
# ----------------------------------------------------------------------
def write_new_words(user_id, count):
    """Have the content for the next `count` new words written and stored,
    and their audio made. Which words come next is fixed (lesson words mixed
    into frequency order), so these are the ones the Words page will show."""
    import audio_engine
    import clock
    import db_manager as db
    import vocab_engine as ve
    from config import VOCAB_LESSON_SHARE
    lessons, frequency = db.new_word_candidates(user_id)
    known = None
    for word in ve.pick_new_words(lessons, frequency, count, VOCAB_LESSON_SHARE):
        if _READY.get((user_id, "word", word["id"])) == clock.today():
            continue
        if known is None:
            known = db.grammar_known_vocab(user_id)
        payload, _cid = db.word_content_for(user_id, word, allow_generate=True, known=known)
        audio_engine.warm([word["chinese"]] + [s_["hanzi"] for s_ in
                                               (payload.get("sentences") or [])[:3]])
        _READY[(user_id, "word", word["id"])] = clock.today()


def new_words(user_id, count):
    if count > 0:
        _submit(("words", user_id), write_new_words, user_id, min(count, 3))


def for_day(user_id, day, hsk_upcoming=(), hsk=False):
    """Start preparing what today's sessions (as built by today_plan) will
    need: called when the Today page is shown, so the drills for a later
    step - or a later session - are written while the learner does
    something else.

    On the HSK track this is the drill bank: every grammar structure in
    today's plan, then the next new ones in HSK order (hsk_upcoming), are
    written and stored ahead of time - so opening Grammar never waits on
    the AI, and the sets have their transform items."""
    try:
        for session in day or []:
            if session.get("done"):
                continue
            for step in session.get("steps", []):
                params = step.get("params") or {}
                if step.get("key") == "grammar" and not step.get("done"):
                    ids = params.get("ids", [])
                    grammar(user_id, ids if hsk else ids[:1], hsk=hsk)
                elif step.get("key") == "words" and not step.get("done") and params.get("new"):
                    new_words(user_id, params["new"])
        if hsk:
            grammar(user_id, list(hsk_upcoming), hsk=True)
    except Exception as e:
        logging.warning(f"[AHEAD] day not prepared: {e}")
