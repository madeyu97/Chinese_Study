# src/ai_prompter.py
"""
Sentences for Listen & speak: written by the model when the bank and the
Tatoeba file have nothing for a word, and wrong-answer options (distractors)
for human-written sentences.

Every written sentence passes a mechanical gate before a reviewer model from
a different family sees it:
  - the target word is in it (as a word, clitics allowed: rumahnya)
  - no Indonesian forms (bisa, mau, karena, uang…) - models drift there
  - numbers as words, and the same numbers as the English
  - at most one word from outside the 5,000-word list (sentences stay
    learnable)
  - not a sentence a learner has flagged
Rejected drafts are rewritten with the problems fed back, up to three times;
nothing that fails is shown.

"dia", "beliau" and "-nya" don't mark gender, so the English says
He/She, him/her, his/her - and distractors never differ on the pronoun
alone.
"""

import logging
import re
from functools import lru_cache

import llm
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from malay import known as kn, morphology, normalise

MAX_OFF_LIST = 1

# ----------------------------------------------------------------------
# Spoken Malaysian Malay: a reference for the writer, not a list to force in
# ----------------------------------------------------------------------
COLLOQUIAL_NOTES = {
    "tak": "not (= tidak)",
    "nak": "want / going to (= hendak, mahu)",
    "dah": "already (= sudah)",
    "je": "only / just (= sahaja)",
    "ni / tu": "this / that (= ini / itu), after the noun: kereta ni",
    "kat": "at / in (= di, dekat)",
    "sikit": "a little (= sedikit)",
    "takde": "there isn't / don't have (= tiada, tak ada)",
    "lah": "softens or presses a statement or request: Jomlah! Makanlah dulu.",
    "kan": "tag 'right?': Dia dah balik, kan?",
    "ke": "yes/no question particle in speech: Awak lapar ke? (also the preposition 'to')",
    "kot": "'maybe / I think', sentence-final: Dia dah tidur kot.",
    "jom": "let's: Jom makan!",
    "kena": "have to; also marks something done to you: kena marah = get told off",
    "tengok": "look / watch (everyday word for lihat)",
    "pasal": "about / because",
    "awak": "you - the polite everyday choice",
    "aku / kau": "I / you between close friends or family only",
    "korang / diorang": "you all / they (casual)",
}

INDONESIAN_EXAMPLES = ("boleh not bisa, mahu/nak not mau, kerana not karena, wang/duit "
                       "not uang, kereta not mobil, faham not paham/mengerti, sahaja/je "
                       "not aja, beritahu not bilang, tidak/tak not nggak/gak, "
                       "sudah/dah not udah, pejabat not kantor, bilik not kamar")


def _colloquial_reference():
    return "\n".join(f"   {k}: {v}" for k, v in COLLOQUIAL_NOTES.items())


# ----------------------------------------------------------------------
# Pronouns: Malay doesn't mark gender
# ----------------------------------------------------------------------
def gender_neutral(malay):
    """Does the sentence use dia / beliau / -nya, which can be he or she?"""
    for tok in normalise.tokens(malay):
        if tok in ("dia", "beliau") or "nya" in morphology.analyse(tok).clitics:
            return True
    return False


# after these, "her" is an object (tell her today), not a possessive (her book)
_NOT_NOUNS = ("today|tomorrow|yesterday|tonight|now|later|again|soon|already|yet|too|also|"
              "back|up|down|out|off|away|here|there|that|to|a|an|the|about|and|but|or|so|in|"
              "on|at|with|for|from|because|when|if|every|this|last|next|all|before|after|once|"
              "twice|well|very|much|anything|something|everything|nothing|what|how|why|where")


