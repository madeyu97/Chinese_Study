"""
Turn a 本草 Herb Dojo export into the herbs.csv this app reads.

Herb Dojo ships its data as a JSON blob inside index.html, so point this at
that file and it writes data/herbs.csv:

    python src/extract_herbs.py ~/Downloads/index.html
    python src/extract_herbs.py ~/Downloads/index.html --tier 1
    python src/extract_herbs.py ~/Downloads/index.html --script traditional

TRADITIONAL vs SIMPLIFIED
------------------------
Herb Dojo stores names in TRADITIONAL characters (麻黃, 生薑). The rest of
this app - your vocabulary, the frequency curriculum - is simplified
(麻黄, 生姜), and 113 of the 217 herbs are written differently in the two
scripts. Both forms are written to the CSV; --script decides which one you
practise writing, and the other is shown on the card for reference.

TIERS
-----
Herb Dojo grades herbs 1-3 by importance. Tier 1 is 68 herbs covering 111
distinct characters - a sensible first target - so the CSV is written in
tier order and the app introduces them that way.
"""

import argparse
import csv
import json
import os
import re
import sys

try:
    from zhconv import convert as _zh
except ImportError:
    _zh = None


def load_herb_dojo(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r'<script[^>]*id="bcdata"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit(
            "Couldn't find the Herb Dojo data block (id=\"bcdata\") in that "
            "file. Is it the Herb Dojo index.html?")
    data = json.loads(m.group(1))
    herbs = data.get("herbs") or []
    if not herbs:
        raise SystemExit("The data block contained no herbs.")
    return data, herbs


def build_rows(herbs, script="simplified", max_tier=3):
    rows = []
    for h in herbs:
        trad = (h.get("zh") or "").strip()
        if not trad:
            continue
        tier = h.get("tier") or 9
        if tier > max_tier:
            continue
        simp = _zh(trad, "zh-cn") if _zh else trad
        chinese = simp if script == "simplified" else trad
        other = trad if script == "simplified" else simp

        # A short, useful gloss: what it is, then what it does.
        english = (h.get("en") or "").strip()
        actions = h.get("act") or []
        if actions and isinstance(actions[0], dict):
            first = (actions[0].get("a") or "").strip()
            english = f"{english} - {first}" if english else first
        rows.append({
            "Chinese": chinese,
            "Pinyin": (h.get("py") or "").strip(),
            "English": english[:160],
            "Category": (h.get("cat") or "").strip(),
            "Tier": tier,
            "Latin": (h.get("lat") or "").strip(),
            "Alt_script": other if other != chinese else "",
        })
    # tier order first, then original ordering within a tier
    rows.sort(key=lambda r: r["Tier"])
    return rows


def main():
    ap = argparse.ArgumentParser(description="Herb Dojo -> herbs.csv")
    ap.add_argument("source", help="path to Herb Dojo index.html")
    ap.add_argument("-o", "--out", default="", help="output CSV path")
    ap.add_argument("--script", choices=["simplified", "traditional"],
                    default="simplified",
                    help="which form you want to practise writing")
    ap.add_argument("--tier", type=int, default=3,
                    help="include herbs up to this tier (1 = core 68 only)")
    args = ap.parse_args()

    data, herbs = load_herb_dojo(args.source)
    meta = data.get("_meta", {})
    print(f"{meta.get('app', 'Herb Dojo')} {meta.get('version', '')} "
          f"- {len(herbs)} herbs")

    if not _zh and args.script == "simplified":
        print("  ! zhconv not installed; names will stay traditional.\n"
              "    pip install zhconv")

    rows = build_rows(herbs, args.script, args.tier)
    out = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "herbs.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Chinese", "Pinyin", "English",
                                          "Category", "Tier", "Latin",
                                          "Alt_script"])
        w.writeheader()
        w.writerows(rows)

    chars = {c for r in rows for c in r["Chinese"] if "\u4e00" <= c <= "\u9fff"}
    by_tier = {}
    for r in rows:
        by_tier[r["Tier"]] = by_tier.get(r["Tier"], 0) + 1
    print(f"Wrote {len(rows)} herbs to {out}")
    print(f"  tiers: " + ", ".join(f"{t}:{n}" for t, n in sorted(by_tier.items())))
    print(f"  {len(chars)} distinct characters to learn")
    print(f"  writing in {args.script}")
    print("\nCommit the CSV, then pick 本草 Herb names in the handwriting "
          "sidebar and press Load.")


if __name__ == "__main__":
    sys.exit(main())
