# src/word_content.py
"""
What each word is learned THROUGH: never the word alone.

For every word the learner studies, a small content set is written from
words they already know plus the target, so each sentence adds one new
thing:

  meaning      the core meaning, as used in the examples
  chunks       2-4 high-frequency collocations the word lives in (minta tolong)
  sentences    4 short natural sentences, favouring the grammar structures
               the learner is practising (tagged by structure id; Phase 4)
  confusables  words learners mix it up with, with the difference
  prompts      situations for spoken production, with a sample answer

It is checked mechanically (target present, only known words, no
Indonesian forms, structure markers present) and then by a reviewer model
from a different family. Up to three rewrites get the problems fed back.

This module also builds the multiple-choice options. Wrong options are never
random: each is labelled - same ROOT (makan / makanan), SOUND-alike (bawa /
bawah), similar MEANING, or the Indonesian FALSE FRIEND meaning (senang =
easy, not happy) - so the option a learner picks feeds the diagnosis of why
a word is missed. Typed and spoken answers are marked by malay/checker.py.
"""

import logging
import random
import re

import llm
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from malay import checker, known as kn, morphology, normalise

MAX_INTRODUCED = 1
MAX_SENTENCE_WORDS = 14
CLITICS = ("nya", "lah", "kah", "pun", "ku", "mu")


# ======================================================================
# Meanings and target handling
# ======================================================================
def short_meaning(english, limit=40):
    """The first sense of a gloss, without notes:
    'can (Indonesian) / venom (Malay)' -> 'can'; 'I / me (polite)' -> 'I'."""
    text = (english or "").strip()
    first = re.split(r"\s*/\s*|;\s*", text)[0]
    first = re.sub(r"\s*\([^)]*\)", "", first).strip(" ,")
    if not first:          # a gloss that is all note: '(lambat laun = sooner or later)'
        inner = re.search(r"\(([^)]*)\)", text)
        first = (inner.group(1) if inner else text).strip()
    return first[:limit].rstrip(" ,")


def _target_re(target):
    """Whole-word match for the target, with an optional clitic and the
    '2' reduplication shorthand left aside: makan, makannya, Makan."""
    t = re.escape(target.lower()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![\w-])({t})((?:{'|'.join(CLITICS)})?)(?![\w-])", re.I)


def contains(text, target):
    return bool(_target_re(target).search(text or ""))


def marked(text, target, style):
    """The sentence with the target wrapped in a highlight span."""
    return _target_re(target).sub(
        lambda m: f"<span style='{style}'>{m.group(1)}</span>{m.group(2)}", text, count=1)


def cloze(text, target):
    """The sentence with the target blanked once: Saya makan nasi -> Saya ＿＿＿ nasi."""
    return _target_re(target).sub(lambda m: "＿＿＿" + m.group(2), text, count=1)


# ======================================================================
# Typed and spoken answers
# ======================================================================
RESULT = {checker.CORRECT: "correct", checker.CLOSE_AFFIX: "close",
          checker.CLOSE_SPELLING: "close", checker.CLOSE_INDONESIAN: "close",
          checker.WRONG: "wrong"}


def check_answer(answer, target, accept=(), spoken=False):
    """Judge a typed or transcribed production answer.

    Returns (result, detail). result: correct / close / wrong. detail
    carries the checker's verdict and note, plus the flags the diagnosis
    reads: affix_error, spelling_error, indonesian."""
    said = normalise.clean_transcript(answer) if spoken else (answer or "").strip()
    c = checker.check_answer(said, target, accept)
    detail = {"typed": answer or "", "verdict": c.verdict, "note": c.note}
    if c.verdict == checker.CLOSE_AFFIX:
        detail["affix_error"] = True
    elif c.verdict == checker.CLOSE_SPELLING:
        if spoken:      # speech can't misspell: Whisper chose the letters
            return "correct", {**detail, "verdict": checker.CORRECT, "note": ""}
        detail["spelling_error"] = True
    elif c.verdict == checker.CLOSE_INDONESIAN:
        detail["indonesian"] = normalise.tokens(said)[0] if normalise.tokens(said) else said
    return RESULT[c.verdict], detail


