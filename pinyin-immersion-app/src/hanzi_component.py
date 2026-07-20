# src/hanzi_component.py
"""
Declares the handwriting drill component in a real, importable module.

Why this file exists: streamlit's multipage runner executes page scripts as
anonymous modules (not registered in sys.modules), and
components.declare_component() inspects the caller's module to name the
component — from a page script that lookup returns None and crashes with
"RuntimeError: module is None". Declaring here, in a module the page
imports, resolves normally.
"""

from pathlib import Path

import streamlit.components.v1 as components

COMPONENT_DIR = Path(__file__).resolve().parent / "hw_component"

hanzi_drill = components.declare_component("hanzi_drill", path=str(COMPONENT_DIR))
