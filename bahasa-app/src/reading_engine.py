# src/reading_engine.py
"""
Graded reading: short passages in standard Malay where at least 95% of the
words are ones you know.

Coverage counts every running word, through roots and voice forms (membaca
counts if you know baca), with function words and Malaysian place names
free. A passage below MIN_COVERAGE for you is never shown.

Where passages come from, in order:
  1. the shared reading bank - passages written for either learner, shown to
     you once they fit your vocabulary;
  2. a new passage, written by the model from your words, then checked in
     code (coverage, Indonesian forms, digits, colloquial forms, every new
     word declared with its meaning, comprehension keys in range) and read
     by a reviewer. A draft that fails is rewritten with the problems fed
     back, as everywhere else in the app;
  3. "short reads": Tatoeba sentences you can read, when no passage fits and
     the model can't be reached.

Each word on screen carries its root, affixes and meaning, shown on tap.
Words you haven't met are marked, and can be sent to the Words page as the
next new words.
"""

import html
import logging
import re
import time

import llm
import word_content as wc
from config import GENERATION_MODEL, GRADING_MODEL, REVIEW_MODEL
from malay import known as kn, morphology, normalise

MIN_COVERAGE = 0.95
MAX_NEW = 4
MIN_KNOWN = 40                 # reading opens at about this many words
PROMPT_WORDS = 450             # known words listed in the writer's prompt
PLACES = {"malaysia", "pulau", "pinang", "penang", "georgetown", "ipoh", "kuala", "lumpur",
          "melaka", "johor", "kedah", "perak", "langkawi", "sabah", "sarawak", "selangor",
          "singapura", "thailand", "cameron", "highlands"}
TOPICS = ("breakfast at a kopitiam", "a morning at the wet market", "rain in the afternoon",
          "a visit to the clinic", "a sore back after work", "a family weekend",
          "taking the bus in Penang", "a trip to Ipoh", "cooking dinner at home",
          "a neighbour's new cat", "looking for a house to rent", "a walk on the beach",
          "a phone call to a friend", "buying medicine at the pharmacy", "a hot day",
          "learning Malay", "a birthday", "fixing a broken fan")
_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
_COLLOQUIAL = {"tak", "nak", "dah", "je", "kat", "ni", "tu", "takde", "camne", "korang", "diorang"}


def level(known_count):
    """(min sentences, max sentences, max words) for this vocabulary size."""
    if known_count < 150:
        return 3, 4, 45
    if known_count < 600:
        return 4, 5, 65
    return 5, 6, 85


# ======================================================================
# Coverage and the words on screen
# ======================================================================
def allowed_for(known_words, extra=()):
    return kn.allowed_set(list(known_words) + sorted(PLACES), extra)


def coverage(text, allowed):
    """{total, unknown: [unique, in order], unknown_count (running), coverage}."""
    toks = normalise.tokens(text)
    misses = [t for t in toks if not kn.is_known(t, allowed)]
    return {"total": len(toks), "unknown": list(dict.fromkeys(misses)),
            "unknown_count": len(misses),
            "coverage": (1 - len(misses) / len(toks)) if toks else 0.0}


def passage_text(payload):
    return " ".join(s["malay"] for s in payload.get("sentences", []))


def annotate(text, allowed, glosses):
    """The passage cut into pieces for display: [{text, word, known, parts,
    gloss}], where word is None for spaces and punctuation."""
    out, pos = [], 0
    for m in _WORD.finditer(text):
        if m.start() > pos:
            out.append({"text": text[pos:m.start()], "word": None})
        raw = m.group(0)
        tok = raw.lower()
        _t, parts, gloss = (wc.breakdown(tok, glosses) or [(tok, "", "")])[0]
        out.append({"text": raw, "word": tok, "known": kn.is_known(tok, allowed),
                    "parts": parts, "gloss": gloss})
        pos = m.end()
    if pos < len(text):
        out.append({"text": text[pos:], "word": None})
    return out