# ======================================================================
# Diagnostic multiple-choice options
# ======================================================================
def sounds_alike(a, b):
    """bawa / bawah, tahu / tahun: one letter apart (two on long words)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    limit = 1 if max(len(a), len(b)) <= 6 else 2
    return checker.distance(a, b) <= limit


def _root(w):
    return (w.get("root") or w.get("malay") or "").lower()


def meaning_options(word, pool, confusables=(), n=3, rng=None, audio=False):
    """Options for 'what does it mean?': the right meaning plus up to n wrong
    ones, each labelled for diagnosis:
      meaning       a word commonly confused in meaning
      false_friend  the meaning the word has in Indonesian (senang: happy)
      root          another word from the same root (makan / makanan)
      sound         one or two letters apart (bawa / bawah)
      other         filler from the learner's words
    Groups take turns, so one kind never fills every slot.

    pool: word dicts (malay, english, root) - ideally words the learner has
    met, so the options are plausible."""
    rng = rng or random.Random()
    target = word["malay"]
    right = short_meaning(word["english"])
    seen = {right.lower()}
    picks = {"meaning": [], "false_friend": [], "root": [], "sound": [], "other": []}
    by_ms = {w["malay"]: w for w in pool}
    for c in confusables or ():
        w = by_ms.get((c.get("malay") or "").lower())
        if w and w["malay"] != target:
            picks["meaning"].append(w)
    ff = normalise.false_friend(target)
    if ff:
        picks["false_friend"].append({"malay": target, "english": ff})
    root = _root(word)
    for w in pool:
        if w["malay"] == target or " " in w["malay"]:
            continue
        if _root(w) == root:
            picks["root"].append(w)
        elif sounds_alike(target, w["malay"]):
            picks["sound"].append(w)
    others = [w for w in pool if w["malay"] != target]
    rng.shuffle(others)
    picks["other"] = others[:40]
    for kind in ("meaning", "root", "sound"):
        rng.shuffle(picks[kind])
    options, order = [], ("meaning", "false_friend", "root", "sound")
    while len(options) < n and any(picks[k] for k in order):
        for kind in order:
            while picks[kind] and len(options) < n:
                w = picks[kind].pop(0)
                m = short_meaning(w["english"])
                if m and m.lower() not in seen:
                    seen.add(m.lower())
                    options.append({"text": m, "kind": kind, "malay": w["malay"]})
                    break
    for w in picks["other"]:
        if len(options) >= n:
            break
        m = short_meaning(w["english"])
        if m and m.lower() not in seen:
            seen.add(m.lower())
            options.append({"text": m, "kind": "other", "malay": w["malay"]})
    options.append({"text": right, "kind": "correct", "malay": target})
    rng.shuffle(options)
    return options


# ======================================================================
# Word-by-word breakdown (from the analyser and the glossed list, never
# from the model)
# ======================================================================
def breakdown(text, glosses):
    """[(word, parts, gloss)] for a sentence. glosses: malay -> english for
    the sentence's words and their roots (db.glosses_for)."""
    out = []
    for tok in dict.fromkeys(normalise.tokens(text)):
        a = morphology.analyse(tok)
        parts = ""
        if a.root != tok or a.affix_label:
            parts = f"{a.root} {a.affix_label}".strip()
        base = morphology.attach(a.root, a.prefixes, a.suffix) if a.clitics else tok
        gloss = glosses.get(tok) or glosses.get(base) or glosses.get(a.root) or ""
        std = normalise.standard_of(tok)
        if std and std != tok:
            gloss = gloss or glosses.get(std, "")
            parts = parts or f"= {std}"          # tak -> = tidak
        out.append((tok, parts, short_meaning(gloss) if gloss else ""))
    return out


# ======================================================================
# Writing the content
# ======================================================================
INDONESIAN_EXAMPLES = ("boleh not bisa, mahu/nak not mau, kerana not karena, wang/duit "
                       "not uang, kereta not mobil, faham not paham/mengerti, sahaja/je "
                       "not aja, beritahu not bilang, tidak/tak not nggak/gak, "
                       "sudah/dah not udah")


def _register_line(word):
    reg = word.get("register") or "standard"
    std = normalise.standard_of(word["malay"])
    if reg == "colloquial":
        return (f"This is a COLLOQUIAL word" + (f" (standard form: {std})" if std else "")
                + ": use it in casual everyday speech.")
    if reg == "formal":
        return "This is a FORMAL word: use it in formal or written contexts (news, notices, speeches)."
    return "Standard word: everyday contexts."