def normalize_pronouns(text):
    """He -> He/She, him -> him/her, his -> his/her, her -> his/her or
    him/her. Safe to run twice."""
    if not text:
        return text
    obj = rf"(?!\s+(?:{_NOT_NOUNS})\b)"
    subs = [(r"(?<!/)\b(?:He|She)\b(?!/)", "He/She"), (r"(?<!/)\b(?:he|she)\b(?!/)", "he/she"),
            (r"(?<!/)\bHim\b(?!/)", "Him/Her"), (r"(?<!/)\bhim\b(?!/)", "him/her"),
            (r"(?<!/)\bHis\b(?!/)", "His/Her"), (r"(?<!/)\bhis\b(?!/)", "his/her"),
            (rf"(?<!/)\bHer\b(?=\s+\w){obj}(?!/)", "His/Her"),
            (rf"(?<!/)\bher\b(?=\s+\w){obj}(?!/)", "his/her"),
            (r"(?<!/)\bHer\b(?!/)", "Him/Her"), (r"(?<!/)\bher\b(?!/)", "him/her")]
    for pattern, repl in subs:
        text = re.sub(pattern, repl, text)
    return text


# ----------------------------------------------------------------------
# Numbers in the English, to compare with the Malay
# ----------------------------------------------------------------------
_EN_UNITS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_EN_TENS = {w: 10 * n for n, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def numbers_in_english(text):
    found, total, chunk, active = set(), 0, 0, False

    def flush():
        nonlocal total, chunk, active
        if active:
            found.add(total + chunk)
        total = chunk = 0
        active = False

    for tok in re.findall(r"[a-z]+|\d+", (text or "").lower().replace("-", " ")):
        if tok.isdigit():
            flush()
            found.add(int(tok))
        elif tok in _EN_UNITS:
            chunk, active = chunk + _EN_UNITS[tok], True
        elif tok in _EN_TENS:
            chunk, active = chunk + _EN_TENS[tok], True
        elif tok == "hundred":
            chunk, active = (chunk or 1) * 100, True
        elif tok in ("thousand", "million"):
            total, chunk, active = total + (chunk or 1) * (1000 if tok == "thousand" else 1_000_000), 0, True
        elif tok == "and" and active:
            continue
        else:
            flush()
    flush()
    return found


def number_mismatch(malay, english):
    """Both sides state numbers and none of them agree (tiga as 'four')."""
    ms, en = normalise.numbers_in(malay), numbers_in_english(english)
    return bool(ms and en and ms.isdisjoint(en))


# ----------------------------------------------------------------------
# Sentences stay inside the word list
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _list_allowed():
    return kn.allowed_set(morphology.default_model().known)


def off_list(malay):
    """Words in the sentence that are not on the 5,000-word list (nor a
    form of a listed word)."""
    return kn.unknown_words(malay, _list_allowed())


def gate(malay, english, target, blocked=()):
    """Mechanical problems with a written sentence, as a list of strings."""
    problems = []
    if not malay.strip() or not english.strip():
        return ["empty sentence or translation"]
    from word_content import contains
    if target and not contains(malay, target):
        problems.append(f"target '{target}' missing from the sentence")
    indo = normalise.indonesian_in(malay)
    if indo:
        problems.append("Indonesian, not Malaysian: "
                        + ", ".join(f"{f} (say {m})" for f, m in indo))
    if re.search(r"\d", malay):
        problems.append("digits in the Malay - write numbers as words")
    if number_mismatch(malay, english):
        problems.append(f"numbers disagree: the Malay says {sorted(normalise.numbers_in(malay))}, "
                        f"the English {sorted(numbers_in_english(english))}")
    extra = [w for w in off_list(malay) if w != target]
    if len(extra) > MAX_OFF_LIST:
        problems.append("uses uncommon words (" + ", ".join(extra)
                        + ") - use everyday words instead")
    if malay in blocked:
        problems.append("a sentence the learner flagged as wrong")
    if "/" in malay:
        problems.append("a slash in the Malay")
    return problems


# ----------------------------------------------------------------------
# Review
# ----------------------------------------------------------------------
def _flagged_lines(flagged_examples):
    if not flagged_examples:
        return ""
    lines = "\n".join(f"- {s}" + (f"  ({r})" if r else "") for s, r in flagged_examples[:8])
    return ("\nThe learner has flagged these sentences as wrong - reject anything with the "
            "same kind of mistake:\n" + lines + "\n")


def review_sentence(malay, english, flagged_examples=None):
    """{acceptable, problems}. A different model family from the writer."""
    prompt = f"""
You are a strict native-speaker reviewer of MALAYSIAN Malay teaching material.
Judge whether this sentence is grammatical, natural Malay that a Malaysian
would actually say, and whether the English translation is accurate.

SENTENCE: {malay}
CLAIMED MEANING: {english}
{_flagged_lines(flagged_examples)}
Check with particular care:
- It is Malaysian Malay, NOT Indonesian: {INDONESIAN_EXAMPLES}. Indonesian
  words, spellings or usage are errors.
- Affixes are right: meN- for an active verb with an object, di- for the
  passive, ber- for an intransitive/having verb, -kan / -i used correctly.
- Colloquial forms (tak, nak, dah, ni, tu, je, kat, lah, kan) are fine and
  must NOT be marked as errors; mixing registers awkwardly is.
- Word choice is semantically right, and the sentence makes real-world sense.
- The English matches the Malay exactly (numbers, negation, time, who).

Return ONLY raw JSON: {{"acceptable": true/false, "problems": "<empty if acceptable, else one line>"}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = llm.chat_json(model, prompt, 0)
            return {"acceptable": bool(v.get("acceptable", False)) and not str(v.get("problems") or "").strip(),
                    "problems": str(v.get("problems") or "")}
        except Exception as e:
            logging.warning(f"[REVIEW] {model} failed: {e}")
    # a broken reviewer must not block study: the mechanical gate still applied
    return {"acceptable": True, "problems": "", "unreviewed": True}


# ----------------------------------------------------------------------
# Distractors
# ----------------------------------------------------------------------
def _clean_distractors(raw, correct, neutral):
    if neutral:
        correct = normalize_pronouns(correct)
        raw = [normalize_pronouns(d) for d in raw]
    seen, out = {correct.strip().lower()}, []
    for d in raw:
        key = d.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(d.strip())
    return out


def generate_distractors_for(malay, english_correct, n=3):
    """Wrong English options for an existing (human-written) sentence. The
    sentence itself is never touched; only the options come from the model."""
    neutral = gender_neutral(malay)
    pronoun_rule = ("The sentence uses dia/beliau/-nya, which can be he or she: write He/She, "
                    "him/her, his/her, and never make a distractor differ only on the pronoun."
                    if neutral else "")
    prompt = f"""
Create exactly {n} plausible WRONG English translations (distractors) for a
listening exercise in Malaysian Malay.

MALAY SENTENCE: {malay}
CORRECT TRANSLATION: {english_correct}
{pronoun_rule}

Each distractor must be clearly wrong for a listener who understood the
sentence, but tempting for one who misheard a single element: a content
word (especially one that sounds alike: bawa/bawah, tahu/tahun), a number,
negation (tak/tidak/bukan/belum), time or tense (dah, nak, sedang), or who
did what (an affix: memukul vs dipukul). Same register and length as the
correct translation.

Return ONLY raw JSON: {{"english_distractors": ["<d1>", "<d2>", "<d3>"]}}
""".strip()
    try:
        data = llm.chat_json(GENERATION_MODEL, prompt, 0.7)
        raw = [str(d) for d in data.get("english_distractors", []) if str(d).strip()]
    except Exception as e:
        logging.error(f"[DISTRACTORS] failed: {e}")
        return []
    return _clean_distractors(raw, english_correct, neutral)[:n]


# ----------------------------------------------------------------------
# Writing a sentence
# ----------------------------------------------------------------------
def build_prompt(word, mode, feedback="", flagged_examples=None):
    target, english = word["malay"], word.get("english", "")
    if mode == "recall":
        task = f"""RECALL MODE: the learner will see ONLY the English and must say the Malay
from memory, so the Malay must be PREDICTABLE from the English.
1. Use '{target}' ("{english}") in a SHORT, SIMPLE sentence of 4-8 words.
2. Use only words the English implies - no idiomatic additions. BAD: English
   "Her cat is cute" -> "Kucing yang dia bela tu comel" (adds bela). GOOD:
   "Kucing dia comel." """
    else:
        task = f"""Write ONE natural everyday sentence (5-10 words) using '{target}'
("{english}") in a real situation."""
    flagged = ""
    if flagged_examples:
        flagged = ("\nSENTENCES THE LEARNER FLAGGED AS WRONG (never produce these, or ones with "
                   "the same kind of mistake):\n"
                   + "\n".join(f"   - {s}" + (f"  ({r})" if r else "") for s, r in flagged_examples[:8]))
    return f"""
You are an expert tutor of MALAYSIAN Malay (Bahasa Melayu as spoken in Malaysia).

{task}

Spoken Malaysian Malay - use these only where natural, never forced:
{_colloquial_reference()}

RULES:
1. Malaysian Malay only, never Indonesian: {INDONESIAN_EXAMPLES}.
2. Everyday words a learner meets early; no rare or literary words.
3. No invented names - use pronouns (saya, awak, dia, kami, kita, mereka).
4. Numbers as words (tiga, dua puluh), never digits.
5. Affixes correct: meN- active with an object, di- passive, ber- intransitive.
6. "dia" can be he or she: write the English as He/She (him/her, his/her).
{flagged}
{("YOUR PREVIOUS ATTEMPT WAS REJECTED:\n" + feedback + "\nWrite a NEW sentence that fixes this.") if feedback else ""}

Return ONLY raw JSON:
{{"malay": "<sentence>", "english_correct": "<accurate translation>",
  "english_distractors": ["<d1>", "<d2>", "<d3>"],
  "grammar_note": "<one short line on a useful point in the sentence, or empty>"}}
""".strip()


def generate_exercise(word, mode="listen", blocked_sentences=None, flagged_examples=None):
    """A checked sentence for `word`, or None. mode: listen (with distractors)
    or recall (English shown, Malay said)."""
    blocked = set(blocked_sentences or ())
    target = word["malay"]
    feedback = ""
    for attempt in range(1, llm.MAX_ATTEMPTS + 1):
        try:
            cand = llm.chat_json(GENERATION_MODEL, build_prompt(word, mode, feedback, flagged_examples), 0.8)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or ("rate" in msg and "limit" in msg):
                raise
            logging.warning(f"[GEN] attempt {attempt}: {e}")
            feedback = "- the reply was not valid JSON"
            continue
        malay = re.sub(r"\s+", " ", str(cand.get("malay") or "")).strip()
        english = str(cand.get("english_correct") or "").strip()
        problems = gate(malay, english, target, blocked)
        review = None
        if not problems:
            review = review_sentence(malay, english, flagged_examples)
            if not review["acceptable"]:
                problems.append(f"reviewer: {review['problems']}")
        if problems:
            feedback = f"Sentence: {malay}\n" + "\n".join(f"- {p}" for p in problems)
            logging.warning(f"[GEN] {target} attempt {attempt} rejected: {'; '.join(problems)}")
            continue
        neutral = gender_neutral(malay)
        if neutral:
            english = normalize_pronouns(english)
        raw = [str(d) for d in cand.get("english_distractors") or [] if str(d).strip()]
        distractors = _clean_distractors(raw, english, neutral)
        if mode == "listen" and len(distractors) < 2:
            feedback = "- give three distinct wrong translations"
            continue
        return {"malay": malay, "english_correct": english, "english_distractors": distractors[:3],
                "grammar_note": str(cand.get("grammar_note") or "").strip(),
                "target": target, "generation_mode": mode, "source": "generated",
                "reviewed": not (review or {}).get("unreviewed")}
    return None
