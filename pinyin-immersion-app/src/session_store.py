# src/session_store.py
"""
Keeps a practice session going when the connection drops.

Streamlit forgets everything in a browser session once you've been away from
the app for a couple of minutes (another app, the phone locked, a restart).
Each page that runs a session saves its state here whenever it changes, and
picks it up again when you come back: same card, same answer on screen, same
score, same place in today's plan.

    keep(user_id, "words", KEYS, clock="wd_t0")    save if anything changed
    resume(user_id, "words", KEYS, clock="wd_t0")  restore -> True if found
    drop(user_id, "words")                         the session is over
    notice()                                       "Picked up where you left off."

Study sessions come back only on the day they were saved; a game within a
day. Session state is plain data - lists, dicts, sets, tuples - so it goes
into the database as JSON, with sets, tuples and number-keyed dicts tagged so
they come back as they were.
"""

import hashlib
import json
import logging
import time

import streamlit as st

import db_manager as db


def _enc(v):
    if isinstance(v, set):
        return {"__set__": [_enc(x) for x in sorted(v, key=repr)]}
    if isinstance(v, tuple):
        return {"__tuple__": [_enc(x) for x in v]}
    if isinstance(v, dict):
        if v and all(isinstance(k, int) and not isinstance(k, bool) for k in v):
            return {"__intkeys__": {str(k): _enc(x) for k, x in v.items()}}
        return {str(k): _enc(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    return v


def _dec(v):
    if isinstance(v, list):
        return [_dec(x) for x in v]
    if isinstance(v, dict):
        if set(v) == {"__set__"}:
            return {_dec(x) for x in v["__set__"]}
        if set(v) == {"__tuple__"}:
            return tuple(_dec(x) for x in v["__tuple__"])
        if set(v) == {"__intkeys__"}:
            return {int(k): _dec(x) for k, x in v["__intkeys__"].items()}
        return {k: _dec(x) for k, x in v.items()}
    return v


def _blob(encoded):
    return json.dumps(encoded, sort_keys=True, ensure_ascii=False, default=str)


def _marker(name):
    return f"_store_{name}"


def keep(user_id, name, keys, clock=None):
    """Save these session keys if they changed since the last save. Never
    raises: saving must not interrupt study."""
    S = st.session_state
    try:
        blob = _blob(_enc({k: S[k] for k in keys if k in S}))
        digest = hashlib.md5(blob.encode("utf-8")).hexdigest()
        if S.get(_marker(name)) == digest:
            return
        elapsed = time.time() - S[clock] if clock and S.get(clock) else 0
        db.saved_session_put(user_id, name, blob, elapsed)
        S[_marker(name)] = digest
    except Exception as e:
        logging.warning(f"[STORE] {name} not saved: {e}")


def resume(user_id, name, keys, clock=None, same_day=True, max_age_hours=24):
    """Put a saved session back into this browser session. Returns True if
    there was one."""
    row = db.saved_session_get(user_id, name, same_day=same_day, max_age_hours=max_age_hours)
    if not row:
        return False
    S = st.session_state
    try:
        state = _dec(row["state"])
        for k in keys:
            if k in state:
                S[k] = state[k]
        if clock:
            S[clock] = time.time() - min(row.get("elapsed") or 0, db.MAX_SESSION_SECONDS)
        S[_marker(name)] = hashlib.md5(_blob(row["state"]).encode("utf-8")).hexdigest()
        S["_store_resumed"] = True
        return True
    except Exception as e:
        logging.warning(f"[STORE] {name} not restored: {e}")
        return False


def drop(user_id, name):
    """The session is finished or abandoned: nothing to pick up later."""
    S = st.session_state
    if S.get(_marker(name)) == "dropped":
        return
    db.saved_session_del(user_id, name)
    S[_marker(name)] = "dropped"


def notice():
    if st.session_state.pop("_store_resumed", False):
        st.caption("Picked up where you left off.")
