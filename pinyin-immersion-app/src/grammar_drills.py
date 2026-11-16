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

import functools
import json
import logging
import re
import time
from datetime import date, timedelta

import jieba

import clock
import ai_prompter as ap
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from dictionary_engine import derive_pinyin, has_erhua, is_cjk_char

MAX_ATTEMPTS = 3
MAX_INTRODUCED = 4
NEW_PER_SENTENCE = 1      # undeclared new words one sentence may bring in on its own

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
          "rapid": (4, 8), "conversation": (3, 5)}


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


@functools.lru_cache(maxsize=1)
def grammar_words():
    """Every structure's grammar words. The contrast stage sets the target
    against a look-alike; for most structures the curriculum names none and
    the writer picks one (即使 against 无论), so that look-alike's grammar
    words have to be allowed there or no contrast item could ever pass."""
    import grammar_curriculum as gc
    words = set()
    for src in gc.STRUCTURES:
        for marker in src.markers:
            if len(marker) >= 2 or marker in FUNCTION_WORDS:
                words.add(marker)
    return words


def _runs_left(text, allowed):
    """The parts of each Chinese run not covered by known words of two or
    more characters (matched longest first)."""
    longest = max((len(w) for w in allowed), default=1)
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text)):
        rest, i = [], 0
        while i < len(run):
            for L in range(min(longest, len(run) - i), 1, -1):
                if run[i:i + L] in allowed:
                    rest.append(" ")
                    i += L
                    break
            else:
                rest.append(run[i])
                i += 1
        yield from "".join(rest).split()


def unknown_tokens(text, allowed):
    """Whole words (as jieba cuts them) that aren't known - what to declare
    as new: 电话, not the 电 that unknown_words reports for 打电话."""
    out = []
    for piece in _runs_left(text, allowed):
        loose = ""                    # unknown single characters in a row
        for tok in jieba.lcut(piece, HMM=False):
            unknown = not (tok in allowed or _splits_into(tok, allowed)) and \
                not all(ch in "零一二两三四五六七八九十百千万几半" for ch in tok)
            if unknown and len(tok) == 1:
                # jieba cuts words it doesn't know (巴刹) into characters,
                # each a dictionary entry on its own (巴, 刹): keep them together
                loose += tok
                continue
            if loose:
                out.append(loose)
                loose = ""
            if unknown:
                out.append(tok)
        if loose:
            out.append(loose)
    return out


def unknown_words(text, allowed):
    """Words in `text` the learner hasn't met. A token counts as known if it
    is on the list or splits cleanly into words that are.

    Known words of two or more characters are matched first, longest first,
    before jieba segments what is left: jieba doesn't know Malaysian words
    (巴刹, 拜六, 月尾, 手信) and splits them into characters that aren't on
    the list on their own - which made the learner's own words "unstudied"."""
    unknown = []
    for piece in _runs_left(text, allowed):
        for tok in jieba.lcut(piece, HMM=False):
            if tok in allowed or _splits_into(tok, allowed):
                continue
            # report only the part that isn't known: 喝啤酒 -> 啤酒
            gap, j = "", 0
            while j < len(tok):
                for L in range(min(4, len(tok) - j), 0, -1):
                    if tok[j:j + L] in allowed:
                        break
                else:
                    L = 0
                if L:
                    if gap:
                        unknown.append(gap)
                        gap = ""
                    j += L
                else:
                    gap += tok[j]
                    j += 1
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
  functions in English, all written the same way and about the same length:
  the right one must never stand out by being longer or more detailed, and
  its position in the list must vary from item to item. Set "read": true only when the item can't be told apart
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


_BLANK_OPTION = re.compile(r"^\s*(<[^>]*>|\.{2,}|…+|-+|_+|option\s*\d*|[a-d]\)?|n/?a)\s*$", re.I)


def mcq_problem(item):
    """What's wrong with a multiple-choice item's options, or None: it needs
    3-4 real, different options (not blanks or a template's '…' copied back)
    and an answer index that points at one of them."""
    opts = item.get("options") if isinstance(item, dict) else None
    if not isinstance(opts, list) or not (3 <= len(opts) <= 4):
        return "needs 3-4 options"
    texts = [str(o).strip() if isinstance(o, (str, int, float)) else "" for o in opts]
    if any(not t or _BLANK_OPTION.match(t) for t in texts):
        return "has a blank or placeholder option - write every option in full"
    if len({re.sub(r"[^\w']+", " ", t.lower()).strip() for t in texts}) != len(texts):
        return "needs 3-4 different options"
    ans = item.get("answer")
    if not isinstance(ans, int) or isinstance(ans, bool) or not (0 <= ans < len(opts)):
        return "answer index out of range"
    sizes = [len(t.split()) for t in texts]
    rest = [n for i, n in enumerate(sizes) if i != ans]
    if sizes[ans] >= 4 and sizes[ans] >= 2 * max(rest):
        return "the right option is much longer than the others - make them all about the same length"
    if min(rest) >= 4 and min(rest) >= 2 * sizes[ans]:
        return "the right option is much shorter than the others - make them all about the same length"
    return None


