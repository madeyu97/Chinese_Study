# src/vocab_engine.py
"""
The vocabulary learning engine.

Every word has two separate skills, each with its own spaced-repetition
schedule:
  recognition  - understanding it: Chinese -> meaning, audio -> meaning
  production   - using it: cloze, meaning -> Chinese, spoken production

Production of a word only starts once it is recognised reliably, and
China-tagged words (mainland usage) are learned for recognition only, after
their Malaysian partner.

Sessions are built so new words never swamp the learner: a small cap per
session and per day, shrinking to nothing when reviews pile up. A new word is
met in context, retrieved straight away, and retrieved again a few items later
in the same session. Retrieval modes rotate, lean towards the modes the
learner misses most, and harden (cloze -> meaning -> free speech) as a word
strengthens.

Everything here is pure logic; db_manager supplies the data.
"""

import random
import re
from datetime import date, timedelta

RECOGNITION, PRODUCTION = "recognition", "production"
REC_MODES = ("zh_to_meaning", "audio_to_meaning")
PROD_MODES = ("cloze", "meaning_to_zh", "spoken")
MODE_TITLES = {
    "zh_to_meaning": "Read → meaning",
    "audio_to_meaning": "Listen → meaning",
    "cloze": "Fill the gap",
    "meaning_to_zh": "Meaning → Chinese",
    "spoken": "Say it in a sentence",
}
MODE_SKILL = {m: RECOGNITION for m in REC_MODES} | {m: PRODUCTION for m in PROD_MODES}
GRADES = {"wrong": 0, "close": 1, "correct": 2, "easy": 3}

# A word's recognition must be this solid before production starts.
UNLOCK_MIN_INTERVAL = 3
UNLOCK_MIN_STREAK = 2
MAX_INTERVAL = 365


# ======================================================================
# Scheduling
# ======================================================================
def update_track(track, result, today=None):
    """Apply one retrieval result to a skill track. Returns a new dict.
    'ungraded' leaves the track untouched."""
    today = today or date.today()
    track = dict(track or {})
    if result not in GRADES:
        return track
    grade = GRADES[result]
    interval = track.get("interval") or 0
    ease = track.get("ease") or 2.5
    was_learned = interval >= 1
    if grade == 0:
        ease = max(1.3, ease - 0.2)
        interval = 0
        track["streak"] = 0
        if was_learned:
            track["lapses"] = (track.get("lapses") or 0) + 1
    else:
        if grade == 1:
            ease = max(1.3, ease - 0.15)
        elif grade == 3:
            ease += 0.15
        if interval == 0:
            interval = 1
        elif interval == 1:
            interval = 3 if grade >= 2 else 2
        else:
            factor = {1: 1.2, 2: ease, 3: ease * 1.3}[grade]
            interval = max(interval + 1, int(interval * factor))
        track["streak"] = (track.get("streak") or 0) + 1
    track["interval"] = min(interval, MAX_INTERVAL)
    track["ease"] = round(ease, 2)
    track["reps"] = (track.get("reps") or 0) + 1
    track["last_result"] = result
    track["next_review_date"] = (today + timedelta(days=track["interval"])).isoformat()
    return track


def can_produce(word):
    """Production practice is for real words the learner should say:
    Chinese, short, and not a mainland-only form."""
    zh = word.get("chinese") or ""
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{1,6}", zh)) and word.get("tag") != "China"


def production_ready(rec_track):
    return bool(rec_track) and (rec_track.get("interval") or 0) >= UNLOCK_MIN_INTERVAL \
        and (rec_track.get("streak") or 0) >= UNLOCK_MIN_STREAK


