# src/main_app.py
"""
Entry point and menu.

The app opens on Today: two study sessions a day (morning and evening),
each built from what's due and started with one button. Play is the alternative to scrolling. Everything else - each
practice page on its own - lives in the Library, where it's there when you
want it but never the first question.

    Today · Play · Together
    Library   Words · Grammar · Listen & speak · Tones & pairings ·
              Handwriting · Reading
    Settings  Sentence bank & words

On the HSK track (config.HSK_TRACK_USERS) the menu is the HSK 1-4 app
instead:

    Today · Play
    Study     Write · Grammar · Read
    Settings  HSK level test

The page scripts live in views/, not pages/: Streamlit treats a folder named
pages/ as an old-style menu, and on a freshly started server that made the
first visit to a link like /play show "Page not found".

app2.py runs this same file for the second deployment; who the app belongs
to is decided by the APP_USER secret (see auth.py).
"""

import streamlit as st

st.set_page_config(page_title="华语 Study", page_icon="🎧", layout="centered")

try:
    from auth import current_user, login_page, on_hsk_track  # noqa: E402  (page config must come first)
except Exception as e:                       # the database is set up on import
    import logging
    logging.error(f"[START] couldn't start: {e}")
    st.error("Can't reach the study database just now - your progress is safe. "
             "Try again in a minute.")
    if st.button("🔄 Try again", type="primary"):
        st.rerun()
    st.stop()

if current_user() is None:
    # the sign-in screen is the only page until someone has chosen who they are
    st.navigation([st.Page(login_page, title="Sign in", icon="🔑")]).run()
    st.stop()

PAGES = {
    "": [
        st.Page("views/0_Today.py", title="Today", icon="🏠", default=True),
        st.Page("views/8_Games.py", title="Play", icon="🎮", url_path="play"),
        st.Page("views/5_Together.py", title="Together", icon="🏆", url_path="together"),
    ],
    "Library": [
        st.Page("views/1_Words.py", title="Words", icon="📚", url_path="words"),
        st.Page("views/7_Grammar.py", title="Grammar", icon="🧩", url_path="grammar"),
        st.Page("views/9_Sentences.py", title="Listen & speak", icon="🎧",
                url_path="sentences"),
        st.Page("views/4_Sound_and_Pairing.py", title="Tones & pairings", icon="🎵",
                url_path="tones"),
        st.Page("views/2_Handwriting.py", title="Handwriting", icon="✍️",
                url_path="handwriting"),
        st.Page("views/6_Reading.py", title="Reading", icon="📖", url_path="reading"),
    ],
    "Settings": [
        st.Page("views/10_Admin.py", title="Sentence bank & words", icon="🛠️",
                url_path="admin"),
    ],
}

# The HSK 1-4 app: four things - writing, grammar, reading, games - and a
# level test. Anyone not on the HSK track keeps PAGES above, unchanged.
HSK_PAGES = {
    "": [
        st.Page("views/0_Today.py", title="Today", icon="🏠", default=True),
        st.Page("views/8_Games.py", title="Play", icon="🎮", url_path="play"),
    ],
    "Study": [
        st.Page("views/2_Handwriting.py", title="Write", icon="✍️", url_path="handwriting"),
        st.Page("views/7_Grammar.py", title="Grammar", icon="🧩", url_path="grammar"),
        st.Page("views/6_Reading.py", title="Read", icon="📖", url_path="reading"),
    ],
    "Settings": [
        st.Page("views/11_Level_test.py", title="HSK level test", icon="🎯",
                url_path="level"),
    ],
}

if on_hsk_track():
    # on a phone the page titles took two lines and pushed the lesson down
    st.markdown("<style>@media (max-width: 640px) { h1 { font-size: 1.7rem !important; } "
                "h2, h3 { font-size: 1.25rem !important; } } "
                # word tiles (st.pills): big enough to read and to tap
                "div[data-testid='stButtonGroup'] button { font-size: 1.35rem; "
                "padding: 0.35rem 0.9rem; min-height: 2.6rem; }</style>", unsafe_allow_html=True)
st.navigation(HSK_PAGES if on_hsk_track() else PAGES).run()
