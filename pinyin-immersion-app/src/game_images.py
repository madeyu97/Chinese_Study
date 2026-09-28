# src/game_images.py
"""
Pictures for the games, all bundled in data/game_images so the games work
offline.

Image keys:
  tw:<codepoint>  Twemoji graphic (CC-BY 4.0), e.g. "tw:1f455" -> 1f455.svg
  wm:<name>       photo or illustration from Wikimedia Commons, e.g.
                  "wm:durian" -> durian.jpg; author, licence and source
                  link for each are in credits.json
"""

import base64
import functools
import json
from pathlib import Path

IMAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "game_images"
CREDITS_PATH = IMAGE_DIR / "credits.json"
MIME = {".svg": "image/svg+xml", ".jpg": "image/jpeg", ".png": "image/png"}


@functools.lru_cache(maxsize=1)
def credits():
    """name -> {file, title, author, licence, licence_url, source, changes}"""
    return json.loads(CREDITS_PATH.read_text(encoding="utf-8"))


def path_for(key):
    kind, _, name = key.partition(":")
    if kind == "tw":
        return IMAGE_DIR / f"{name}.svg"
    if kind == "wm":
        return IMAGE_DIR / credits()[name]["file"]
    raise KeyError(key)


@functools.lru_cache(maxsize=512)
def data_uri(key):
    path = path_for(key)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{MIME[path.suffix]};base64,{data}"


def img_tag(key, size=120, extra_style=""):
    """Square picture, shrinking to fit a narrow cell without distorting."""
    style = f"width:{size}px;height:{size}px;max-width:100%;object-fit:contain;"
    if key.startswith("wm:"):
        style += "border-radius:8px;"
    return f'<img src="{data_uri(key)}" style="{style}{extra_style}" alt=""/>'


def _md(text):
    """Plain text safe inside markdown link text."""
    for ch in "\\`*_[]<>":
        text = text.replace(ch, "\\" + ch)
    return text


def credit_lines(items):
    """One markdown line per Commons picture used by these items, in order."""
    lines = []
    for it in items:
        kind, _, name = it["image"].partition(":")
        if kind != "wm":
            continue
        c = credits()[name]
        licence = (f"[{_md(c['licence'])}]({c['licence_url']})" if c.get("licence_url")
                   else _md(c["licence"]))
        source = c["source"].replace("(", "%28").replace(")", "%29")
        lines.append(f"- **{it['chinese']}** {_md(it['english'])} — [{_md(c['title'].removeprefix('File:'))}]({source}) "
                     f"by {_md(c['author'])}, {licence}; {c['changes']}")
    return lines