def build_prompt(word, known_words, structures=(), feedback="", recent=()):
    target = word["malay"]
    known = ", ".join(sorted(set(known_words) - {target}))
    grammar = "\n".join(f"  - [{s.id}] {s.name}: {s.pattern}" for s in structures)
    grammar_block = ("\nGRAMMAR THE LEARNER IS PRACTISING - at least one sentence MUST use one of "
                     "these (naturally), with its id in \"structure\"; the other sentences may too "
                     "(otherwise null):\n" + grammar + "\n") if structures else ""
    morph = f"{word.get('root')} + {word.get('affixes')}" if word.get("affixes") else ""
    return f"""
You write study material for ONE word, for an adult learning MALAYSIAN Malay
(Bahasa Melayu as people speak it in Malaysia - NOT Indonesian).

TARGET WORD: {target} - {short_meaning(word['english'])}
FULL GLOSS: {word['english']}
{("PARTS: " + morph) if morph else ""}
{_register_line(word)}

THE LEARNER ALREADY KNOWS (use ONLY these words, the target, and common
function words: pronouns, prepositions, negation, question words, numbers,
particles). Other forms of a known word are fine: makan -> memakan, dimakan,
makannya. Every sentence should add exactly one new thing, the target:
{known or "(almost nothing yet - keep sentences very short)"}
If a sentence is impossible otherwise, you may use ONE extra simple word and
list it in "introduced_words".
{grammar_block}{("RECENTLY LEARNED WORDS - reuse some where natural, so new words keep "
                 "meeting each other: " + ", ".join(recent)) if recent else ""}

Write:
- "meaning": the core meaning in 2-6 English words, as used in your examples.
- "chunks": 2-4 high-frequency collocations containing the target exactly
  (e.g. for tolong: "minta tolong", "tolong saya"), with English.
- "sentences": 4 short natural sentences (4-12 words), each containing the
  target exactly once, varied in subject and situation, with English.
- "confusables": 1-3 Malay words learners commonly confuse with the target
  (similar meaning, same root, or a false friend), each with a one-line
  plain-English difference.
- "prompts": 2 situations (in English, "You want to…") where the learner would
  naturally say something with the target, each with a short Malay sample
  answer and its English.

Rules:
- Malaysian Malay only, never Indonesian words or usage: {INDONESIAN_EXAMPLES}.
- Natural everyday speech: colloquial forms (tak, nak, dah, ni, tu, je) are
  welcome where a Malaysian would say them.
- Numbers as words, never digits. No English words or names inside the Malay.
{("PREVIOUS ATTEMPT WAS REJECTED. Fix every one of these:\n" + feedback) if feedback else ""}

Return ONLY JSON:
{{"meaning": "…",
 "chunks": [{{"malay": "…", "english": "…"}}],
 "sentences": [{{"malay": "…", "english": "…", "structure": null}}],
 "confusables": [{{"malay": "…", "difference": "…"}}],
 "prompts": [{{"situation": "…", "sample_malay": "…", "sample_english": "…"}}],
 "introduced_words": [{{"malay": "…", "english": "…"}}]}}
""".strip()


