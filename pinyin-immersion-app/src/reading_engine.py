"""
Reading practice, bounded by what you can already write.

The premise: characters you have drilled in the handwriting section are
characters you know. So sentences here are built ONLY from those, letting
you meet them in ordinary computer type rather than as calligraphy - which
is a genuinely different recognition skill.

Two rules make it work:

  * A sentence is only shown if (nearly) every character in it is one you
    have studied. A small allowance of unknown characters is permitted,
    because Chinese is hard to write naturally from a set of sixty-five
    characters, and those few always show their pinyin.
  * Characters you HAVE studied show no pinyin unless you tap them. That's
    the point: you should be recalling, not reading off a transcription.

Generation is checked deterministically after the fact. The model is told
which characters it may use, then the result is verified character by
character and regenerated if it strayed - the same pattern the sentence
pipeline uses elsewhere in this app, because a model asked to restrict
itself to a character set will not reliably do so.
"""

import json
import logging
import re

from dictionary_engine import derive_pinyin, cedict_gloss, is_cjk_char

# Punctuation that doesn't count against the character budget.
_PUNCT = "。，、？！：；「」『』（）,.?!:;\"'()… \n\u3000"

MAX_UNKNOWN_DEFAULT = 3


def analyse(sentence, known):
    """Split a sentence into known / unknown characters."""
    chars = [c for c in sentence if is_cjk_char(c)]
    unknown = [c for c in chars if c not in known]
    return {"total": len(chars), "unknown": unknown,
            "unknown_count": len(set(unknown)),
            "coverage": (1 - len(unknown) / len(chars)) if chars else 0.0}


def annotate(sentence, known):
    """Per-character detail for rendering.

    Each entry: {char, pinyin, known, gloss}. Punctuation passes through
    with known=True so it never draws attention.
    """
    out = []
    pinyins = None
    try:
        from dictionary_engine import _char_pinyin_list
        pinyins = _char_pinyin_list(sentence)
    except Exception:
        pass
    for i, ch in enumerate(sentence):
        if not is_cjk_char(ch):
            out.append({"char": ch, "pinyin": "", "known": True, "gloss": ""})
            continue
        py = pinyins[i] if pinyins and i < len(pinyins) else derive_pinyin(ch)
        gloss = ""
        try:
            gloss = (cedict_gloss(ch)[0] or "").split(" / ")[0]
        except Exception:
            pass
        out.append({"char": ch, "pinyin": py,
                    "known": ch in known, "gloss": gloss})
    return out


def build_prompt(known_chars, topic, max_unknown, previous_problem="",
                 focus=None):
    sample = "".join(sorted(known_chars))
    focus_line = ""
    if focus:
        focus_line = (
            f"\nBUILD THE SENTENCE AROUND THESE if you naturally can - they "
            f"are what the learner is working on right now:\n"
            f"{''.join(focus)}\n")
    retry = ""
    if previous_problem:
        retry = (f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {previous_problem}\n"
                 f"Try again, staying inside the allowed characters.\n")
    return f"""
You are writing reading practice for a learner of Mandarin who knows a
limited set of characters.

ALLOWED CHARACTERS ({len(known_chars)} of them):
{sample}

Write ONE natural, everyday Chinese sentence.

HOW TO USE THE LIST:
The list is a PREFERENCE, not a cage. A natural sentence that borrows a
couple of characters is useful practice; a sentence that obeys the list but
means nothing is worthless and will be rejected.

RULES:
1. Prefer the allowed characters. Aim to build the sentence from them.
2. You may use up to {max_unknown} characters from outside the list. If the
   only way to say something natural needs one or two more than that, say
   the natural thing anyway and keep it as short as possible - a rejected
   sentence helps nobody.
3. MEANING COMES FIRST. The sentence must be something a real person would
   actually say. If you cannot say anything natural with these characters,
   USE MORE UNKNOWN CHARACTERS - that is far better than nonsense. A
   reviewer will reject strings of characters that do not form real words.
4. Between 4 and 14 characters long.
5. Simplified characters only.
6. Punctuation is free - it doesn't count.
{f"7. If you can, make it about: {topic}" if topic else ""}
{focus_line}{retry}
Return ONLY raw JSON:
{{"chinese": "<the sentence>", "english": "<natural translation>"}}
""".strip()


