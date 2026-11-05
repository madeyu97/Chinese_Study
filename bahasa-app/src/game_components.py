# src/game_components.py
"""
Declares the Play page's tappable boards in a real, importable module:
Streamlit registers a component once per module, and a page script is
re-executed on every rerun, so the declaration can't live there.

The boards were written for the Chinese app: a word card's text travels in
the field "zh" and its subtitle in "py". Here zh carries the Malay word and
the subtitle is left empty (show_pinyin=False).

    memory_board(sid, cards, show_pinyin, state, key)       src/memory_board
      -> {"sid", "matched": [card indices], "moves"} after each turn
    choice_board(sid, round, prompt, options, answer,       src/choice_board
                 answered, show_pinyin, key)
      -> {"sid", "round", "chosen": option index} once a card is tapped

Both return None until something has been tapped.
"""

from pathlib import Path

import streamlit.components.v1 as components

SRC = Path(__file__).resolve().parent

memory_board = components.declare_component("memory_board", path=str(SRC / "memory_board"))
choice_board = components.declare_component("choice_board", path=str(SRC / "choice_board"))
