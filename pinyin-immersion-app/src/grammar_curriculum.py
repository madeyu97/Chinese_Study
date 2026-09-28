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

_PARTS = [grammar_data_1, grammar_data_2, grammar_data_3, grammar_data_4,
          grammar_data_5, grammar_data_6]

SECTIONS, STRUCTURES, LISTED = {}, [], {}
for _part in _PARTS:
    SECTIONS.update(_part.SECTIONS)
    STRUCTURES += _part.STRUCTURES
    LISTED.update(_part.LISTED)

BY_ID = {s.id: s for s in STRUCTURES}


def get(structure_id):
    return BY_ID.get(structure_id)


def in_section(section):
    """Structures listed in a section, in syllabus order, without repeats."""
    seen, out = set(), []
    for _line, sid in LISTED.get(section, []):
        if sid not in seen and sid in BY_ID:
            seen.add(sid)
            out.append(BY_ID[sid])
    return out


def learning_order():
    """New structures are introduced in this order: by level, core first,
    then syllabus order - except that a pair drill always waits until both
    (or all) of the structures it contrasts have been introduced."""
    index = {s.id: i for i, s in enumerate(STRUCTURES)}
    ranked = sorted(STRUCTURES, key=lambda s: (s.level, not s.core, index[s.id]))
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