def validate(content, word, known_words, structures=()):
    problems = []
    if not isinstance(content, dict):
        return content, ["not a JSON object"]
    target = word["malay"]
    recognise_only = bool(word.get("tag"))
    introduced = [w for w in (content.get("introduced_words") or [])
                  if isinstance(w, dict) and w.get("malay")]
    content["introduced_words"] = introduced
    if len(introduced) > MAX_INTRODUCED:
        problems.append("more than one introduced word - use known words")
    extra = [target] + [str(w["malay"]).lower() for w in introduced]
    allowed = kn.allowed_set(known_words, extra)
    own = {target} if recognise_only else set()
    by_id = {s.id: s for s in structures}
    if not str(content.get("meaning") or "").strip():
        problems.append("missing meaning")

    def check_ms(text, where, need_target=True):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            problems.append(f"{where}: empty")
            return text
        if need_target and not contains(text, target):
            problems.append(f"{where}: '{text}' doesn't contain {target}")
        if re.search(r"\d", text):
            problems.append(f"{where}: digits in '{text}' - write numbers as words")
        indo = normalise.indonesian_in(text, allow=own)
        if indo:
            problems.append(f"{where}: Indonesian in '{text}': "
                            + ", ".join(f"{f} (Malaysian: {m})" for f, m in indo))
        missing = [u for u in kn.unknown_words(text, allowed) if u != target]
        if missing:
            problems.append(f"{where}: '{text}' uses unstudied words {', '.join(missing)}")
        return text

    for key, lo, hi in (("chunks", 2, 4), ("sentences", 3, 5)):
        items = content.get(key)
        if not isinstance(items, list) or not (lo <= len(items) <= hi):
            problems.append(f"{key}: needs {lo}-{hi} items")
            continue
        for i, it in enumerate(items, 1):
            if not isinstance(it, dict):
                problems.append(f"[{key} {i}] not an object")
                continue
            it["malay"] = check_ms(it.get("malay"), f"[{key} {i}]")
            if key == "sentences":
                if len(normalise.tokens(it["malay"])) > MAX_SENTENCE_WORDS:
                    problems.append(f"[sentences {i}] too long")
                sid = it.get("structure")
                if sid and sid not in by_id:
                    it["structure"] = sid = None
                if sid and not by_id[sid].used_in(it["malay"]):
                    problems.append(f"[sentences {i}] tagged {sid} but doesn't use it")
    if structures and isinstance(content.get("sentences"), list) and \
            not any(isinstance(x, dict) and x.get("structure") in by_id for x in content["sentences"]):
        problems.append("no sentence uses the grammar being practised - tag one that does: "
                        + ", ".join(s.id for s in structures))
    prompts = content.get("prompts") or []
    if recognise_only:
        content["prompts"] = []
    elif not (1 <= len(prompts) <= 3):
        problems.append("prompts: needs 1-3 items")
    else:
        for i, p in enumerate(prompts, 1):
            if not isinstance(p, dict) or not p.get("situation"):
                problems.append(f"[prompts {i}] missing situation")
                continue
            p["sample_malay"] = check_ms(p.get("sample_malay"), f"[prompts {i}]")
    content["confusables"] = [
        {**c, "malay": str(c["malay"]).strip().lower()}
        for c in (content.get("confusables") or [])
        if isinstance(c, dict) and c.get("malay") and str(c["malay"]).strip().lower() != target][:3]
    return content, problems


def review(content, word):
    lines = [f"meaning: {content.get('meaning')}"]
    lines += [f"[chunk] {c['malay']} = {c.get('english')}" for c in content.get("chunks", [])]
    lines += [f"[sentence] {s['malay']} = {s.get('english')}" for s in content.get("sentences", [])]
    lines += [f"[confusable] {c['malay']}: {c.get('difference')}" for c in content.get("confusables", [])]
    lines += [f"[prompt] {p['situation']} -> {p['sample_malay']}" for p in content.get("prompts", [])]
    prompt = f"""
You are a strict native-speaker reviewer of MALAYSIAN Malay study material.
TARGET WORD: {word['malay']} - {word['english']}

Check every line:
- Is the Malay natural, grammatical and something a Malaysian would actually
  say? Colloquial forms (tak, nak, dah, ni, tu, je, kat) are fine.
- Is it Malaysian, NOT Indonesian? Flag any Indonesian word, spelling or usage
  ({INDONESIAN_EXAMPLES}).
- Is the target used in the stated meaning, with the right affixes?
- Are the chunks real, common collocations? Are the English translations
  accurate? Are the confusable differences correct? Do the sample answers fit
  their situations?

{chr(10).join(lines)}

Return ONLY JSON: {{"acceptable": true/false, "problems": ["<line>: <problem>", ...]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = llm.chat_json(model, prompt, 0)
            probs = [str(p) for p in (v.get("problems") or []) if str(p).strip()]
            return bool(v.get("acceptable", False)) and not probs, probs, True
        except Exception as e:
            logging.warning(f"[WORD REVIEW] {model} failed: {e}")
    return True, [], False


def generate(word, known_words, structures=(), recent=()):
    """Write, check and review a word's content. Returns it, or None."""
    import json
    import time
    feedback = ""
    for attempt in range(1, llm.MAX_ATTEMPTS + 1):
        try:
            content = llm.chat_json(GENERATION_MODEL,
                                    build_prompt(word, known_words, structures, feedback, recent), 0.7)
        except json.JSONDecodeError as e:
            feedback = f"- output was not valid JSON ({e})"
            continue
        except Exception as e:
            logging.warning(f"[WORD CONTENT] attempt {attempt}: API error {e}")
            time.sleep(min(20, 5 * attempt))
            continue
        content, problems = validate(content, word, known_words, structures)
        if not problems:
            ok, problems, reviewed = review(content, word)
            if ok:
                content["reviewed"] = reviewed
                content["source"] = "generated"
                return content
        feedback = "\n".join(f"- {p}" for p in problems[:12])
        logging.warning(f"[WORD CONTENT] {word['malay']} attempt {attempt} rejected:\n{feedback}")
    return None