CSS = """<style>
.rd {font-size:1.35rem; line-height:2.15; margin:8px 0 4px;}
.rd .w {position:relative; cursor:pointer; border-radius:4px; padding:0 1px;
        outline:none; border-bottom:1px dotted rgba(120,144,156,.6);}
.rd .w.new {background:rgba(245,200,76,.38);}
.rd .w .tip {display:none; position:absolute; left:0; top:1.75em; z-index:20;
        background:#263238; color:#fff; font-size:.8rem; line-height:1.35;
        padding:5px 9px; border-radius:6px; width:max-content; max-width:15em;
        white-space:normal; box-shadow:0 2px 6px rgba(0,0,0,.25);}
.rd .w:hover .tip, .rd .w:focus .tip {display:block;}
.rd .tip b {color:#ffd54f;}
</style>"""


def render(pieces):
    """HTML for the passage: each word shows its parts and meaning when
    tapped (focus) or hovered; unmet words are highlighted."""
    out = []
    for p in pieces:
        if p["word"] is None:
            out.append(html.escape(p["text"]))
            continue
        tip = f"<b>{html.escape(p['word'])}</b>"
        if p["parts"]:
            tip += f" · {html.escape(p['parts'])}"
        tip += f"<br>{html.escape(p['gloss'] or '—')}"
        cls = "w" if p["known"] else "w new"
        out.append(f'<span class="{cls}" tabindex="0">{html.escape(p["text"])}'
                   f'<span class="tip">{tip}</span></span>')
    return CSS + f'<div class="rd">{"".join(out)}</div>'


# ======================================================================
# Writing a passage
# ======================================================================
def build_prompt(known_words, recent=(), topic="", feedback=""):
    lo, hi, max_words = level(len(known_words))
    listed = list(dict.fromkeys(list(recent) + list(known_words)))[:PROMPT_WORDS]
    return f"""
Write a short reading passage for a learner of MALAYSIAN Malay.

THE LEARNER KNOWS THESE WORDS (and common grammar words):
{", ".join(listed)}

RULES
1. {lo}-{hi} sentences, at most {max_words} words in all, telling one connected
   everyday story or scene{f" about: {topic}" if topic else ""}.
2. Standard written Malaysian Malay, as in a newspaper or a school reader:
   tidak, hendak/mahu, sudah, sahaja, di, ini, itu - not colloquial tak, nak,
   dah, je, kat, ni, tu.
3. Malaysian, never Indonesian (boleh not bisa, kerana not karena, wang not
   uang, kereta not mobil, faham not paham, sahaja not saja/aja).
4. Build it from the words above. Forms of them count (membaca from baca). You
   may use at most {MAX_NEW} other words; list each in "new_words" with its
   English meaning in this passage.
5. No personal names: use roles (seorang doktor, kawan saya, jiran saya).
   Malaysian place names are fine. Write numbers as words, no digits.
6. Use some of these recently learned words if they fit: {", ".join(recent) or "none"}.
7. A Malay title of two to five words. An accurate English translation of
   every sentence. Two or three comprehension questions IN ENGLISH, each
   with three English options and the index of the right one (0-2).
{("PREVIOUS DRAFT WAS REJECTED. Fix every one of these problems:" + chr(10) + feedback) if feedback else ""}

Return ONLY JSON:
{{"title": "...", "title_english": "...",
  "sentences": [{{"malay": "...", "english": "..."}}],
  "new_words": [{{"malay": "...", "english": "..."}}],
  "questions": [{{"question": "...", "options": ["...", "...", "..."], "answer": 0}}]}}
""".strip()


