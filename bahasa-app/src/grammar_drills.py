# src/grammar_drills.py
"""
Builds, checks, grades and schedules grammar drills.

A drill set is written fresh for each learner from the words they already
know well, so it grows as their vocabulary grows. Every set passes three
gates before it is shown:

1. Mechanical checks here: the right shape, the target structure present
   (markers: regular expressions or affix markers checked by the analyser),
   no Indonesian forms, numbers as words, and no word the learner hasn't
   studied - judged through roots, so dimakan counts as known when makan
   is - unless it is declared as an introduced word.
2. The reviewer model (a different model family from the writer) checks
   naturalness, Malaysian usage, register and every answer key.
3. Anything that fails is rewritten with the problems fed back, up to
   MAX_ATTEMPTS; a set that never passes is not shown.

Five stages per structure:
  identify     hear a sentence, pick its meaning/function
  produce      situation in English -> say it in Malay
  contrast     hear or read, tell the target apart from a look-alike
  rapid        quick prompts, answer aloud at once
  conversation natural questions answered with the structure
"""

import json
import logging
import re
import time
from datetime import date, timedelta

import llm
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from malay import known as kn, normalise

MAX_ATTEMPTS = llm.MAX_ATTEMPTS
MAX_INTRODUCED = 4

# Words any drill may use whatever the learner's list says (pronouns,
# particles, numbers, the commonest function words - see malay/known.py).
FUNCTION_WORDS = kn.FUNCTION_WORDS | kn.CORE_WORDS

STAGES = ("identify", "produce", "contrast", "rapid", "conversation")
STAGE_TITLES = {
    "identify": "Hear → identify",
    "produce": "Meaning → Malay",
    "contrast": "Contrast",
    "rapid": "Rapid retrieval",
    "conversation": "Conversation",
}
COUNTS = {"identify": (3, 5), "produce": (3, 4), "contrast": (3, 4),
          "rapid": (5, 8), "conversation": (3, 5)}
INDONESIAN_EXAMPLES = ("boleh not bisa, mahu/nak not mau, kerana not karena, wang/duit "
                       "not uang, kereta not mobil, faham not paham/mengerti, sahaja/je "
                       "not aja, beritahu not bilang, tidak/tak not nggak/gak, "
                       "sudah/dah not udah, pejabat not kantor, bilik not kamar")


# ======================================================================
# Vocabulary control
# ======================================================================
def structure_words(structure):
    """The grammar words of the structure and of the structures it is
    contrasted with (the contrast stage has to use them) - always allowed."""
    import grammar_curriculum as gc
    words = set(structure.words)
    for c in structure.contrast:
        if gc.get(c):
            words |= set(gc.get(c).words)
    return words


def allowed_set(known_words, structure, introduced=()):
    return kn.allowed_set(known_words, set(structure_words(structure)) | set(introduced))


def unknown_words(text, allowed):
    """Words in `text` the learner hasn't met (judged through roots)."""
    return kn.unknown_words(text, allowed)


