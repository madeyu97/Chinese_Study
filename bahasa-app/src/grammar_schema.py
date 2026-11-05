# src/grammar_schema.py
"""The shape of one grammar structure (see grammar_curriculum for the fields).

Markers are how the drill checker knows a sentence really uses the
structure. Malay affixes aren't fixed strings (membaca, menulis, memukul are
all meN-), so a marker is either
  - a regular expression, matched case-insensitively: r"\\btidak\\b|\\btak\\b"
  - an affix marker starting with "@", checked with the morphology analyser:
      "@meN" "@di" "@ber" "@ter" "@peN" "@pe" "@ke"   a prefix
      "@-kan" "@-i" "@-an"                             a suffix
      "@ke-an" "@peN-an" "@per-an"                     a confix
      "@nya"                                           the -nya clitic
      "@R"                                             reduplication
A sentence uses the structure if any one marker matches.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Structure:
    id: str
    section: int
    name: str
    pattern: str
    purpose: str
    notes: str = ""
    contrast: tuple = ()
    markers: tuple = ()
    level: int = 1
    core: bool = False
    kind: str = "structure"          # "structure" or "contrast" (a pair drill)
    also_in: tuple = ()
    words: tuple = ()                # grammar words always allowed in its drills

    def used_in(self, text):
        """Does the sentence contain one of the structure's markers?
        Structures without markers can't be checked mechanically: True."""
        if not self.markers:
            return True
        return any(_marker_in(m, text) for m in self.markers)


def _marker_in(marker, text):
    if not marker.startswith("@"):
        return bool(re.search(marker, text or "", re.I))
    from malay import morphology, normalise
    want = marker[1:]
    for tok in normalise.tokens(text):
        a = morphology.analyse(tok)
        if want == "nya":
            if "nya" in a.clitics:
                return True
        elif want == "R":
            if a.reduplicated:
                return True
        elif want.startswith("-"):
            if a.suffix == want[1:]:
                return True
        elif "-" in want:
            pre, suf = want.split("-")
            if pre in a.prefixes and a.suffix == suf:
                return True
        elif want in a.prefixes:
            return True
    return False
