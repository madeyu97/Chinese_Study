# src/tiles_ui.py
"""
Word tiles to tap into order (grammar Build stage, the level test's grammar
part, the sentence scramble game).

Drawn as pills, which wrap along the line on a phone; buttons in columns
stacked one per row there, so an eight-tile sentence took two screens.
"""

import streamlit as st


def pick(tiles, picked, key, label_of=None):
    """Show the tiles not picked yet; return the index of the one just tapped,
    or None. The widget's key moves on with each pick, so it starts clear."""
    left = [i for i in range(len(tiles)) if i not in picked]
    if not left:
        return None
    chosen = st.pills("Tiles", left, selection_mode="single", default=None,
                      format_func=label_of or (lambda i: tiles[i]),
                      key=f"{key}_pick{len(picked)}", label_visibility="collapsed")
    return chosen
