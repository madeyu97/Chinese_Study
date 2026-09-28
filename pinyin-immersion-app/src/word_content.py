# src/word_content.py
"""
What each word is learned THROUGH: never the word alone.

For every word the learner studies, a small content set is written from
words they already know plus the target (so each sentence adds exactly one
new thing):

  meaning      the core meaning, as used in the examples
  chunks       2-4 high-frequency collocations the word lives in (告诉我)
  sentences    4 short natural sentences, favouring the grammar structures
               the learner is currently practising (tagged by structure id)
  confusables  words learners commonly mix it up with, with the difference
  prompts      situations for spoken production, with a sample answer

It is checked mechanically (target present, only known words, no Beijing 儿,
structure markers present) and then by the reviewer model, like the grammar
drills.

This module also builds the multiple-choice options. Wrong options are never
random: each is labelled as a SOUND-alike, a LOOK-alike or a MEANING-alike,
so that the option a learner picks feeds the diagnosis of why a word is
being missed. And it checks typed or spoken answers, telling a tone slip or
a same-sound character apart from a wrong word.
"""

import logging
import random
import re
import unicodedata

import ai_prompter as ap
import grammar_curriculum as gc
import grammar_drills as gd
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from dictionary_engine import has_erhua

MAX_INTRODUCED = 1
_TONES = {"\u0304": 1, "\u0301": 2, "\u030c": 3, "\u0300": 4}


# ======================================================================
# Meanings
# ======================================================================
def short_meaning(english, limit=40):
    """The first sense of a gloss, trimmed: 'to tell / to inform' -> 'to tell'."""
    text = re.sub(r"\s*\(Malaysia:[^)]*\)", "", english or "").strip()
    first = re.split(r"\s*/\s*|;\s*", text)[0].strip()
    return first[:limit].rstrip(" ,") or text[:limit]


# ======================================================================
# Pinyin comparison (for typed and spoken answers)
# ======================================================================
def _syllables(pinyin):
    """'gào su' / 'gao4su4' / 'gaosu' -> [(base, tone or None), ...]."""
    import dictionary_engine as de
    text = unicodedata.normalize("NFC", str(pinyin).lower()).replace("v", "ü")
    text = re.sub(r"[^a-zü0-9\u0300-\u036f\u00e0-\u01dc ]", " ", text)
    out = []
    for token in text.split():
        numbered = re.findall(r"([a-zü]+)([1-5])", token)
        if numbered and "".join(b + t for b, t in numbered) == token:
            out += [(b, int(t) if t != "5" else 5) for b, t in numbered]
            continue
        parts = de._split_syllables(token) or [token]
        for p in parts:
            tone = None
            for ch in unicodedata.normalize("NFD", p):
                if ch in _TONES:
                    tone = _TONES[ch]
            out.append((de._strip_tones(p), tone))
    return out


def check_answer(answer, target_hanzi, target_pinyin):
    """Judge a typed or transcribed production answer.

    Returns (result, detail). result: correct / close / wrong.
    detail flags feed the diagnosis: tone_error, homophone, typed."""
    answer = ap._force_simplified((answer or "").strip())
    if not answer:
        return "wrong", {"typed": ""}
    if re.search(r"[\u4e00-\u9fff]", answer):
        if target_hanzi in answer:
            return "correct", {"typed": answer}
        # same sound, different characters: right word heard, wrong written form
        from dictionary_engine import derive_pinyin
        if [b for b, _t in _syllables(derive_pinyin(answer))] == \
                [b for b, _t in _syllables(target_pinyin)]:
            return "close", {"typed": answer, "homophone": True}
        return "wrong", {"typed": answer}
    got, want = _syllables(answer), _syllables(target_pinyin)
    if [b for b, _ in got] != [b for b, _ in want]:
        return "wrong", {"typed": answer}
    typed_tones = [t for _b, t in got]
    if all(t is None for t in typed_tones):
        return "correct", {"typed": answer, "tones_given": False}
    wrong = [i for i, ((_b, t), (_b2, w)) in enumerate(zip(got, want))
             if t is not None and t != (w or 5) and not (t == 5 and w is None)]
    if wrong:
        return "close", {"typed": answer, "tone_error": True, "syllables": wrong}
    return "correct", {"typed": answer, "tones_given": True}