def validate(payload, known_words):
    """(payload cleaned, problems). Every check here is mechanical."""
    problems = []
    if not isinstance(payload, dict):
        return payload, ["not a JSON object"]
    lo, hi, max_words = level(len(known_words))
    sents = [s for s in (payload.get("sentences") or []) if isinstance(s, dict)]
    sents = [{"malay": re.sub(r"\s+", " ", str(s.get("malay") or "")).strip(),
              "english": str(s.get("english") or "").strip()} for s in sents]
    payload["sentences"] = sents
    if not (lo <= len(sents) <= hi + 1):
        problems.append(f"needs {lo}-{hi} sentences, got {len(sents)}")
    if not str(payload.get("title") or "").strip():
        problems.append("missing title")
    new = [{"malay": str(w.get("malay") or "").strip().lower(),
            "english": str(w.get("english") or "").strip()}
           for w in (payload.get("new_words") or []) if isinstance(w, dict)]
    new = [w for w in new if w["malay"]]
    payload["new_words"] = new
    if len(new) > MAX_NEW:
        problems.append(f"{len(new)} new words - at most {MAX_NEW}")
    if any(" " in w["malay"] or not w["english"] for w in new):
        problems.append("each new word must be one word with its English meaning")
    text = passage_text(payload)
    words = len(normalise.tokens(text))
    if words > max_words * 1.15:
        problems.append(f"{words} words - at most {max_words}")
    for i, s in enumerate(sents, 1):
        if not s["malay"] or not s["english"]:
            problems.append(f"sentence {i}: Malay and English both needed")
        if re.search(r"\d", s["malay"]):
            problems.append(f"sentence {i}: digits - write numbers as words")
        indo = normalise.indonesian_in(s["malay"])
        if indo:
            problems.append(f"sentence {i}: Indonesian " + ", ".join(
                f"{f} (Malaysian: {m})" for f, m in indo))
        coll = [t for t in normalise.tokens(s["malay"]) if t in _COLLOQUIAL]
        if coll:
            problems.append(f"sentence {i}: colloquial {', '.join(dict.fromkeys(coll))} - "
                            "use the standard form")
    title_indo = normalise.indonesian_in(str(payload.get("title") or ""))
    if title_indo:
        problems.append("title: Indonesian " + ", ".join(f for f, _m in title_indo))
    base = allowed_for(known_words)
    undeclared = coverage(text, allowed_for(known_words, [w["malay"] for w in new]))["unknown"]
    if undeclared:
        problems.append("words the learner doesn't know and you didn't declare: "
                        + ", ".join(undeclared[:10]))
    cov = coverage(text, base)
    if cov["total"] and cov["coverage"] < MIN_COVERAGE:
        problems.append(f"only {cov['coverage']:.0%} of the words are known - at least "
                        f"{MIN_COVERAGE:.0%} needed; use fewer new words")
    qs = []
    for q in payload.get("questions") or []:
        if not isinstance(q, dict):
            continue
        opts = [str(o).strip() for o in (q.get("options") or [])]
        ans = q.get("answer")
        if len(opts) != 3 or len(set(o.lower() for o in opts)) != 3 or not all(opts) \
                or not isinstance(ans, int) or not 0 <= ans < 3 or not str(q.get("question") or "").strip():
            problems.append(f"question '{q.get('question')}': needs 3 different options and an answer 0-2")
            continue
        qs.append({"question": str(q["question"]).strip(), "options": opts, "answer": ans})
    payload["questions"] = qs
    if not 2 <= len(qs) <= 3:
        problems.append("needs 2-3 comprehension questions")
    return payload, problems


def review(payload):
    """(ok, problems, reviewed). Reviewers down: accepted unreviewed, and
    the page shows it once without storing it."""
    lines = [f"[title] {payload.get('title')} = {payload.get('title_english')}"]
    lines += [f"[{i}] {s['malay']} = {s['english']}" for i, s in enumerate(payload["sentences"], 1)]
    lines += [f"[new word] {w['malay']} = {w['english']}" for w in payload["new_words"]]
    lines += [f"[question] {q['question']} options {q['options']} key {q['answer']}"
              for q in payload["questions"]]
    prompt = f"""
You are a strict native-speaker reviewer of MALAYSIAN Malay reading material
for learners. Standard written Malay is expected (tidak, sudah, hendak).

Check every line:
- Natural, grammatical Malay a Malaysian would write? Do the sentences make
  one coherent passage?
- Malaysian, NOT Indonesian, in words, spelling and usage?
- Is each English translation accurate? Are the new-word meanings right?
- Is every comprehension question answerable from the passage, with the
  key pointing at the right option and only one option right?

{chr(10).join(lines)}

Return ONLY JSON: {{"acceptable": true/false, "problems": ["<line>: <problem>", ...]}}
""".strip()
    for model in (REVIEW_MODEL, GRADING_MODEL):
        try:
            v = llm.chat_json(model, prompt, 0)
            probs = [str(p) for p in (v.get("problems") or []) if str(p).strip()]
            return bool(v.get("acceptable", False)) and not probs, probs, True
        except Exception as e:
            logging.warning(f"[READING REVIEW] {model} failed: {e}")
    return True, [], False