# ======================================================================
# Prompt
# ======================================================================
def build_prompt(structure, known_words, indonesian_pairs=(), contrasts=(),
                 previous=(), feedback="", recent=()):
    known_list = ", ".join(sorted(known_words))
    indo = "; ".join(f"{m} not {i}" for i, m in list(indonesian_pairs)[:60])
    contrast_text = "\n".join(f"  - {c.name}: {c.pattern} — {c.purpose}" for c in contrasts) \
        or "  (none listed - pick the most commonly confused structure, or set contrast to null if none is useful)"
    prev = "\n".join(f"  - {s}" for s in list(previous)[:25])
    recent_text = ("\nRECENTLY LEARNED WORDS - recycle several of these across the items (at "
                   "least one is required), so new vocabulary gets used inside the grammar:\n  "
                   + ", ".join(recent) + "\n") if recent else ""
    kind_note = ("This is a CONTRAST DRILL: every stage should make the learner choose "
                 "between the structures listed below (use each of them across the items), "
                 "not just use one." if structure.kind == "contrast" else "")
    return f"""
You write grammar drills for an adult learning MALAYSIAN Malay (Bahasa Melayu as
Malaysians speak it: natural, everyday, conversational - NOT Indonesian).

TARGET STRUCTURE: {structure.name}
PATTERN: {structure.pattern}
PURPOSE: {structure.purpose}
TEACHING NOTES (follow these; never state them as rules to memorise):
  {structure.notes}
{kind_note}
COMMONLY CONFUSED WITH:
{contrast_text}

THE LEARNER'S WELL-STUDIED WORDS (use ONLY these, their other forms - makan ->
memakan, dimakan, makannya - plus pronouns, particles, numbers, and the grammar
words of the target structure):
{known_list}
{recent_text}
If a sentence is impossible without another word, use the simplest common word
and list it in "introduced_words" (at most {MAX_INTRODUCED}). Do not use any other
unlisted word.

MALAYSIAN, NOT INDONESIAN: {INDONESIAN_EXAMPLES}.
{("Also: " + indo + ".") if indo else ""}
Everyday speech uses colloquial forms (tak, nak, dah, ni, tu, je, kat) - use them
in conversational items; use standard forms where the situation is formal.

PRINCIPLES
- Train recognition and spontaneous use, not explanation. Explanations are one
  short plain-English line about meaning/function, no grammar jargon.
- Natural everyday sentences a Malaysian would actually say. Short (3-7 words)
  at first, a little longer towards the end of each stage.
- Vary subjects, objects, time and context across items so nothing can be
  memorised as one sentence. Do not reuse these recent sentences:
{prev or "  (none)"}
- Never describe dah/sudah as "past tense": it marks something done.
- Numbers as words, never digits. No English words inside Malay sentences. No
  names - use pronouns and roles (doktor, pesakit, kawan, abang).
- Produce and rapid prompts are situations or intentions ("You want to tell
  the patient…", "Say you've never…"), not word-for-word English to translate.
- Every sentence that is meant to use the target structure must use it.
- In multiple choice, exactly one option is correct. Options are meanings or
  functions in English. Set "read": true only when the item can't be told apart
  by ear - the text is then shown first.
{("PREVIOUS ATTEMPT WAS REJECTED. Fix every one of these problems:\n" + feedback) if feedback else ""}

Return ONLY a JSON object:
{{
  "identify": [ {{"malay": "…", "english": "…",
                  "question": "What does the speaker mean? / What is this sentence about?",
                  "options": ["…", "…", "…", "…"], "answer": 0,
                  "explain": "…", "read": false}} ],                     // 3-5 items
  "produce": [ {{"situation": "…", "answer_malay": "…", "answer_english": "…"}} ],   // 3-4
  "contrast": {{"with": "<the look-alike, in Malay>",
               "items": [ same shape as identify ]}},                    // 3-4 items, or null
  "rapid": [ {{"prompt": "…", "answer_malay": "…"}} ],                    // 5-8
  "conversation": [ {{"question_malay": "…", "question_english": "…",
                      "sample_malay": "…", "sample_english": "…"}} ],   // 3-5
  "introduced_words": [ {{"malay": "…", "english": "…"}} ]
}}
""".strip()


# ======================================================================
# Mechanical validation
# ======================================================================
FIELDS = {"identify": [("malay", True)],
          "contrast": [("malay", False)],
          "produce": [("answer_malay", True)],
          "rapid": [("answer_malay", True)],
          "conversation": [("question_malay", False), ("sample_malay", True)]}


def _check_mcq(item, where, problems):
    opts = item.get("options") or []
    if not (3 <= len(opts) <= 4) or len({str(o).strip().lower() for o in opts}) != len(opts):
        problems.append(f"{where}: needs 3-4 different options")
    ans = item.get("answer")
    if not isinstance(ans, int) or not (0 <= ans < len(opts)):
        problems.append(f"{where}: answer index out of range")