# ======================================================================
# Diagnostic multiple-choice options
# ======================================================================
def _toneless(pinyin):
    return tuple(b for b, _t in _syllables(pinyin))


_BARE_STROKES = set("一丨丶丿乙亅乚㇀㇏")


def _components(ch):
    try:
        from radical_engine import decompose
        d = decompose(ch) or {}
        return {c["component"] for c in d.get("components", [])
                if c.get("component") and c["component"] not in _BARE_STROKES}
    except Exception:
        return set()


def _looks_alike(a, b):
    """Multi-character words: share a character (告诉 / 报告). Single
    characters: share a real component (冷 / 领 / 零 - all built on 令)."""
    if a == b:
        return False
    if len(a) > 1 or len(b) > 1:
        return bool(set(a) & set(b))
    return bool(_components(a) & _components(b))


def _toned(pinyin):
    return tuple((b, t or 5) for b, t in _syllables(pinyin))


def meaning_options(word, pool, confusables=(), n=3, rng=None, audio=False):
    """Options for 'what does it mean?': the right meaning plus up to n wrong
    ones, each labelled for diagnosis:
      homophone  identical sound, different word (他 / 她)
      tone       same syllables, different tones (买 / 卖)
      look       shares a character or component (冷 / 领)
      meaning    a word commonly confused in meaning (告诉 / 说)
      other      filler from the learner's words
    With audio=True exact homophones are left out: no ear can separate them.

    pool: word dicts (chinese, pinyin, english) - ideally words the learner
    has met, so the options are plausible."""
    rng = rng or random.Random()
    right = short_meaning(word["english"])
    seen = {right.lower()}
    target_toneless, target_toned = _toneless(word["pinyin"]), _toned(word["pinyin"])
    picks = {"meaning": [], "tone": [], "homophone": [], "look": [], "other": []}
    by_zh = {w["chinese"]: w for w in pool}
    for c in confusables or ():
        w = by_zh.get(c.get("hanzi"))
        if w:
            picks["meaning"].append(w)
    for w in pool:
        if w["chinese"] == word["chinese"]:
            continue
        if _toneless(w["pinyin"]) == target_toneless:
            picks["homophone" if _toned(w["pinyin"]) == target_toned else "tone"].append(w)
        elif _looks_alike(word["chinese"], w["chinese"]):
            picks["look"].append(w)
    others = [w for w in pool if w["chinese"] != word["chinese"]]
    rng.shuffle(others)
    picks["other"] = others[:40]
    if audio:   # nothing that sounds identical, from any group
        same = {w["chinese"] for w in picks["homophone"]}
        picks = {k: [w for w in v if w["chinese"] not in same] for k, v in picks.items()}
        picks["homophone"] = []
    options = []
    for kind in ("meaning", "tone", "homophone", "look", "other"):
        group = picks[kind]
        if kind != "other":
            rng.shuffle(group)
        for w in group:
            m = short_meaning(w["english"])
            if m and m.lower() not in seen and len(options) < n:
                seen.add(m.lower())
                options.append({"text": m, "kind": kind, "chinese": w["chinese"]})
        if len(options) >= n:
            break
    options.append({"text": right, "kind": "correct", "chinese": word["chinese"]})
    rng.shuffle(options)
    return options


