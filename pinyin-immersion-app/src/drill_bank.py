# src/drill_bank.py
"""
The grammar drill bank (HSK track): which structures should have a drill
set written and stored before they're needed, so a lesson never waits on
the AI.

  targets(progress, order, today)  structures to have ready, most urgent
                                   first: reviews due by `today + DAYS`
                                   (earliest first), then the next NEW_AHEAD
                                   structures not started yet, in HSK order

Filled two ways, both through ahead.write_grammar_set (which skips any
structure that already has a usable stored set):
  - every night by tools/fill_bank.py (.github/workflows/fill-drill-bank.yml),
    using what's left of the day's Groq allowance
  - while the app is open, in the background (ahead.for_day), as a backstop
"""

from datetime import timedelta

DAYS = 3            # reviews coming due within this many days
NEW_AHEAD = 10      # new structures, beyond those already started
APP_NEW_AHEAD = 6   # how far ahead the app itself writes, when it's open


def targets(progress, order, today, days=DAYS, new_ahead=NEW_AHEAD, upto=None):
    """progress: {structure id: {"next_review_date": ISO date, ...}};
    order: the HSK learning order (Structure objects or ids). With `upto`
    (the grammar level), the new ones are those the mornings will actually
    pick over `days` days - quick checks of lower levels and new lessons
    side by side (hsk_grammar.plan_lessons) - not just the next in order."""
    ids = [getattr(s, "id", s) for s in order]
    horizon = (today + timedelta(days=days)).isoformat()
    due = sorted((p.get("next_review_date") or "", sid) for sid, p in progress.items()
                 if sid in ids and (p.get("next_review_date") or "") <= horizon)
    fresh = [sid for sid in ids if sid not in progress]
    if upto is None:
        new = fresh[:new_ahead]
    else:
        import hsk_grammar as hg
        from config import HSK_GRAMMAR_CHECKS_MAX, HSK_GRAMMAR_MINUTES, HSK_GRAMMAR_NEW_MAX
        new = [sid for sid, _m in hg.plan_lessons(
            [], fresh, {}, upto, days * HSK_GRAMMAR_MINUTES, days * HSK_GRAMMAR_NEW_MAX,
            days * HSK_GRAMMAR_CHECKS_MAX)]
        new = sorted(new, key=lambda sid: hg.lesson_mode(sid, {}, upto) != "new")[:new_ahead]
    return [sid for _d, sid in due] + new
