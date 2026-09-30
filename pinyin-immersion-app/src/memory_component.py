# src/memory_component.py
"""
Declares the memory-match board (src/memory_board/index.html) in a real,
importable module - see hanzi_component.py for why this can't live in the
page script itself.

    memory_board(sid=..., cards=[...], show_pinyin=..., state={...}, key=...)
      -> {"sid", "matched": [card indices], "moves"} after each turn, or None
"""

from pathlib import Path

import streamlit.components.v1 as components

COMPONENT_DIR = Path(__file__).resolve().parent / "memory_board"

memory_board = components.declare_component("memory_board", path=str(COMPONENT_DIR))