def _check_mcq(item, where, problems):
    problem = mcq_problem(item)
    if problem:
        problems.append(f"{where}: {problem}")


def structure_problem(hanzi, structure):
    """Why a sentence meant to use the structure doesn't, or None: it must
    contain one of the markers and match every `requires` pattern (连 alone
    is also in 连续 and 连忙; 无论很忙 has 无论 but isn't the structure)."""
    if structure.markers and not any(m in hanzi for m in structure.markers):
        return "doesn't use the target structure"
    for pattern, wrong in structure.requires:
        if not re.search(pattern, hanzi):
            return wrong
    return None


def stored_set_ok(payload, structure):
    """Whether a drill set saved earlier still passes today's structure check
    (one written before a structure's rules were tightened may not)."""
    keys = {"identify": ("hanzi",), "produce": ("answer_hanzi",),
            "rapid": ("answer_hanzi",), "conversation": ("sample_hanzi",)}
    try:
        return all(structure_problem(str(it.get(k) or ""), structure) is None
                   for stage, ks in keys.items() for it in payload.get(stage) or []
                   for k in ks)
    except (AttributeError, TypeError):
        return False


FIELDS = {"identify": [("hanzi", "pinyin", True)],
          "contrast": [("hanzi", "pinyin", False)],
          "produce": [("answer_hanzi", "answer_pinyin", True)],
          "rapid": [("answer_hanzi", "answer_pinyin", True)],
          "conversation": [("question_hanzi", "question_pinyin", False),
                           ("sample_hanzi", "sample_pinyin", True)]}
OPTIONAL = {"contrast"}          # a set without a good contrast stage is still a set


def _new_words(tokens, allowed):
    """Dictionary words to declare for unknown tokens: the token itself if
    it is one (下雨, 晴天, 电话), otherwise its unknown parts. None if some
    part isn't in the dictionary."""
    from dictionary_engine import cedict_gloss
    out = []
    for tok in tokens:
        if cedict_gloss(tok)[0]:
            out.append(tok)
            continue
        # split off the known part (喝啤酒 -> 啤酒); a word with no known part
        # that the dictionary lacks (冰厨) is not declared as its characters
        parts = unknown_words(tok, allowed)
        if not parts or "".join(parts) == tok or not all(cedict_gloss(p)[0] for p in parts):
            return None
        out += parts
    return out


def _auto_introduce(words, introduced):
    """Declare unstudied words the writer used but didn't list, while the
    budget allows: an everyday word in an otherwise good sentence (儿子,
    晴天) is taught on the spot instead of the sentence being thrown away.
    Only words the dictionary knows, so each comes with pinyin and English.
    Returns True if every word is now declared."""
    from dictionary_engine import cedict_gloss
    have = {w["hanzi"] for w in introduced}
    todo = [w for w in dict.fromkeys(words) if w not in have]
    if len(have) + len(todo) > MAX_INTRODUCED:
        return False
    found = []
    for w in todo:
        gloss = cedict_gloss(w)[0]
        if not gloss:
            return False
        # a few senses, not just the first: 多晚 needs "late", not "evening"
        senses = [re.sub(r"\s*\([^)]*\)", "", x).strip() for x in gloss.split(" / ")]
        english = " / ".join([x for x in senses if x][:3]) or gloss
        found.append({"hanzi": w, "pinyin": derive_pinyin(w), "english": english, "auto": True})
    introduced.extend(found)
    return True


