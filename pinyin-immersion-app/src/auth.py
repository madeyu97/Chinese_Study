# src/auth.py
"""
Who is studying?

Vocabulary, sentence banks and Hokkien verifications are shared by everyone
on this deployment; SRS progress is private to each person. A short PIN
keeps the two apart so neither of you can accidentally study — and corrupt —
the other's schedule.

The PIN is a convenience lock, not real security: it stops mis-taps, not
determined strangers. Don't reuse a PIN that matters.
"""

import os

import streamlit as st

import db_manager as db


def _pinned_username():
    """A deployment can be bound to ONE person via an APP_USER secret.

    Running two Streamlit deployments off this same repo — one for each of
    you, sharing the same DATABASE_URL but with separate GROQ_API_KEYs —
    gives each person their own 1GB resource allocation and their own API
    rate limits, while vocabulary, sentence banks, Hokkien verifications
    and cached audio stay shared through the database.

    Set in that app's secrets:
        APP_USER = "matt"     # or "jean"

    When set, the PIN screen is skipped entirely. When absent, the app
    falls back to the PIN chooser so a single shared deployment still
    works.
    """
    try:
        if hasattr(st, "secrets") and "APP_USER" in st.secrets:
            return str(st.secrets["APP_USER"]).strip()
    except Exception:
        pass
    return os.environ.get("APP_USER", "").strip()


def _login_screen():
    st.title("华语 Study")
    st.caption("Who's studying?")

    users = db.list_users()
    if not users:
        st.error("No users configured.")
        st.stop()

    labels = {u["id"]: u["display_name"] for u in users}
    chosen = st.radio("Select your name", options=list(labels),
                      format_func=lambda i: labels[i], horizontal=True)
    user = next(u for u in users if u["id"] == chosen)

    if not user["has_pin"]:
        st.info(f"First time for {user['display_name']} — choose a 4-digit PIN.")
        new_pin = st.text_input("New PIN", type="password", max_chars=8,
                                key="new_pin")
        confirm = st.text_input("Confirm PIN", type="password", max_chars=8,
                                key="confirm_pin")
        if st.button("Set PIN and start", type="primary",
                     use_container_width=True):
            if len(new_pin) < 4:
                st.error("Use at least 4 digits.")
            elif new_pin != confirm:
                st.error("Those don't match.")
            else:
                db.set_user_pin(user["id"], new_pin)
                st.session_state.user = {"id": user["id"],
                                         "display_name": user["display_name"]}
                st.rerun()
    else:
        pin = st.text_input("PIN", type="password", max_chars=8, key="pin_in")
        if st.button("Start studying", type="primary",
                     use_container_width=True):
            if db.verify_user_pin(user["id"], pin):
                st.session_state.user = {"id": user["id"],
                                         "display_name": user["display_name"]}
                st.rerun()
            else:
                st.error("Wrong PIN.")

    st.stop()


def require_login():
    """Return the signed-in user dict, or render the login screen and stop.

    Call this at the top of every page, before touching any progress data.
    """
    user = st.session_state.get("user")
    if user:
        return user

    # Deployment pinned to one person: sign in automatically.
    pinned = _pinned_username()
    if pinned:
        for u in db.list_users():
            if u["username"].lower() == pinned.lower():
                st.session_state.user = {"id": u["id"],
                                         "display_name": u["display_name"],
                                         "pinned": True}
                return st.session_state.user
        st.error(f"APP_USER is set to '{pinned}', but no such user exists. "
                 f"Known users: "
                 f"{', '.join(u['username'] for u in db.list_users())}")
        st.stop()

    _login_screen()
    return st.session_state.get("user")


def sidebar_user_badge():
    """Show who's signed in, with a way to switch. Call inside `with
    st.sidebar:` or at the top of a page."""
    user = st.session_state.get("user")
    if not user:
        return
    st.sidebar.caption(f"👤 {user['display_name']}")
    if user.get("pinned"):
        # This deployment belongs to one person; switching would be
        # meaningless (and confusing) here.
        return
    if st.sidebar.button("Switch user", use_container_width=True):
        # Clear everything session-scoped so no cards, queues or cached
        # answers leak from one person's session into the other's.
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
