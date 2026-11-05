"""Mark a typed Malay answer.

check_answer(given, expected, accept=()) -> Check with a verdict:
  correct            exact, or equal up to register (tak = tidak, nak = hendak)
  close-indonesian   the Indonesian form of the expected word (bisa for boleh)
  close-affix        right root, wrong affixes (belajar for mengajar)
  close-spelling     one or two letters off
  wrong              anything else

Only 'correct' counts as a pass for scheduling; the close verdicts get a
specific note so the learner sees what was nearly right.
"""
from __future__ import annotations

from dataclasses import dataclass

from malay import morphology, normalise

CORRECT = "correct"
CLOSE_INDONESIAN = "close-indonesian"
CLOSE_AFFIX = "close-affix"
CLOSE_SPELLING = "close-spelling"
WRONG = "wrong"
ORDER = (CORRECT, CLOSE_INDONESIAN, CLOSE_AFFIX, CLOSE_SPELLING, WRONG)


@dataclass
class Check:
    verdict: str
    given: str
    expected: str
    note: str = ""

    @property
    def ok(self):
        return self.verdict == CORRECT

    @property
    def close(self):
        return self.verdict.startswith("close")


def distance(a, b):
    """Levenshtein distance."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _spelling_close(a, b):
    limit = 1 if max(len(a), len(b)) <= 5 else 2
    return distance(a, b) <= limit


def _word_verdict(g, e, shown):
    """Verdict and note for one given token against one expected token
    (both canonical); `shown` is the expected token as written."""
    if g == e:
        return CORRECT, ""
    if any(normalise.canonical(m) == [e] for m in normalise.malaysian_for(g)):
        return CLOSE_INDONESIAN, f"'{g}' is Indonesian; in Malaysia say '{shown}'."
    ga, ea = morphology.analyse(g), morphology.analyse(e)
    if ga.root == ea.root and ga.root and ga.affix_label != ea.affix_label:
        want = ea.affix_label or "no affix"
        return CLOSE_AFFIX, f"Right root ({ea.root}), wrong form: '{g}' should be '{shown}' ({want})."
    if _spelling_close(g, e):
        return CLOSE_SPELLING, f"Check the spelling: '{shown}'."
    return WRONG, ""


def _against(given, expected):
    g, e = normalise.canonical(given), normalise.canonical(expected)
    if not g:
        return Check(WRONG, given, expected, "No answer.")
    if g == e:
        return Check(CORRECT, given, expected, _register_note(given, expected))
    if "".join(g) == "".join(e):
        return Check(CLOSE_SPELLING, given, expected, f"Spacing: write '{expected}'.")
    if len(g) == len(e):
        written = normalise.tokens(expected)
        shown = written if len(written) == len(e) else e
        verdicts = [_word_verdict(a, b, s) for a, b, s in zip(g, e, shown)]
        worst = max(verdicts, key=lambda v: ORDER.index(v[0]))
        if worst[0] != WRONG:
            notes = [n for v, n in verdicts if v != CORRECT and n]
            return Check(worst[0], given, expected, " ".join(dict.fromkeys(notes)))
    if _spelling_close(" ".join(g), " ".join(e)):
        return Check(CLOSE_SPELLING, given, expected, f"Nearly: '{expected}'.")
    return Check(WRONG, given, expected, "")


def _register_note(given, expected):
    """Say so when the learner used the other register."""
    gt, et = normalise.tokens(given), normalise.tokens(expected)
    if gt == et:
        return ""
    pairs = [(a, b) for a, b in zip(gt, et) if a != b]
    if pairs and len(gt) == len(et):
        return "Also right: " + ", ".join(f"{a} = {b}" for a, b in pairs) + "."
    return f"Also right: '{expected}'."


def check_answer(given, expected, accept=()):
    """Best verdict against the expected answer and any accepted
    alternatives."""
    best = None
    for target in (expected, *accept):
        c = _against(given or "", target)
        if c.ok:
            return c
        if best is None or ORDER.index(c.verdict) < ORDER.index(best.verdict):
            best = c
    if best.verdict == WRONG:
        best.expected = expected          # show the main answer, not an alternative
    return best