# ======================================================================
# Retrieval mode
# ======================================================================
def choose_mode(skill, track=None, mode_errors=None, rng=None, step=None):
    """Pick how to test this item.

    New words: step 1 reads (Chinese -> meaning), step 2 listens.
    Production hardens with the streak: cloze first, then meaning -> Chinese,
    then free speaking. The mode last used for this word is avoided, and
    modes the learner misses more often are weighted up."""
    rng = rng or random
    mode_errors = mode_errors or {}
    if skill == RECOGNITION:
        if step == 1:
            return "zh_to_meaning"
        if step == 2:
            return "audio_to_meaning"
        options = list(REC_MODES)
    else:
        streak = (track or {}).get("streak") or 0
        if streak <= 1:
            options = ["cloze"]
        elif streak <= 3:
            options = ["cloze", "meaning_to_zh"]
        else:
            options = ["meaning_to_zh", "spoken", "cloze"]
    last = (track or {}).get("last_mode")
    if len(options) > 1 and last in options:
        options.remove(last)
    weights = [1.0 + 2.0 * mode_errors.get(m, 0.0) for m in options]
    return rng.choices(options, weights)[0]


# ======================================================================
# How much new material
# ======================================================================
def new_word_allowance(due_count, introduced_today, per_session, per_day, backlog_soft):
    """New words allowed this session: within the session and daily caps,
    scaled down as the review backlog grows past `backlog_soft`, reaching
    zero at twice that."""
    room = max(0, min(per_session, per_day - introduced_today))
    if due_count > backlog_soft:
        scale = max(0.0, 1 - (due_count - backlog_soft) / backlog_soft)
        room = int(room * scale)
    return room


def pick_new_words(lesson_candidates, frequency_candidates, n, lesson_share=0.4):
    """Mix new words from your lessons into the frequency order: roughly
    `lesson_share` of the new words come from your lesson list."""
    out, li, fi = [], 0, 0
    seen = set()
    while len(out) < n and (li < len(lesson_candidates) or fi < len(frequency_candidates)):
        lessons_due = li < len(lesson_candidates) and (
            fi >= len(frequency_candidates)
            or (len([w for w in out if w.get("from_lessons")]) < round((len(out) + 1) * lesson_share)))
        w = lesson_candidates[li] if lessons_due else frequency_candidates[fi]
        if lessons_due:
            li += 1
        else:
            fi += 1
        if w["id"] not in seen:
            seen.add(w["id"])
            out.append(w)
    return out


# ======================================================================
# Session
# ======================================================================
def build_session(due_recognition, due_production, unlockable, new_words,
                  max_reviews, max_unlocks, mode_errors=None, tracks=None, rng=None):
    """Lay out one session.

    due_* / unlockable / new_words are lists of word dicts (id, chinese,
    pinyin, english, tag, ...). tracks maps (vocab_id, skill) -> track.
    Returns a list of items: {word, skill, mode, kind} where kind is
    'review', 'unlock' (first production practice), 'new' (introduce + first
    retrieval) or 'step2' (the same new word again, later in the session)."""
    rng = rng or random.Random()
    tracks = tracks or {}
    reviews = []
    rq, pq = list(due_recognition), list(due_production)
    while (rq or pq) and len(reviews) < max_reviews:
        # interleave the two skills so neither dominates a stretch
        for q, skill in ((rq, RECOGNITION), (pq, PRODUCTION)):
            if q and len(reviews) < max_reviews:
                w = q.pop(0)
                reviews.append({"word": w, "skill": skill, "kind": "review",
                                "mode": choose_mode(skill, tracks.get((w["id"], skill)),
                                                    mode_errors, rng)})
    unlocks = [{"word": w, "skill": PRODUCTION, "kind": "unlock", "mode": "cloze"}
               for w in unlockable[:max_unlocks]]

    items = reviews[:3]                      # warm up on familiar material
    rest = reviews[3:] + unlocks
    rng.shuffle(rest)
    for w in new_words:
        items.append({"word": w, "skill": RECOGNITION, "kind": "new", "mode": "zh_to_meaning"})
        for _ in range(3):                    # other items between new words
            if rest:
                items.append(rest.pop(0))
    items += rest
    # the second look at each new word comes at least four items later
    for w in new_words:
        intro = next(i for i, it in enumerate(items)
                     if it["kind"] == "new" and it["word"]["id"] == w["id"])
        items.insert(min(intro + 5, len(items)),
                     {"word": w, "skill": RECOGNITION, "kind": "step2",
                      "mode": "audio_to_meaning"})
    return items


def requeue_position(items, current_index, gap=4):
    """Where to put a missed item so it comes back later in the session."""
    return min(len(items), current_index + 1 + gap)
