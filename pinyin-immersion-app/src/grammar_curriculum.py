# src/grammar_curriculum.py
"""
The grammar curriculum the drill engine works from.

Each structure is written once, however many sections of the syllabus list
it, and carries what the drill writer needs to teach it well:

  pattern  - the shape, in Chinese, shown to the learner
  purpose  - one short sentence: what the structure lets you do
  notes    - guidance for the drill writer: the function to drill, the
             pitfalls, what NOT to teach. Never shown as a rule to learn.
  contrast - structures it is commonly confused with (drill 3 uses these)
  markers  - strings of which at least one must appear in every sentence that
             is meant to use the structure (a cheap mechanical check; the
             reviewer model checks the rest)
  requires - (regex, problem) pairs every such sentence must also match, for
             structures whose marker alone proves nothing: 连 is also in 连续
             and 连忙, and 无论很忙 has 无论 but isn't the structure
  level    - 1 first weeks ... 5 advanced; new structures arrive in this order
  core     - in the Core Grammar Automation Set: reviewed more often

Malaysian Mandarin throughout: no Beijing 儿 (哪里 not 哪儿, 一点 not 一点儿),
and the syllabus's own examples are corrected where they are unnatural.

`LISTED` maps every line of the syllabus, section by section, to the
structure that drills it, so coverage can be checked line by line.
"""

from grammar_schema import Structure  # noqa: F401  (re-exported)
import grammar_data_1
import grammar_data_2
import grammar_data_3
import grammar_data_4
import grammar_data_5
import grammar_data_6
import grammar_data_hsk

_PARTS = [grammar_data_1, grammar_data_2, grammar_data_3, grammar_data_4,
          grammar_data_5, grammar_data_6, grammar_data_hsk]

SECTIONS, STRUCTURES, LISTED = {}, [], {}
for _part in _PARTS:
    SECTIONS.update(_part.SECTIONS)
    STRUCTURES += _part.STRUCTURES
    for _sec, _lines in _part.LISTED.items():
        LISTED.setdefault(_sec, []).extend(_lines)

BY_ID = {s.id: s for s in STRUCTURES}


def get(structure_id):
    return BY_ID.get(structure_id)


def in_section(section, hsk=False):
    """Structures listed in a section, in syllabus order, without repeats
    (the HSK track's additions only with hsk=True)."""
    seen, out = set(), []
    for _line, sid in LISTED.get(section, []):
        if sid not in seen and sid in BY_ID and (hsk or sid not in HSK_ONLY):
            seen.add(sid)
            out.append(BY_ID[sid])
    return out


HSK_ONLY = {s.id for s in grammar_data_hsk.STRUCTURES}


def learning_order(hsk=False):
    """New structures are introduced in this order: by level, core first,
    then syllabus order - except that a pair drill always waits until both
    (or all) of the structures it contrasts have been introduced.

    The structures added for the HSK track (grammar_data_hsk) are only in
    the order with hsk=True, so the original app's queue doesn't change."""
    index = {s.id: i for i, s in enumerate(STRUCTURES)}
    pool = [s for s in STRUCTURES if hsk or s.id not in HSK_ONLY]
    ranked = sorted(pool, key=lambda s: (s.level, not s.core, index[s.id]))
    placed, out, waiting = set(), [], []

    def ready(s):
        return all(c in placed or c not in BY_ID for c in s.contrast)

    for s in ranked:
        if s.kind == "contrast" and not ready(s):
            waiting.append(s)
            continue
        out.append(s)
        placed.add(s.id)
        for w in [w for w in waiting if ready(w)]:
            waiting.remove(w)
            out.append(w)
            placed.add(w.id)
    return out + waiting
