# src/quiz.py
"""
The buttons under a question: Check, and "I don't know".

"I don't know" counts as a miss - the word or structure comes back soon -
but it is recorded as not knowing, not as a wrong pick. A guess that
happens to land on a look-alike or a same-sound word would otherwise be
read as that confusion (see word_diagnosis), and a lucky guess as knowing.
"""

import streamlit as st

DONT_KNOW = "🤷 I don't know"


def buttons(ready, key=""):
    """Check (enabled once there's an answer) and I don't know, side by side.
    Returns "check", "dont_know" or None."""
    c1, c2 = st.columns(2)
    if c1.button("Check", type="primary", width="stretch", disabled=not ready,
                 key=f"quiz_check_{key}" if key else None):
        return "check"
    if c2.button(DONT_KNOW, width="stretch", key=f"quiz_dk_{key}" if key else None):
        return "dont_know"
    return None