def _item_problems(stage, it, structure, allowed, introduced):
    """What's wrong with one item (cleaning it in place), as a list. Unstudied
    words are declared automatically (within budget) only for an item with
    nothing else wrong, so a sentence that is dropped anyway spends none."""
    problems, missing_all = [], []
    if not isinstance(it, dict):
        return ["not an object"]
    for hz_key, py_key, needs_marker in FIELDS[stage]:
        hz = ap._force_simplified(str(it.get(hz_key) or "")).strip()
        it[hz_key] = hz
        if not hz:
            problems.append(f"empty {hz_key}")
            continue
        if has_erhua(hz, it.get(py_key, "")):
            problems.append(f"uses Beijing 儿 in '{hz}'")
        if re.search(r"[A-Za-z0-9]", hz):
            problems.append(f"digits or Latin letters in '{hz}'")
        if needs_marker:
            wrong = structure_problem(hz, structure)
            if wrong:
                problems.append(f"'{hz}' {wrong}")
        it[py_key] = _fix_pinyin(hz, it.get(py_key, ""))
        known_now = allowed | {w["hanzi"] for w in introduced}
        missing = unknown_words(hz, known_now)
        if missing:
            missing_all.append((hz, missing, unknown_tokens(hz, known_now)))
    if stage in ("identify", "contrast"):
        problem = mcq_problem(it)
        if problem:
            problems.append(problem)
        it["read"] = bool(it.get("read"))
    if stage in ("produce", "rapid") and not (it.get("situation") or it.get("prompt")):
        problems.append("missing prompt")
    if missing_all:
        words = _new_words([t for _hz, _ws, toks in missing_all for t in toks], allowed)
        # one new word in a sentence is learnable in context; three are not,
        # and would use up the budget other sentences need
        if problems or words is None or len(set(words)) > NEW_PER_SENTENCE * len(missing_all) \
                or not _auto_introduce(words, introduced):
            problems += [f"'{hz}' uses unstudied words {'、'.join(dict.fromkeys(ws))} "
                         f"- replace them or declare them in introduced_words"
                         for hz, ws, _toks in missing_all]
    return problems


def check_items(payload, structure, known_words, recent=(), introduced=None):
    """Check a draft item by item. Returns (good, problems, introduced):
    good maps each stage to the items that pass; problems lists what was
    wrong with the rest (labelled with the draft's own numbering, so the
    writer can find them); introduced is the words declared so far, the
    writer's own plus any added automatically."""
    known = set(known_words) | set(recent)
    good = {stage: [] for stage in STAGES}
    problems = []
    if not isinstance(payload, dict):
        return good, ["not a JSON object"], introduced or []
    introduced = list(introduced or [])
    seen = {w["hanzi"] for w in introduced}
    for w in payload.get("introduced_words") or []:
        if isinstance(w, dict) and w.get("hanzi") and w["hanzi"] not in seen \
                and len(introduced) < MAX_INTRODUCED:
            introduced.append(w)
            seen.add(w["hanzi"])
    allowed = allowed_set(known, structure)
    contrast = payload.get("contrast") if isinstance(payload.get("contrast"), dict) else None
    for stage in STAGES:
        items = (contrast or {}).get("items") if stage == "contrast" else payload.get(stage)
        if not isinstance(items, list):
            if stage not in OPTIONAL:
                problems.append(f"{stage}: missing")
            continue
        stage_allowed = allowed | grammar_words() if stage == "contrast" else allowed
        for i, it in enumerate(items, 1):
            wrong = _item_problems(stage, it, structure, stage_allowed, introduced)
            if wrong:
                problems += [f"[{stage} {i}]: {w}" for w in wrong]
            else:
                good[stage].append(it)
    return good, problems, introduced


def _key(stage, it):
    return it.get(FIELDS[stage][-1][0]) or json.dumps(it, ensure_ascii=False, sort_keys=True)


def _shortfall(bank):
    """{stage: how many more items it needs} for the required stages."""
    return {stage: COUNTS[stage][0] - len(bank[stage]) for stage in STAGES
            if stage not in OPTIONAL and len(bank[stage]) < COUNTS[stage][0]}


def _assemble(bank, contrast_with, introduced, structure):
    """A drill set from the items that passed, in the usual shape."""
    out = {stage: list(bank[stage]) for stage in STAGES if stage != "contrast"}
    out["contrast"] = ({"with": contrast_with or "", "items": list(bank["contrast"])}
                       if len(bank["contrast"]) >= COUNTS["contrast"][0] else None)
    text = "".join(sentences_in(out))
    out["introduced_words"] = [w for w in introduced if w["hanzi"] in text]
    out["structure_id"] = structure.id
    return out


def validate(payload, structure, known_words, recent=()):
    """Returns (cleaned payload, list of problems). Empty list = every item
    passes and every stage has its share."""
    good, problems, introduced = check_items(payload, structure, known_words, recent)
    if not isinstance(payload, dict):
        return payload, problems
    payload["introduced_words"] = introduced
    for stage in STAGES:
        lo, hi = COUNTS[stage]
        items = (payload.get("contrast") or {}).get("items") if stage == "contrast" \
            else payload.get(stage)
        if stage == "contrast" and not payload.get("contrast"):
            continue
        if not isinstance(items, list) or not (lo <= len(items) <= hi):
            problems.append(f"{stage}: needs {lo}-{hi} items")
    if not problems:
        problems += _recycling_problem(payload, recent)
    return payload, problems