# ======================================================================
# Writing the content
# ======================================================================
def build_prompt(word, known_words, structures=(), feedback="", recent=()):
    china = word.get("tag") == "China"
    partner = re.search(r"\(Malaysia: (\S+)", word.get("english") or "")
    known = "、".join(sorted(set(known_words) - {word["chinese"]}, key=lambda w: (len(w), w)))
    grammar = "\n".join(f"  - [{s.id}] {s.name}: {s.pattern}" for s in structures) or "  (none yet)"
    mainland = (f"\nThis is a MAINLAND word; Malaysians say {partner.group(1) if partner else 'something else'}. "
                "Write sentences as heard in mainland speech or media: the learner only needs to "
                "RECOGNISE it. Return an empty prompts list.") if china else ""
    return f"""
You write study material for ONE word, for an adult learning MALAYSIAN Mandarin
(natural everyday speech of Chinese Malaysians).

TARGET WORD: {word['chinese']} ({word['pinyin']}) - {short_meaning(word['english'])}
FULL GLOSS: {word['english']}{mainland}

THE LEARNER ALREADY KNOWS (use ONLY these words, the target, pronouns,
particles and numbers - every sentence should add exactly one new thing, the
target):
{known}
If a sentence is impossible otherwise, you may use ONE extra simple word and
list it in "introduced_words".

GRAMMAR THE LEARNER IS PRACTISING - at least one sentence MUST use one of these
(naturally), with its id in "structure"; the other sentences may too (otherwise null):
{grammar}
{("RECENTLY LEARNED WORDS - reuse some where natural, so new words keep meeting "
  "each other: " + "、".join(recent)) if recent else ""}

Write:
- "meaning": the core meaning in 2-6 English words, as used in your examples.
- "chunks": 2-4 high-frequency collocations containing the target exactly
  (e.g. for 告诉: 告诉我, 告诉你一件事), with pinyin and English.
- "sentences": 4 short natural sentences (5-12 characters), each containing the
  target exactly once, varied in subject and situation, with pinyin and English.
- "confusables": 1-3 words learners commonly confuse with the target, each with
  a one-line plain-English difference.
- "prompts": 2 situations (in English, "You want to…") where the learner would
  naturally say something with the target, each with a short sample answer.

Rules: simplified characters; no Beijing 儿 (一点 not 一点儿, 哪里 not 哪儿);
Chinese numerals, never digits; no English words or names inside Chinese.
{("PREVIOUS ATTEMPT WAS REJECTED. Fix every one of these:\n" + feedback) if feedback else ""}

Return ONLY JSON:
{{"meaning": "…",
 "chunks": [{{"hanzi": "…", "pinyin": "…", "english": "…"}}],
 "sentences": [{{"hanzi": "…", "pinyin": "…", "english": "…", "structure": null}}],
 "confusables": [{{"hanzi": "…", "difference": "…"}}],
 "prompts": [{{"situation": "…", "sample_hanzi": "…", "sample_pinyin": "…", "sample_english": "…"}}],
 "introduced_words": [{{"hanzi": "…", "pinyin": "…", "english": "…"}}]}}
""".strip()


