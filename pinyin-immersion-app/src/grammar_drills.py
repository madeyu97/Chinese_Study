# src/grammar_drills.py
"""
Builds, checks, grades and schedules grammar drills.

A drill set is written fresh for each learner from the words they already
know well, so it grows as their vocabulary grows. Every set passes three
gates before it is shown:

1. Mechanical checks here: the right shape, simplified characters, no
   Beijing 儿, the target structure present, and no word the learner hasn't
   studied unless it is declared as an introduced word.
2. The reviewer model (a different model family from the writer) checks
   naturalness, grammar and that every answer key is right.
3. Anything that fails is rewritten with the problems fed back, up to
   MAX_ATTEMPTS; a set that never passes is not shown.

Five stages per structure, as specified:
  identify     hear a sentence, pick its meaning/function
  produce      situation in English -> say it in Chinese
  contrast     hear or read, tell the target apart from a look-alike
  rapid        quick prompts, answer aloud at once
  conversation natural questions answered with the structure
"""

import json
import logging
import re
import time
from datetime import date, timedelta

import jieba

import ai_prompter as ap
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from dictionary_engine import derive_pinyin, has_erhua, is_cjk_char

MAX_ATTEMPTS = 3
MAX_INTRODUCED = 4

# Words any drill may use whatever the learner's list says: pronouns,
# particles, numbers and the commonest function words. Content words must
# come from the learner's own studied vocabulary.
FUNCTION_WORDS = set("""
我 你 他 她 它 我们 你们 他们 她们 咱们 自己 大家 这 那 哪 这个 那个 哪个 这些 那些
这里 那里 哪里 这样 那样 的 地 得 了 着 过 吗 呢 吧 啊 呀 啦 咯 哦 噢 嗯 嘛 咩 叻 是 不 没 没有 有
很 也 都 还 就 才 又 再 在 和 跟 个 一 二 两 三 四 五 六 七 八 九 十 百 千 万 几 多少
什么 谁 怎么 为什么 一下 一点 一些 会 要 想 能 可以 给 对 把 被 比 从 到 去 来 说 太
最 更 真 好 人 东西 事 时候 地方
""".split())

STAGES = ("identify", "produce", "contrast", "rapid", "conversation")
STAGE_TITLES = {
    "identify": "Hear → identify",
    "produce": "Meaning → Chinese",
    "contrast": "Contrast",
    "rapid": "Rapid retrieval",
    "conversation": "Conversation",
}
COUNTS = {"identify": (3, 5), "produce": (3, 4), "contrast": (3, 4),
          "rapid": (5, 8), "conversation": (3, 5)}


# ======================================================================
# Vocabulary control
# ======================================================================
def structure_words(structure):
    """The grammar words the structure is built from (its markers), plus those
    of the structures it is contrasted with (the contrast stage has to use
    them) - always allowed. The example words in patterns are NOT: those must
    still come from the learner's own vocabulary."""
    import grammar_curriculum as gc
    words = set()
    sources = [structure] + [gc.get(c) for c in structure.contrast if gc.get(c)]
    for src in sources:
        for marker in src.markers:
            words.add(marker)
            words.update(jieba.lcut(marker, HMM=False))
    return words


def allowed_set(known_words, structure, introduced=()):
    return set(known_words) | FUNCTION_WORDS | structure_words(structure) | set(introduced)


def unknown_words(text, allowed):
    """Words in `text` the learner hasn't met. A token counts as known if it
    is on the list or splits cleanly into words that are."""
    unknown = []
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text)):
        for tok in jieba.lcut(run, HMM=False):
            if tok in allowed or _splits_into(tok, allowed):
                continue
            # report only the part that isn't known: 喝啤酒 -> 啤酒
            gap, i = "", 0
            while i < len(tok):
                for L in range(min(4, len(tok) - i), 0, -1):
                    if tok[i:i + L] in allowed:
                        break
                else:
                    L = 0
                if L:
                    if gap:
                        unknown.append(gap)
                        gap = ""
                    i += L
                else:
                    gap += tok[i]
                    i += 1
            if gap:
                unknown.append(gap)
    return [u for u in unknown
            if not all(ch in "零一二两三四五六七八九十百千万几半" for ch in u)]