def validate(payload, structure, known_words, recent=()):
    """Returns (cleaned payload, list of problems). Empty list = passes."""
    problems = []
    known_words = list(known_words) + [w for w in recent if w not in known_words]
    if not isinstance(payload, dict):
        return payload, ["not a JSON object"]
    introduced = [w for w in (payload.get("introduced_words") or [])
                  if isinstance(w, dict) and w.get("malay")]
    payload["introduced_words"] = introduced
    if len(introduced) > MAX_INTRODUCED:
        problems.append(f"too many introduced words ({len(introduced)}); use known words")
    allowed = allowed_set(known_words, structure, [str(w["malay"]).lower() for w in introduced])

    contrast = payload.get("contrast")
    for stage in STAGES:
        items = (contrast or {}).get("items") if stage == "contrast" else payload.get(stage)
        if stage == "contrast" and not contrast:
            continue
        lo, hi = COUNTS[stage]
        if not isinstance(items, list) or not (lo <= len(items) <= hi):
            problems.append(f"{stage}: needs {lo}-{hi} items")
            continue
        for i, it in enumerate(items, 1):
            where = f"[{stage} {i}]"
            if not isinstance(it, dict):
                problems.append(f"{where}: not an object")
                continue
            for key, needs_marker in FIELDS[stage]:
                text = re.sub(r"\s+", " ", str(it.get(key) or "")).strip()
                it[key] = text
                if not text:
                    problems.append(f"{where}: empty {key}")
                    continue
                if re.search(r"\d", text):
                    problems.append(f"{where}: digits in '{text}' - write numbers as words")
                indo = normalise.indonesian_in(text)
                if indo:
                    problems.append(f"{where}: Indonesian in '{text}': "
                                    + ", ".join(f"{f} (Malaysian: {m})" for f, m in indo))
                if needs_marker and not structure.used_in(text):
                    problems.append(f"{where}: '{text}' doesn't use the target structure")
                missing = unknown_words(text, allowed)
                if missing:
                    problems.append(f"{where}: '{text}' uses unstudied words "
                                    f"{', '.join(missing)} - replace them or declare them in "
                                    f"introduced_words")
            if stage in ("identify", "contrast"):
                _check_mcq(it, where, problems)
                it["read"] = bool(it.get("read"))
            if stage in ("produce", "rapid") and not (it.get("situation") or it.get("prompt")):
                problems.append(f"{where}: missing prompt")
    if len(recent) >= 3 and not problems:
        if not kn.words_used(" ".join(sentences_in(payload)), recent):
            problems.append("none of the recently learned words is used - recycle at least one: "
                            + ", ".join(list(recent)[:10]))
    return payload, problems


# ======================================================================
# Review
# ======================================================================
def _describe_for_review(payload):
    lines = []
    for i, it in enumerate(payload.get("identify", []), 1):
        lines.append(f"[identify {i}] {it['malay']} = {it.get('english')} | Q: {it.get('question')} | "
                     f"options: {it.get('options')} | key: {it.get('answer')} | "
                     f"explain: {it.get('explain')}")
    for i, it in enumerate(payload.get("produce", []), 1):
        lines.append(f"[produce {i}] situation: {it.get('situation')} -> {it['answer_malay']}")
    c = payload.get("contrast")
    if c:
        for i, it in enumerate(c.get("items", []), 1):
            lines.append(f"[contrast {i}] (vs {c.get('with')}) {it['malay']} | "
                         f"Q: {it.get('question')} | options: {it.get('options')} | "
                         f"key: {it.get('answer')} | explain: {it.get('explain')}")
    for i, it in enumerate(payload.get("rapid", []), 1):
        lines.append(f"[rapid {i}] {it.get('prompt')} -> {it['answer_malay']}")
    for i, it in enumerate(payload.get("conversation", []), 1):
        lines.append(f"[conversation {i}] Q: {it['question_malay']} -> sample: {it['sample_malay']}")
    return "\n".join(lines)