def validate(content, word, known_words, structures=()):
    problems = []
    if not isinstance(content, dict):
        return content, ["not a JSON object"]
    target = word["chinese"]
    china = word.get("tag") == "China"
    introduced = [w for w in (content.get("introduced_words") or [])
                  if isinstance(w, dict) and w.get("hanzi")]
    content["introduced_words"] = introduced
    if len(introduced) > MAX_INTRODUCED:
        problems.append("more than one introduced word - use known words")
    allowed = set(known_words) | gd.FUNCTION_WORDS | {target} | {w["hanzi"] for w in introduced}
    by_id = {s.id: s for s in structures}
    if not str(content.get("meaning") or "").strip():
        problems.append("missing meaning")

    def check_zh(hz, where, need_target=True, py=""):
        hz = ap._force_simplified(str(hz or "")).strip()
        if not hz:
            problems.append(f"{where}: empty")
            return hz
        if need_target and target not in hz:
            problems.append(f"{where}: '{hz}' doesn't contain {target}")
        if has_erhua(hz, py):
            problems.append(f"{where}: Beijing 儿 in '{hz}'")
        if re.search(r"[A-Za-z0-9]", hz):
            problems.append(f"{where}: digits or Latin letters in '{hz}'")
        missing = [u for u in gd.unknown_words(hz, allowed) if u != target]
        if missing:
            problems.append(f"{where}: '{hz}' uses unstudied words {'、'.join(dict.fromkeys(missing))}")
        return hz

    for key, lo, hi in (("chunks", 2, 4), ("sentences", 3, 5)):
        items = content.get(key)
        if not isinstance(items, list) or not (lo <= len(items) <= hi):
            problems.append(f"{key}: needs {lo}-{hi} items")
            continue
        for i, it in enumerate(items, 1):
            if not isinstance(it, dict):
                problems.append(f"[{key} {i}] not an object")
                continue
            it["hanzi"] = check_zh(it.get("hanzi"), f"[{key} {i}]", py=it.get("pinyin", ""))
            it["pinyin"] = gd._fix_pinyin(it["hanzi"], it.get("pinyin", ""))
            if key == "sentences":
                if len(it["hanzi"]) > 20:
                    problems.append(f"[sentences {i}] too long")
                sid = it.get("structure")
                if sid and sid not in by_id:
                    it["structure"] = None
                    sid = None
                if sid:
                    s = by_id.get(sid)
                    if not s:
                        it["structure"] = None
                    elif s.markers and not any(m in it["hanzi"] for m in s.markers):
                        problems.append(f"[sentences {i}] tagged {sid} but doesn't use it")
    if structures and isinstance(content.get("sentences"), list) and \
            not any(isinstance(x, dict) and x.get("structure") in by_id for x in content["sentences"]):
        problems.append("no sentence uses the grammar being practised - tag one that does: "
                        + ", ".join(s.id for s in structures))
    prompts = content.get("prompts") or []
    if china:
        content["prompts"] = []
    elif not (1 <= len(prompts) <= 3):
        problems.append("prompts: needs 1-3 items")
    else:
        for i, p in enumerate(prompts, 1):
            if not isinstance(p, dict) or not p.get("situation"):
                problems.append(f"[prompts {i}] missing situation")
                continue
            p["sample_hanzi"] = check_zh(p.get("sample_hanzi"), f"[prompts {i}]",
                                         py=p.get("sample_pinyin", ""))
            p["sample_pinyin"] = gd._fix_pinyin(p["sample_hanzi"], p.get("sample_pinyin", ""))
    content["confusables"] = [c for c in (content.get("confusables") or [])
                              if isinstance(c, dict) and c.get("hanzi") and c["hanzi"] != target][:3]
    return content, problems