def _splits_into(tok, allowed):
    i = 0
    while i < len(tok):
        for L in range(min(4, len(tok) - i), 0, -1):
            if tok[i:i + L] in allowed:
                i += L
                break
        else:
            return False
    return True


# ======================================================================
# Prompt
# ======================================================================
def build_prompt(structure, known_words, china_pairs=(), contrasts=(),
                 previous=(), feedback="", recent=()):
    known_list = "、".join(sorted(known_words, key=lambda w: (len(w), w)))
    china = "; ".join(f"{m} not {c}" for c, m in china_pairs[:60])
    contrast_text = "\n".join(f"  - {c.name}: {c.pattern} — {c.purpose}" for c in contrasts) \
        or "  (none listed - pick the most commonly confused structure, or set contrast to null if none is useful)"
    prev = "\n".join(f"  - {s}" for s in list(previous)[:25])
    recent_text = ("\nRECENTLY LEARNED WORDS - recycle several of these across the items (at "
                   "least one is required), so new vocabulary gets used inside the grammar:\n  "
                   + "、".join(recent) + "\n") if recent else ""
    kind_note = ("This is a CONTRAST DRILL: every stage should make the learner choose "
                 "between the structures listed below (use each of them across the items), "
                 "not just use one." if structure.kind == "contrast" else "")
    return f"""
You write grammar drills for an adult learning MALAYSIAN Mandarin (the Mandarin
spoken by Chinese Malaysians: natural, everyday, conversational).

TARGET STRUCTURE: {structure.name}
PATTERN: {structure.pattern}
PURPOSE: {structure.purpose}
TEACHING NOTES (follow these; never state them as rules to memorise):
  {structure.notes}
{kind_note}
COMMONLY CONFUSED WITH:
{contrast_text}

THE LEARNER'S WELL-STUDIED WORDS (use ONLY these, plus pronouns, particles,
numbers, and the grammar words of the target structure):
{known_list}
{recent_text}
If a sentence is impossible without another word, use the simplest common word
and list it in "introduced_words" (at most {MAX_INTRODUCED}). Do not use any other
unlisted word.

MALAYSIAN USAGE: no Beijing 儿 at all (一点 not 一点儿, 哪里 not 哪儿, 这里 not 这儿).
Prefer the words Malaysians use: {china or "(none)"}.

PRINCIPLES
- Train recognition and spontaneous use, not explanation. Explanations are one
  short plain-English line about meaning/function, no grammar jargon.
- Natural everyday sentences a Malaysian would actually say. Short (4-9
  characters) at first, a little longer towards the end of each stage.
- Vary subjects, objects, time and context across items so nothing can be
  memorised as one sentence. Do not reuse these recent sentences:
{prev or "  (none)"}
- Never describe 了 as "past tense".
- Simplified characters only. Chinese numerals, never digits. No English words
  inside Chinese sentences. No names - use pronouns and roles.
- Produce and rapid prompts are situations or intentions ("You want to tell
  your friend…", "Say you've never…"), not word-for-word English to translate.
- Every sentence that is meant to use the target structure must use it.
- In multiple choice, exactly one option is correct. Options are meanings or
  functions in English. Set "read": true only when the item can't be told apart
  by ear (e.g. 的/得/地, which sound identical) - the text is then shown first.
{("PREVIOUS ATTEMPT WAS REJECTED. Fix every one of these problems:\n" + feedback) if feedback else ""}

Return ONLY a JSON object:
{{
  "identify": [ {{"hanzi": "…", "pinyin": "…", "english": "…",
                  "question": "What does the speaker mean? / What is this sentence about?",
                  "options": ["…", "…", "…", "…"], "answer": 0,
                  "explain": "…", "read": false}} ],                     // 3-5 items
  "produce": [ {{"situation": "…", "answer_hanzi": "…", "answer_pinyin": "…",
                 "answer_english": "…"}} ],                              // 3-4 items
  "contrast": {{"with": "<the look-alike, in Chinese>",
               "items": [ same shape as identify ]}},                    // 3-4 items, or null
  "rapid": [ {{"prompt": "…", "answer_hanzi": "…", "answer_pinyin": "…"}} ],   // 5-8
  "conversation": [ {{"question_hanzi": "…", "question_pinyin": "…",
                      "question_english": "…", "sample_hanzi": "…",
                      "sample_pinyin": "…", "sample_english": "…"}} ],   // 3-5
  "introduced_words": [ {{"hanzi": "…", "pinyin": "…", "english": "…"}} ]
}}
""".strip()