def segments_ok(sentence):
    """Retired.

    This tried to spot gibberish by checking whether jieba found real
    multi-character words. Measured against actual cases it was wrong in
    both directions: jieba happily segments 我天, 不个 and 水天 as "words"
    (so nonsense passed), while a perfectly natural short sentence like
    你有水吗？ contains no multi-character word at all (so it failed).

    Judging whether a sentence means anything needs a language model, not a
    segmentation heuristic - review_sentence does that job. Kept as a
    no-op so callers and tests stay valid.
    """
    return True, ""


def review_sentence(client, model, sentence, english):
    """Second-pass native-speaker check, mirroring the main app's reviewer.

    Restricting the character set pushes hard against natural phrasing, so
    a model will happily produce grammatical-looking nonsense to satisfy
    the constraint. Verifying the CONSTRAINT is not the same as verifying
    the SENTENCE, which is what this does.
    """
    prompt = f"""
You are a strict native speaker of Mandarin reviewing material written for
a learner.

SENTENCE: {sentence}
CLAIMED MEANING: {english}

Answer honestly - this sentence was produced under a restricted character
set, so it may well be unnatural.

Reject it if ANY of these is true:
- it is not something a real person would say
- the words do not combine into a coherent statement
- it is grammatically broken
- it reads as characters strung together to fill a quota
- the English does not match the Chinese

Return ONLY raw JSON:
{{"ok": true/false, "why": "<short reason if not ok>"}}
""".strip()
    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model, response_format={"type": "json_object"},
            temperature=0)
        v = json.loads(resp.choices[0].message.content)
        return bool(v.get("ok", True)), str(v.get("why", "") or "")
    except Exception as e:
        logging.warning(f"[READ] review unavailable ({e}) - accepting")
        return True, ""


def generate_sentence(client, model, known_chars, topic="",
                      max_unknown=MAX_UNKNOWN_DEFAULT, attempts=3,
                      focus=None):
    """Generate one sentence, verified against the allowed character set.

    Returns (sentence, english, report) or (None, None, report).
    The report explains what happened, so the UI can be honest when the
    known set is simply too small for a natural sentence.
    """
    known = set(known_chars)
    problem = ""
    best = None
    for attempt in range(1, attempts + 1):
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "user",
                           "content": build_prompt(known, topic, max_unknown,
                                                   problem, focus)}],
                model=model,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            logging.error(f"[READ] generation failed: {e}")
            return None, None, f"Generation failed: {e}"

        sentence = (data.get("chinese") or "").strip()
        english = (data.get("english") or "").strip()
        if not sentence:
            problem = "empty sentence"
            continue

        stats = analyse(sentence, known)
        if stats["total"] < 3:
            problem = "sentence too short"
            continue
        # A natural sentence one character over the allowance beats a
        # compliant sentence that means nothing, so allow a small overshoot
        # on the final attempt - but only if it survives review.
        tolerance = max_unknown + (1 if attempt == attempts else 0)
        if stats["unknown_count"] <= tolerance:
            ok_sense, why = review_sentence(client, model, sentence, english)
            if not ok_sense:
                problem = f"a native speaker rejected it: {why}"
                logging.info(f"[READ] attempt {attempt} rejected: {why}")
                continue
            used = [c for c in (focus or []) if c in sentence]
            note = (f"{stats['total']} characters, "
                    f"{stats['unknown_count']} outside your set")
            if stats["unknown_count"] > max_unknown:
                note += " (one over, to keep it natural)"
            if used:
                note += f" - practising {''.join(used)}"
            return sentence, english, note
        # keep the closest attempt in case every try overshoots
        if best is None or stats["unknown_count"] < best[2]["unknown_count"]:
            best = (sentence, english, stats)
        problem = (f"used {stats['unknown_count']} characters outside the "
                   f"allowed set ({''.join(sorted(set(stats['unknown'])))}), "
                   f"limit is {max_unknown}")
        logging.info(f"[READ] attempt {attempt}: {problem}")

    if best:
        sentence, english, stats = best
        # Only offer a near-miss if it is at least real Chinese; a sentence
        # that failed the sense check must never be shown as practice.
        ok_sense, _ = review_sentence(client, model, sentence, english)
        if ok_sense:
            return sentence, english, (
                f"Closest attempt: {stats['unknown_count']} characters "
                f"outside your set. Learn a few more and these get easier.")
    return None, None, (
        "Couldn't write a natural sentence from those characters yet. "
        "Try allowing a few more new characters, or learn a handful more "
        "first - very small character sets make natural Chinese hard.")