def review(content, word):
    lines = [f"meaning: {content.get('meaning')}"]
    lines += [f"[chunk] {c['hanzi']} = {c.get('english')}" for c in content.get("chunks", [])]
    lines += [f"[sentence] {s['hanzi']} = {s.get('english')}" for s in content.get("sentences", [])]
    lines += [f"[confusable] {c['hanzi']}: {c.get('difference')}" for c in content.get("confusables", [])]
    lines += [f"[prompt] {p['situation']} -> {p['sample_hanzi']}" for p in content.get("prompts", [])]
    prompt = f"""
You are a strict native-speaker reviewer of Malaysian Mandarin study material.
TARGET WORD: {word['chinese']} ({word['pinyin']}) - {word['english']}

Check: every Chinese line is natural, grammatical everyday Mandarin a Chinese
Malaysian would say (Malaysian words such as 巴士, 冷气, 蛮, 啦 are fine); the
target is used in the stated meaning; chunks are real, common collocations;
English translations are accurate; confusable differences are correct; the
sample answers fit their situations. No Beijing 儿.

{chr(10).join(lines)}

Return ONLY JSON: {{"acceptable": true/false, "problems": ["<line>: <problem>", ...]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = gd._chat_json(model, prompt, 0)
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
    for attempt in range(1, gd.MAX_ATTEMPTS + 1):
        try:
            content = gd._chat_json(GENERATION_MODEL,
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
        logging.warning(f"[WORD CONTENT] {word['chinese']} attempt {attempt} rejected:\n{feedback}")
    return None


def fallback_content(word, bank_exercise=None):
    """Minimal content when nothing better exists yet: a vetted sentence-bank
    sentence if there is one, otherwise the word itself."""
    sentences = []
    if bank_exercise and word["chinese"] in (bank_exercise.get("chinese") or ""):
        sentences = [{"hanzi": bank_exercise["chinese"],
                      "pinyin": bank_exercise.get("pinyin", ""),
                      "english": bank_exercise.get("english_correct", ""),
                      "structure": None}]
    return {"meaning": short_meaning(word["english"]), "chunks": [], "sentences": sentences,
            "confusables": [], "prompts": [], "introduced_words": [],
            "source": "bank" if sentences else "word", "reviewed": True}


def cloze(sentence_hanzi, target):
    """The sentence with the target blanked once: 你告诉我 -> 你＿＿我."""
    return sentence_hanzi.replace(target, "＿" * len(target), 1)


def grade_spoken(word, situation, sample, said, spoken=True):
    """Judge a spoken sentence meant to use the word. Returns
    {verdict, feedback, better, error}, where error is one of
    none / wrong_word / collocation / grammar / meaning / unclear."""
    if not (said or "").strip():
        return {"verdict": "wrong", "feedback": "Nothing was heard.", "better": sample,
                "error": "unclear"}
    prompt = f"""
You are a warm but exact Malaysian Mandarin tutor. The learner is practising
the word {word['chinese']} ({word['pinyin']}, {short_meaning(word['english'])}).
SITUATION: {situation}
A GOOD ANSWER (one of many): {sample}
LEARNER SAID: {said}
{"(Speech transcription: ignore homophone mix-ups and punctuation.)" if spoken else ""}

verdict: "correct" = natural, fits the situation, uses the word correctly;
"close" = right idea but a small slip, or the word avoided; "wrong" otherwise.
error: "none", "wrong_word" (used a different word instead), "collocation"
(word used with the wrong partner word), "grammar", "meaning" (word used in a
wrong sense), or "unclear".
feedback: at most two short plain-English sentences. better: a natural
version using the word. No Beijing 儿.

Return ONLY JSON: {{"verdict": "...", "error": "...", "feedback": "...", "better": "..."}}
""".strip()
    try:
        v = gd._chat_json(GRADING_MODEL, prompt, 0.2)
        verdict = v.get("verdict") if v.get("verdict") in ("correct", "close", "wrong") else "close"
        return {"verdict": verdict, "error": str(v.get("error") or "none"),
                "feedback": str(v.get("feedback") or ""),
                "better": ap._force_simplified(str(v.get("better") or sample))}
    except Exception as e:
        logging.warning(f"[WORD GRADE] failed: {e}")
        return {"verdict": "ungraded", "error": "none", "better": sample,
                "feedback": "Couldn't grade this one automatically - compare with the "
                            "sample (it won't count against you)."}


def practising_structures(progress_rows, today, limit=3):
    """The grammar structures to weave into new content: those practised in
    the last fortnight or due now, most recent first."""
    from datetime import date as _date, timedelta
    t = today if isinstance(today, _date) else _date.fromisoformat(str(today))
    cutoff = (t - timedelta(days=14)).isoformat()
    rows = [r for r in progress_rows.values()
            if (r.get("last_seen") or "") >= cutoff or (r.get("next_review_date") or "9") <= t.isoformat()]
    rows.sort(key=lambda r: r.get("last_seen") or "", reverse=True)
    return [gc.get(r["structure_id"]) for r in rows if gc.get(r["structure_id"])][:limit]