# ======================================================================
# Mechanical validation
# ======================================================================
def _fix_pinyin(hanzi, pinyin):
    """Keep the writer's pinyin when it has one syllable per character;
    otherwise derive it, so characters and pinyin never disagree."""
    n = sum(1 for ch in hanzi if is_cjk_char(ch))
    syl = re.findall(r"[A-Za-züÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]+", pinyin or "")
    return pinyin if pinyin and len(syl) == n else derive_pinyin(hanzi)


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
                  if isinstance(w, dict) and w.get("hanzi")]
    payload["introduced_words"] = introduced
    if len(introduced) > MAX_INTRODUCED:
        problems.append(f"too many introduced words ({len(introduced)}); use known words")
    allowed = allowed_set(known_words, structure, [w["hanzi"] for w in introduced])

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
            fields = {"identify": [("hanzi", "pinyin", True)],
                      "contrast": [("hanzi", "pinyin", False)],
                      "produce": [("answer_hanzi", "answer_pinyin", True)],
                      "rapid": [("answer_hanzi", "answer_pinyin", True)],
                      "conversation": [("question_hanzi", "question_pinyin", False),
                                       ("sample_hanzi", "sample_pinyin", True)]}[stage]
            for hz_key, py_key, needs_marker in fields:
                hz = ap._force_simplified(str(it.get(hz_key) or "")).strip()
                it[hz_key] = hz
                if not hz:
                    problems.append(f"{where}: empty {hz_key}")
                    continue
                if has_erhua(hz, it.get(py_key, "")):
                    problems.append(f"{where}: uses Beijing 儿 in '{hz}'")
                if re.search(r"[A-Za-z0-9]", hz):
                    problems.append(f"{where}: digits or Latin letters in '{hz}'")
                if needs_marker and structure.markers and \
                        not any(m in hz for m in structure.markers):
                    problems.append(f"{where}: '{hz}' doesn't use the target structure")
                it[py_key] = _fix_pinyin(hz, it.get(py_key, ""))
                missing = unknown_words(hz, allowed)
                if missing:
                    problems.append(f"{where}: '{hz}' uses unstudied words "
                                    f"{'、'.join(dict.fromkeys(missing))} - replace them "
                                    f"or declare them in introduced_words")
            if stage in ("identify", "contrast"):
                _check_mcq(it, where, problems)
                it["read"] = bool(it.get("read"))
            if stage in ("produce", "rapid") and not (it.get("situation") or it.get("prompt")):
                problems.append(f"{where}: missing prompt")
    if len(recent) >= 3 and not problems:
        text = "".join(sentences_in(payload))
        if not any(w in text for w in recent):
            problems.append("none of the recently learned words is used - recycle at least one: "
                            + "、".join(recent[:10]))
    return payload, problems


# ======================================================================
# LLM calls
# ======================================================================
def _chat_json(model, prompt, temperature):
    kwargs = dict(messages=[{"role": "user", "content": prompt}], model=model,
                  response_format={"type": "json_object"}, temperature=temperature)
    if "qwen" in model:
        kwargs["reasoning_effort"] = "none"
    resp = ap.client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    return json.loads(text)


def _describe_for_review(payload):
    lines = []
    for i, it in enumerate(payload.get("identify", []), 1):
        lines.append(f"[identify {i}] {it['hanzi']} | Q: {it.get('question')} | "
                     f"options: {it.get('options')} | key: {it.get('answer')} | "
                     f"explain: {it.get('explain')}")
    for i, it in enumerate(payload.get("produce", []), 1):
        lines.append(f"[produce {i}] situation: {it.get('situation')} -> {it['answer_hanzi']}")
    c = payload.get("contrast")
    if c:
        for i, it in enumerate(c.get("items", []), 1):
            lines.append(f"[contrast {i}] (vs {c.get('with')}) {it['hanzi']} | "
                         f"Q: {it.get('question')} | options: {it.get('options')} | "
                         f"key: {it.get('answer')} | explain: {it.get('explain')}")
    for i, it in enumerate(payload.get("rapid", []), 1):
        lines.append(f"[rapid {i}] {it.get('prompt')} -> {it['answer_hanzi']}")
    for i, it in enumerate(payload.get("conversation", []), 1):
        lines.append(f"[conversation {i}] Q: {it['question_hanzi']} -> sample: {it['sample_hanzi']}")
    return "\n".join(lines)