def generate(known_words, recent=(), topic=""):
    """Write, check and review a passage. Returns the payload or None."""
    import json
    feedback = ""
    for attempt in range(1, llm.MAX_ATTEMPTS + 1):
        try:
            payload = llm.chat_json(GENERATION_MODEL, build_prompt(known_words, recent, topic, feedback),
                                    0.7)
        except json.JSONDecodeError as e:
            feedback = f"- output was not valid JSON ({e})"
            continue
        except Exception as e:
            logging.warning(f"[READING] attempt {attempt}: API error {e}")
            time.sleep(min(20, 5 * attempt))
            continue
        payload, problems = validate(payload, known_words)
        if not problems:
            ok, problems, reviewed = review(payload)
            if ok:
                payload.update({"reviewed": reviewed, "source": "generated", "topic": topic})
                return payload
        feedback = "\n".join(f"- {p}" for p in problems[:12])
        logging.warning(f"[READING] attempt {attempt} rejected:\n{feedback}")
    return None


# ======================================================================
# Choosing what to read
# ======================================================================
def pick_passage(candidates, allowed, read_ids=()):
    """The best stored passage for this learner: unread, at or above
    MIN_COVERAGE, the most familiar first (fewest unknown words, then the
    longest). candidates: [{id, payload}]. None if nothing fits."""
    read_ids = set(read_ids)
    scored = []
    for c in candidates:
        if c["id"] in read_ids:
            continue
        cov = coverage(passage_text(c["payload"]), allowed)
        if cov["total"] and cov["coverage"] >= MIN_COVERAGE:
            scored.append((cov["unknown_count"], -cov["total"], c["id"], c))
    return min(scored)[3] if scored else None


def short_reads(rows, allowed, recent=(), n=5, exclude=()):
    """Tatoeba sentences you can read (at most one unknown word each),
    preferring ones with recently learned words, as a passage-shaped
    payload. rows: tatoeba.pairs()."""
    exclude = set(exclude)
    scored = []
    for r in rows:
        if r["malay"] in exclude:
            continue
        cov = coverage(r["malay"], allowed)
        if cov["total"] < 4 or cov["unknown_count"] > 1:
            continue
        fresh = len(kn.words_used(r["malay"], recent)) if recent else 0
        scored.append((cov["unknown_count"], -fresh, len(r["malay"]), r["malay"], r))
    scored.sort(key=lambda x: x[:4])
    picked = [x[4] for x in scored[:n]]
    if not picked:
        return None
    return {"title": "Bacaan pendek", "title_english": "Short reads", "source": "tatoeba",
            "sentences": [{"malay": r["malay"], "english": r["english"],
                           "tatoeba_id": r.get("tatoeba_id"), "author": r.get("author")}
                          for r in picked],
            "new_words": [], "questions": []}


def gloss_new_words(payload, unknown, glosses):
    """[(word, meaning)] for the words new to this learner: the passage's
    own glossary first, then the word list."""
    declared = {w["malay"]: w["english"] for w in payload.get("new_words", [])}
    out = []
    for tok in unknown:
        a = morphology.analyse(tok)
        meaning = declared.get(tok) or glosses.get(tok) or glosses.get(a.root) or ""
        out.append((tok, wc.short_meaning(meaning) if meaning else ""))
    return out
