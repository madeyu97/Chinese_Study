# src/grammar_schema.py
"""The shape of one grammar structure (see grammar_curriculum for the fields)."""

from dataclasses import dataclass, field


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