def _recycling_problem(payload, recent):
    if len(recent) >= 3 and not any(w in "".join(sentences_in(payload)) for w in recent):
        return ["none of the recently learned words is used - recycle at least one: "
                + "、".join(recent[:10])]
    return []


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


_LABEL = re.compile(r"\b(identify|produce|contrast|rapid|conversation)\s*#?\s*(\d+)", re.I)


def flagged_items(problems):
    """The items a reviewer's problems point at, as {(stage, number)}; None
    if any problem doesn't name an item (a problem with the whole set)."""
    out = set()
    for p in problems:
        labels = _LABEL.findall(p)
        if not labels:
            return None
        out |= {(stage.lower(), int(n)) for stage, n in labels}
    return out


def generate(structure, known_words, china_pairs=(), contrasts=(), previous=(), recent=()):
    """Write, check and review a drill set. Returns the payload or None.

    A set has some twenty sentences, and one unstudied word or one
    reviewer's quibble used to throw all of them away - and the next draft,
    written from scratch, brought new slips of its own, so after three
    drafts there was often nothing. Now every item is judged on its own:
    those that pass are kept from draft to draft, and a later draft only
    has to supply what is still missing. Items the reviewer flags are
    dropped; the set is accepted once every stage still has its share."""
    bank = {stage: [] for stage in STAGES}
    keys = {stage: set() for stage in STAGES}
    introduced, contrast_with, feedback = [], None, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = build_prompt(structure, known_words, china_pairs, contrasts,
                              [_key(st_, it) for st_ in STAGES for it in bank[st_]] + list(previous),
                              feedback, recent)
        try:
            draft = _chat_json(GENERATION_MODEL, prompt, 0.7)
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
        good, problems, introduced = check_items(draft, structure, known_words, recent,
                                                 introduced)
        if isinstance(draft, dict) and isinstance(draft.get("contrast"), dict) \
                and good["contrast"] and not contrast_with:
            contrast_with = draft["contrast"].get("with")
        for stage in STAGES:
            for it in good[stage]:
                k = _key(stage, it)
                if k not in keys[stage] and len(bank[stage]) < COUNTS[stage][1]:
                    keys[stage].add(k)
                    bank[stage].append(it)
        short = _shortfall(bank)
        recycle = [] if short else _recycling_problem(
            _assemble(bank, contrast_with, introduced, structure), recent)
        if recycle and attempt < MAX_ATTEMPTS:
            # a preference worth one more draft (its items join the set),
            # not worth losing the set over on the last one
            problems = problems + recycle
        elif not short:
            candidate = _assemble(bank, contrast_with, introduced, structure)
            ok, review_problems, reviewed = review(candidate, structure)
            if ok:
                candidate["reviewed"] = reviewed
                return candidate
            flagged = flagged_items(review_problems)
            if flagged is not None:
                # drop what the reviewer flagged; the rest it judged sound
                for stage in STAGES:
                    items = candidate["contrast"]["items"] if stage == "contrast" and \
                        candidate.get("contrast") else candidate.get(stage) or []
                    for n, it in enumerate(items, 1):
                        if (stage, n) in flagged and it in bank[stage]:
                            bank[stage].remove(it)
                if not _shortfall(bank):
                    candidate = _assemble(bank, contrast_with, introduced, structure)
                    candidate["reviewed"] = reviewed
                    return candidate
            problems = review_problems
            short = _shortfall(bank)
        if recycle and not short:
            # make room: the next draft's items that recycle a word join the set
            for stage in ("rapid", "identify", "conversation"):
                if len(bank[stage]) >= COUNTS[stage][1]:
                    bank[stage].pop()
        need = "; ".join(f"{stage}: {n} more" for stage, n in short.items())
        feedback = "\n".join(f"- {p}" for p in problems[:15])
        if need:
            feedback += ("\n" if feedback else "") + \
                f"- Items that passed are kept. Still needed, at least: {need}. Write a full set again."
        logging.warning(f"[GRAMMAR] {structure.id} attempt {attempt}: kept "
                        f"{ {st_: len(v) for st_, v in bank.items()} }, still short {short}:\n{feedback}")
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
    today = today or clock.today()
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