def fallback_content(word, bank_exercise=None):
    """Minimal content when nothing better exists yet: a vetted sentence-bank
    sentence if there is one, otherwise the word itself."""
    sentences = []
    text = (bank_exercise or {}).get("malay") or ""
    if text and contains(text, word["malay"]):
        sentences = [{"malay": text, "english": bank_exercise.get("english_correct", ""),
                      "structure": None}]
    return {"meaning": short_meaning(word["english"]), "chunks": [], "sentences": sentences,
            "confusables": [], "prompts": [], "introduced_words": [],
            "source": ((bank_exercise or {}).get("source") == "tatoeba" and "tatoeba")
                      or ("bank" if sentences else "word"),
            "reviewed": True}


def grade_spoken(word, situation, sample, said, spoken=True):
    """Judge a spoken sentence meant to use the word. Returns
    {verdict, feedback, better, error}, where error is one of
    none / wrong_word / indonesian / affix / collocation / grammar /
    meaning / unclear."""
    if not (said or "").strip():
        return {"verdict": "wrong", "feedback": "Nothing was heard.", "better": sample,
                "error": "unclear"}
    prompt = f"""
You are a warm but exact tutor of MALAYSIAN Malay. The learner is practising
the word {word['malay']} ({short_meaning(word['english'])}).
SITUATION: {situation}
A GOOD ANSWER (one of many): {sample}
LEARNER SAID: {said}
{"(Speech transcription: ignore spelling and punctuation; Whisper often writes colloquial speech in standard spelling.)" if spoken else ""}

Colloquial and standard forms are equally correct (tak = tidak, nak = hendak,
dah = sudah). Indonesian words or usage are NOT correct.

verdict: "correct" = natural, fits the situation, uses the word correctly;
"close" = right idea but a small slip, or the word avoided; "wrong" otherwise.
error: "none", "wrong_word" (used a different word instead), "indonesian"
(used an Indonesian form), "affix" (right root, wrong affix), "collocation"
(word used with the wrong partner word), "grammar", "meaning" (word used in a
wrong sense), or "unclear".
feedback: at most two short plain-English sentences. better: a natural
Malaysian version using the word.

Return ONLY JSON: {{"verdict": "...", "error": "...", "feedback": "...", "better": "..."}}
""".strip()
    try:
        v = llm.chat_json(GRADING_MODEL, prompt, 0.2)
        verdict = v.get("verdict") if v.get("verdict") in ("correct", "close", "wrong") else "close"
        return {"verdict": verdict, "error": str(v.get("error") or "none"),
                "feedback": str(v.get("feedback") or ""),
                "better": str(v.get("better") or sample)}
    except Exception as e:
        logging.warning(f"[WORD GRADE] failed: {e}")
        return {"verdict": "ungraded", "error": "none", "better": sample,
                "feedback": "Couldn't grade this one automatically - compare with the "
                            "sample (it won't count against you)."}


def practising_structures(progress_rows, today, limit=3):
    """The grammar structures to weave into new content: those practised in
    the last fortnight or due now, most recent first. Empty until the
    grammar syllabus exists (Phase 4)."""
    try:
        import grammar_curriculum as gc
    except ImportError:
        return []
    from datetime import date as _date, timedelta
    t = today if isinstance(today, _date) else _date.fromisoformat(str(today))
    cutoff = (t - timedelta(days=14)).isoformat()
    rows = [r for r in progress_rows.values()
            if (r.get("last_seen") or "") >= cutoff or (r.get("next_review_date") or "9") <= t.isoformat()]
    rows.sort(key=lambda r: r.get("last_seen") or "", reverse=True)
    return [gc.get(r["structure_id"]) for r in rows if gc.get(r["structure_id"])][:limit]
