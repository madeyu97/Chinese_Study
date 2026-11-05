"""Measure the rule-based analyser honestly.

The rules are tuned on ranks 1-2500 of the glossed list. They are then
scored on 300 random words from ranks 2501-5000 that they have never been
tuned on, with a model that only knows the roots of ranks 1-2500 - the
situation of a word that is not on the list. The hand-written root is the
answer key. Gate: 95% of roots right on sample B.

Run:  python3 -I tools/eval_morphology.py [--show]
"""
import csv
import random
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / "src"))
from malay import morphology as m  # noqa: E402

LABEL_NORMAL = {"pe-": "peN-", "be-": "ber-", "mer-": "meN-"}


def norm_label(label):
    label = (label or "").replace(" ", "")
    for a, b in LABEL_NORMAL.items():
        if label.startswith(a):
            label = b + label[len(a):]
    return label


def score(rows, model):
    root_ok, label_ok, misses = 0, 0, []
    for r in rows:
        gold_root = r["root"] or r["malay"]
        a = m.analyse(r["malay"], model=model, use_list=False)
        if a.root == gold_root:
            root_ok += 1
            if norm_label(a.affix_label) == norm_label(r["affixes"]):
                label_ok += 1
        else:
            misses.append((r["malay"], a.root, a.affix_label, gold_root, r["affixes"]))
    return root_ok, label_ok, misses


def main():
    show = "--show" in sys.argv
    rows = list(csv.DictReader((APP / "data" / "malay_words.csv").open(encoding="utf-8")))
    tune, rest = rows[:2500], rows[2500:]
    model = m.Model(tune)
    held = random.Random(20261015).sample(rest, 300)
    # A second sample, drawn after the rules were last changed: the first
    # one was looked at during development, this one never was.
    left = [r for r in rest if r not in held]
    fresh = random.Random(1510).sample(left, 300)
    for name, data in (("tuning set, ranks 1-2500", tune),
                       ("held out A, 300 of 2501-5000", held),
                       ("held out B, 300 more, unseen", fresh)):
        ok, lab, misses = score(data, model)
        print(f"{name}: roots {ok}/{len(data)} = {ok / len(data):.1%}; "
              f"root and affix label {lab}/{len(data)} = {lab / len(data):.1%}")
        if show:
            for miss in misses:
                print("   ", *miss, sep=" | ")


if __name__ == "__main__":
    main()