def review(payload, structure):
    """Second model checks naturalness, Malaysian usage and answer keys.
    Returns (acceptable, problems, reviewed). If both models are unreachable
    it lets the set through but reports reviewed=False, so it is shown once
    and never stored for reuse."""
    prompt = f"""
You are a strict native-speaker reviewer of MALAYSIAN Malay teaching material.

TARGET STRUCTURE: {structure.name} — {structure.pattern}
WHAT IT SHOULD TEACH: {structure.purpose} {structure.notes}

Check every item below:
1. Natural, grammatical, everyday Malay a Malaysian would say. Colloquial forms
   (tak, nak, dah, ni, tu, je, kat, lah, kan) are correct, not errors.
2. Malaysian, not Indonesian: flag any Indonesian word, spelling or usage
   ({INDONESIAN_EXAMPLES}).
3. Items meant to use the target structure use it correctly, with the right
   affixes.
4. Multiple choice: exactly one option is right and the key points to it.
5. Situations/prompts would naturally lead to the given answer.
6. Contrast items genuinely hinge on the difference; explanations are
   accurate. dah/sudah must never be explained as simply "past tense".

DRILLS:
{_describe_for_review(payload)}

Return ONLY JSON: {{"acceptable": true/false,
 "problems": ["<item label>: <problem and fix>", ...]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = llm.chat_json(model, prompt, 0)
            probs = [str(p) for p in (v.get("problems") or []) if str(p).strip()]
            return bool(v.get("acceptable", False)) and not probs, probs, True
        except Exception as e:
            logging.warning(f"[GRAMMAR REVIEW] {model} failed: {e}")
    return True, [], False


def generate(structure, known_words, indonesian_pairs=(), contrasts=(), previous=(), recent=()):
    """Write, check and review a drill set. Returns the payload or None."""
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = build_prompt(structure, known_words, indonesian_pairs, contrasts,
                              previous, feedback, recent)
        try:
            payload = llm.chat_json(GENERATION_MODEL, prompt, 0.7)
        except json.JSONDecodeError as e:
            feedback = f"- output was not valid JSON ({e})"
            logging.warning(f"[GRAMMAR] attempt {attempt}: {feedback}")
            continue
        except Exception as e:
            # API trouble (rate limit, timeout): wait and try again rather
            # than burning every attempt in the same second.
            logging.warning(f"[GRAMMAR] attempt {attempt}: API error {e}")
            time.sleep(min(20, 5 * attempt))
            continue
        payload, problems = validate(payload, structure, known_words, recent)
        if not problems:
            ok, problems, reviewed = review(payload, structure)
            if ok:
                payload["structure_id"] = structure.id
                payload["reviewed"] = reviewed
                return payload
        feedback = "\n".join(f"- {p}" for p in problems[:15])
        logging.warning(f"[GRAMMAR] {structure.id} attempt {attempt} rejected:\n{feedback}")
    return None


def sentences_in(payload):
    """Every Malay sentence in a set - fed back so the next set differs."""
    out = [it.get("malay") for it in payload.get("identify", [])]
    out += [it.get("answer_malay") for it in payload.get("produce", [])]
    out += [it.get("answer_malay") for it in payload.get("rapid", [])]
    out += [it.get("sample_malay") for it in payload.get("conversation", [])]
    out += [it.get("malay") for it in (payload.get("contrast") or {}).get("items", [])]
    return [s for s in out if s]


# ======================================================================
# Grading spoken / typed answers
# ======================================================================
def grade_answer(structure, task, reference, learner_text, spoken=True):
    """Judge a produced answer. Returns {"verdict": correct|close|wrong,
    "feedback": str, "better": str}. An answer equal to the reference up to
    register (tak = tidak) is correct without asking the model."""
    if not (learner_text or "").strip():
        return {"verdict": "wrong", "feedback": "Nothing was heard - try again aloud.",
                "better": reference}
    said = normalise.clean_transcript(learner_text) if spoken else learner_text
    if normalise.same(said, reference):
        return {"verdict": "correct", "feedback": "", "better": reference}
    prompt = f"""
