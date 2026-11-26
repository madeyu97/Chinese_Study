# tools/build_hsk_pictures.py
"""
Fetch the pictures named in data/hsk/pictures.csv that aren't bundled yet.

pictures.csv is the hand-checked list: one HSK word per row, with the
picture the picture games show for it.

  as:<id>   ARASAAC pictogram <id>, saved as data/game_images/arasaac/<id>.webp
            (240 px). Pictograms by Sergio Palao, ARASAAC (arasaac.org),
            Government of Aragón, CC BY-NC-SA 4.0.
  tw:<hex>  Twemoji SVG, saved as data/game_images/<hex>.svg (CC BY 4.0)
  wm:<name> a Wikimedia Commons picture already bundled (credits.json)

Each picture was looked at before it went on the list: one that could
fairly stand for another HSK word in the same game, or that only makes
sense to someone who already knows the word (an arrow for 关于 'about'),
was left out.

Run: python tools/build_hsk_pictures.py
"""

import csv
import io
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "hsk" / "pictures.csv"
OUT = ROOT / "data" / "game_images"
UA = {"User-Agent": "ChineseStudyApp/1.0 (github.com/madeyu97/Chinese_Study)"}
SIZE = 240


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def main():
    from PIL import Image
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    got = 0
    for r in rows:
        kind, _, name = r["image"].partition(":")
        if kind == "as":
            path = OUT / "arasaac" / f"{name}.webp"
            if path.exists():
                continue
            png = fetch(f"https://static.arasaac.org/pictograms/{name}/{name}_300.png")
            im = Image.open(io.BytesIO(png)).convert("RGBA")
            im.thumbnail((SIZE, SIZE))
            path.parent.mkdir(parents=True, exist_ok=True)
            im.save(path, "WEBP", quality=82, method=6)
            got += 1
        elif kind == "tw":
            path = OUT / f"{name}.svg"
            if path.exists():
                continue
            path.write_bytes(fetch(
                f"https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.0.3/assets/svg/{name}.svg"))
            got += 1
    print(f"{len(rows)} pictures, {got} fetched")


if __name__ == "__main__":
    sys.exit(main())
