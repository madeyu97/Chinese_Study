# src/main_app.py
"""
Entry point and menu.

The app opens on Today: a plan built from everything that's due, with one
Start button. Everything else - each practice page on its own - lives in the
Library, where it's there when you want it but never the first question.

    Today · Play · Together
    Library   Words · Affixes · Grammar · Listen & speak · Reading ·
              Clinic role-play · Penang Malay
    Settings  Word list & sentence bank

Pages join the menu as their phase lands (see LIBRARY below and
today_plan.LIVE_STEPS). The page scripts live in views/, not pages/:
Streamlit treats a folder named pages/ as an old-style menu.

app2.py runs this same file for a second deployment; who the app belongs
to is decided by the APP_USER secret (see auth.py).
"""

import streamlit as st

st.set_page_config(page_title="Bahasa Study", page_icon="🌺", layout="centered")

from auth import current_user, login_page  # noqa: E402  (page config must come first)
import today_plan as tp  # noqa: E402

if current_user() is None:
    # the sign-in screen is the only page until someone has chosen who they are
    st.navigation([st.Page(login_page, title="Sign in", icon="🔑")]).run()
    st.stop()

TOP = [st.Page("views/0_Today.py", title="Today", icon="🏠", default=True)]
if tp.GAMES_LIVE:
    TOP.append(st.Page("views/8_Games.py", title="Play", icon="🎮", url_path="play"))
TOP.append(st.Page("views/5_Together.py", title="Together", icon="🏆", url_path="together"))

# Library pages, in menu order, as (step key or page id, page). Each phase
# adds its page here when it lands.
LIBRARY = [
    ("words", st.Page("views/1_Words.py", title="Words", icon="📚", url_path="words")),
    ("affixes", st.Page("views/4_Affixes.py", title="Affixes", icon="🧬", url_path="affixes")),
    ("grammar", st.Page("views/7_Grammar.py", title="Grammar", icon="🧩", url_path="grammar")),
    ("sentences", st.Page("views/9_Sentences.py", title="Listen & speak", icon="🎧",
                          url_path="listen")),
    ("reading", st.Page("views/6_Reading.py", title="Reading", icon="📖", url_path="reading")),
    ("clinic", st.Page("views/11_Clinic.py", title="Clinic role-play", icon="🩺", url_path="clinic")),
    ("penang", st.Page("views/12_Penang.py", title="Penang Malay", icon="🏝️", url_path="penang")),
]

PAGES = {"": TOP}
if LIBRARY:
    PAGES["Library"] = [page for _key, page in LIBRARY]
PAGES["Settings"] = [st.Page("views/10_Admin.py", title="Word list & sentence bank",
                             icon="🛠️", url_path="admin")]

st.navigation(PAGES).run()