def review(payload, structure):
    """Second model checks naturalness, grammar and answer keys.
    Returns (acceptable, problems, reviewed). If both models are unreachable
    it lets the set through but reports reviewed=False, so it is shown once
    and never stored for reuse."""
    prompt = f"""
You are a strict native-speaker reviewer of Malaysian Mandarin teaching material.

TARGET STRUCTURE: {structure.name} — {structure.pattern}
WHAT IT SHOULD TEACH: {structure.purpose} {structure.notes}

Check every item below:
1. Natural, grammatical, everyday Mandarin a Chinese Malaysian would say
   (Malaysian words like 巴士, 冷气, 做工, 蛮, 啦 are correct, not errors).
2. Items meant to use the target structure use it correctly.
3. Multiple choice: exactly one option is right and the key points to it.
4. Situations/prompts would naturally lead to the given answer.
5. Contrast items genuinely hinge on the difference; explanations are
   accurate. 了 must never be explained as simply "past tense".
6. No Beijing 儿 (哪儿, 一点儿 etc.).

DRILLS:
{_describe_for_review(payload)}

Return ONLY JSON: {{"acceptable": true/false,
 "problems": ["<item label>: <problem and fix>", ...]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = _chat_json(model, prompt, 0)
            probs = [str(p) for p in (v.get("problems") or []) if str(p).strip()]
            return bool(v.get("acceptable", False)) and not probs, probs, True
        except Exception as e:
            logging.warning(f"[GRAMMAR REVIEW] {model} failed: {e}")
    return True, [], False


def generate(structure, known_words, china_pairs=(), contrasts=(), previous=(), recent=()):
    """Write, check and review a drill set. Returns the payload or None."""
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = build_prompt(structure, known_words, china_pairs, contrasts,
                              previous, feedback, recent)
        try:
            payload = _chat_json(GENERATION_MODEL, prompt, 0.7)
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
    """Every Chinese sentence in a set - fed back so the next set differs."""
    out = [it.get("hanzi") for it in payload.get("identify", [])]
    out += [it.get("answer_hanzi") for it in payload.get("produce", [])]
    out += [it.get("answer_hanzi") for it in payload.get("rapid", [])]
    out += [it.get("sample_hanzi") for it in payload.get("conversation", [])]
    out += [it.get("hanzi") for it in (payload.get("contrast") or {}).get("items", [])]
    return [s for s in out if s]


# ======================================================================
# Grading spoken / typed answers
# ======================================================================
def grade_answer(structure, task, reference, learner_text, spoken=True):
    """Judge a produced answer. Returns {"verdict": correct|close|wrong,
    "feedback": str, "better": str}."""
    if not (learner_text or "").strip():
        return {"verdict": "wrong", "feedback": "Nothing was heard - try again aloud.",
                "better": reference}
    prompt = f"""
You are a warm but exact Malaysian Mandarin tutor. The learner is practising:
{structure.name} ({structure.pattern}) - {structure.purpose}

TASK: {task}
A GOOD ANSWER (one of many): {reference}
LEARNER SAID: {learner_text}
{"(This is a speech transcription: ignore homophone mix-ups such as 在/再 and missing punctuation.)" if spoken else ""}

Verdict:
 "correct" - natural Mandarin, fits the task, and uses the target structure
             correctly (other wordings are fine);
 "close"   - meaning right but a small error, or the structure was avoided;
 "wrong"   - wrong meaning or ungrammatical.
Feedback: at most two short sentences about meaning and function, no jargon.
"better": a natural version using the structure (the learner's own words where
possible). No Beijing 儿.

Return ONLY JSON: {{"verdict": "...", "feedback": "...", "better": "..."}}
""".strip()
    try:
        v = _chat_json(GRADING_MODEL, prompt, 0.2)
        verdict = v.get("verdict") if v.get("verdict") in ("correct", "close", "wrong") else "close"
        return {"verdict": verdict, "feedback": str(v.get("feedback") or ""),
                "better": ap._force_simplified(str(v.get("better") or reference))}
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
