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

import streamlit as st

import db_manager as db


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
    if not user:
        _login_screen()
    return user


def sidebar_user_badge():
    """Show who's signed in, with a way to switch. Call inside `with
    st.sidebar:` or at the top of a page."""
    user = st.session_state.get("user")
    if not user:
        return
    st.sidebar.caption(f"👤 {user['display_name']}")
    if st.sidebar.button("Switch user", use_container_width=True):
        # Clear everything session-scoped so no cards, queues or cached
        # answers leak from one person's session into the other's.
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
