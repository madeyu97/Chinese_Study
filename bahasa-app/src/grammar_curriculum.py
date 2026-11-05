# src/grammar_curriculum.py
"""
The grammar curriculum the drill engine works from.

Each structure is written once, however many sections of the syllabus list
it, and carries what the drill writer needs to teach it well:

  pattern  - the shape, with an example, shown to the learner
  purpose  - one short sentence: what the structure lets you do
  notes    - guidance for the drill writer: the function to drill, the
             pitfalls, what NOT to teach. Never shown as a rule to learn.
  contrast - structures it is commonly confused with (stage 3 uses these)
  markers  - regular expressions or affix markers ("@meN", "@-kan"), of which
             at least one must match every sentence meant to use the
             structure (a cheap mechanical check; the reviewer checks the rest)
  words    - grammar words its drills may always use (jangan, belum, kat)
  level    - 1 first weeks ... 5 advanced; new structures arrive in this order
  core     - in the core automation set: reviewed more often

Malaysian Malay throughout: colloquial forms (tak, nak, dah, kat) next to the
standard ones, never Indonesian.

`LISTED` maps every section to the structures that drill it - their own
section, sections listed in also_in, and section 25 (the core set).
"""

from grammar_schema import Structure  # noqa: F401  (re-exported)
import grammar_data_1
import grammar_data_2
import grammar_data_3

_PARTS = [grammar_data_1, grammar_data_2, grammar_data_3]

SECTIONS, STRUCTURES = {}, []
for _part in _PARTS:
    SECTIONS.update(_part.SECTIONS)
    STRUCTURES += _part.STRUCTURES

BY_ID = {s.id: s for s in STRUCTURES}

LISTED = {n: [] for n in SECTIONS}
for _s in STRUCTURES:
    for _n in (_s.section, *_s.also_in):
        LISTED[_n].append((_s.name, _s.id))
    if _s.core:
        LISTED[25].append((_s.name, _s.id))


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