You are a warm but exact tutor of MALAYSIAN Malay. The learner is practising:
{structure.name} ({structure.pattern}) - {structure.purpose}

TASK: {task}
A GOOD ANSWER (one of many): {reference}
LEARNER SAID: {said}
{"(This is a speech transcription: ignore spelling and punctuation; Whisper often writes colloquial speech in standard spelling.)" if spoken else ""}

Colloquial and standard forms are equally correct (tak = tidak, nak = hendak,
dah = sudah). Indonesian words or usage are not correct.

Verdict:
 "correct" - natural Malay, fits the task, and uses the target structure
             correctly (other wordings are fine);
 "close"   - meaning right but a small error, or the structure was avoided;
 "wrong"   - wrong meaning or ungrammatical.
Feedback: at most two short sentences about meaning and function, no jargon.
"better": a natural Malaysian version using the structure (the learner's own
words where possible).

Return ONLY JSON: {{"verdict": "...", "feedback": "...", "better": "..."}}
""".strip()
    try:
        v = llm.chat_json(GRADING_MODEL, prompt, 0.2)
        verdict = v.get("verdict") if v.get("verdict") in ("correct", "close", "wrong") else "close"
        return {"verdict": verdict, "feedback": str(v.get("feedback") or ""),
                "better": str(v.get("better") or reference)}
    except Exception as e:
        logging.warning(f"[GRAMMAR GRADE] failed: {e}")
        return {"verdict": "ungraded", "feedback": "Couldn't grade this one "
                "automatically - compare with the model answer (it won't count "
                "against you).", "better": reference}


# ======================================================================
# Scheduling
# ======================================================================
POINTS = {"correct": 1.0, "close": 0.5, "wrong": 0.0,
          "got": 1.0, "nearly": 0.5, "missed": 0.0, True: 1.0, False: 0.0}


def session_grade(results):
    """results: list of verdict values from all stages -> SRS grade 0-3."""
    pts = [POINTS.get(r, 0.0) for r in results]
    if not pts:
        return 0, 0.0
    score = sum(pts) / len(pts)
    grade = 0 if score < 0.5 else 1 if score < 0.7 else 2 if score < 0.9 else 3
    return grade, round(score, 3)


def schedule(interval, ease, grade, core=False, today=None):
    """Same spacing as the vocabulary SRS; core structures are capped at a
    shorter interval so they keep coming back."""
    today = today or date.today()
    ease = ease or 2.5
    if grade == 0:
        ease, interval = max(1.3, ease - 0.2), 0
    else:
        if grade == 1:
            ease = max(1.3, ease - 0.15)
        elif grade == 3:
            ease = ease + 0.15
        if not interval:
            interval = 1
        elif interval == 1:
            interval = 3
        else:
            factor = {1: 1.2, 2: ease, 3: ease * 1.3}[grade]
            interval = max(interval + 1, int(interval * factor))
    interval = min(interval, 21 if core else 90)
    nxt = today + timedelta(days=max(interval, 1) if grade else 0)
    return interval, round(ease, 2), nxt.isoformat()


def todays_queue(curriculum_order, progress, today, new_so_far, new_per_day):
    """Due structures first (core first, then oldest), then new ones in
    learning order up to the day's allowance."""
    today_s = today.isoformat() if hasattr(today, "isoformat") else str(today)
    due = [s for s in curriculum_order
           if s.id in progress and (progress[s.id].get("next_review_date") or "") <= today_s]
    due.sort(key=lambda s: (not s.core, progress[s.id].get("next_review_date") or "", s.level))
    fresh = [s for s in curriculum_order if s.id not in progress]
    return due + fresh[:max(0, new_per_day - new_so_far)]
