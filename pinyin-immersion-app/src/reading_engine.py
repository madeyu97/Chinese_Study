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

RULES:
1. Use the allowed characters above wherever possible.
2. You may use AT MOST {max_unknown} characters from outside that list, and
   only if the sentence would be impossible otherwise. Fewer is better.
3. The sentence must be grammatical, natural modern Mandarin that a real
   person would say. Never string characters together just to satisfy the
   list - a nonsense sentence is worse than an extra unknown character.
4. Between 4 and 14 characters long.
5. Simplified characters only.
6. Punctuation is free - it doesn't count.
{f"7. If you can, make it about: {topic}" if topic else ""}
{focus_line}{retry}
Return ONLY raw JSON:
{{"chinese": "<the sentence>", "english": "<natural translation>"}}
""".strip()


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
        if stats["unknown_count"] <= max_unknown:
            used = [c for c in (focus or []) if c in sentence]
            note = (f"{stats['total']} characters, "
                    f"{stats['unknown_count']} outside your set")
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
        return sentence, english, (
            f"Closest attempt: {stats['unknown_count']} characters outside "
            f"your set. Learn a few more and these get easier.")
    return None, None, "Couldn't build a sentence from those characters yet."
