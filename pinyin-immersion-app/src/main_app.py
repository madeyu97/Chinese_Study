# src/main_app.py
"""
Entry point and menu.

The app opens on Today: a plan built from everything that's due, with one
Start button. Play is the alternative to scrolling. Everything else - each
practice page on its own - lives in the Library, where it's there when you
want it but never the first question.

    Today · Play · Together
    Library   Words · Grammar · Listen & speak · Tones & pairings ·
              Handwriting · Reading
    Settings  Sentence bank & words

app2.py runs this same file for the second deployment; who the app belongs
to is decided by the APP_USER secret (see auth.py).
"""

import streamlit as st

st.set_page_config(page_title="华语 Study", page_icon="🎧", layout="centered")

from auth import current_user, login_page  # noqa: E402  (page config must come first)

if current_user() is None:
    # the sign-in screen is the only page until someone has chosen who they are
    st.navigation([st.Page(login_page, title="Sign in", icon="🔑")]).run()
    st.stop()

PAGES = {
    "": [
        st.Page("pages/0_Today.py", title="Today", icon="🏠", default=True),
        st.Page("pages/8_Games.py", title="Play", icon="🎮", url_path="play"),
        st.Page("pages/5_Together.py", title="Together", icon="🏆", url_path="together"),
    ],
    "Library": [
        st.Page("pages/1_Words.py", title="Words", icon="📚", url_path="words"),
        st.Page("pages/7_Grammar.py", title="Grammar", icon="🧩", url_path="grammar"),
        st.Page("pages/9_Sentences.py", title="Listen & speak", icon="🎧",
                url_path="sentences"),
        st.Page("pages/4_Sound_and_Pairing.py", title="Tones & pairings", icon="🎵",
                url_path="tones"),
        st.Page("pages/2_Handwriting.py", title="Handwriting", icon="✍️",
                url_path="handwriting"),
        st.Page("pages/6_Reading.py", title="Reading", icon="📖", url_path="reading"),
    ],
    "Settings": [
        st.Page("pages/10_Admin.py", title="Sentence bank & words", icon="🛠️",
                url_path="admin"),
    ],
}

st.navigation(PAGES).run()
