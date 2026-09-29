# src/pages/1_Words.py
"""
📚 Words - vocabulary learned through chunks, natural sentences and
retrieval, not as a list.

Each item tests one skill of one word in one of five ways:
  Read → meaning      a sentence with the word highlighted
  Listen → meaning    the word, then a sentence, heard not seen
  Fill the gap        the sentence with the word blanked (type or say it)
  Meaning → Chinese   produce the word from its meaning
  Say it              a situation to answer aloud using the word
New words are introduced through their chunks and sentences first, then
checked straight away and again a few items later. Misses come back once in
the same session. Content for upcoming items is prepared in the background.

Pinyin fades as a word matures: shown with the answer while you're still
learning a word, tucked behind a tap once you've known it for three weeks.
As a step of today's plan, the session starts straight away with the plan's
limits.
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import streamlit as st

import db_manager as db
import grammar_curriculum as gc
import today_plan as tp
import vocab_engine as ve
import word_content as wc
import word_diagnosis as wd
from ai_prompter import _force_simplified
from audio_engine import create_audio_file
from auth import require_login, sidebar_user_badge
from config import VOCAB_BACKLOG_SOFT, VOCAB_NEW_PER_DAY, VOCAB_NEW_PER_SESSION
from speech_engine import transcribe_audio

st.set_page_config(page_title="Words", page_icon="📚", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state
HIGHLIGHT = "color:#d9480f;font-weight:600"
MAX_ENRICH = 6          # background content writes per session for review words
MAX_REMEDIES = 3        # diagnoses acted on per session, so repair never swamps review
MATURE_DAYS = 21        # from here on, pinyin waits behind a tap


def reset():
    for k in [k for k in S if k.startswith("wd_")]:
        del S[k]


if S.get("wd_date") and S.wd_date != str(date.today()):
    reset()
if "words_exec" not in S:
    S.words_exec = ThreadPoolExecutor(max_workers=2)

with st.sidebar:
    sidebar_user_badge()
    tp.sidebar("words", reset)
    if "wd_items" in S and S.wd_items:
        st.caption(f"{min(S.wd_i, len(S.wd_items))} of {len(S.wd_items)} done")
        if not S.get("wd_plan") and st.button("End session"):
            reset()
            st.rerun()

st.title("📚 Words")


# ----------------------------------------------------------------------
# start screen
# ----------------------------------------------------------------------
def begin(in_plan=False, review_cap=None, new_cap=None, unlocks=True):
    plan = db.plan_word_session(USER_ID, review_cap=review_cap, new_cap=new_cap,
                                unlocks=unlocks)
    reset()
    S.wd_items, S.wd_i, S.wd_results = plan["items"], 0, []
    S.wd_content, S.wd_futures, S.wd_retried, S.wd_rot = {}, {}, set(), {}
    S.wd_plan, S.wd_t0 = in_plan, time.time()
    S.wd_date, S.wd_enriched, S.wd_remedies = str(date.today()), 0, 0
    if plan["items"]:
        ids = {it["word"]["id"] for it in plan["items"]}
        S.wd_mature = {vid for (vid, skill), t in db.word_tracks(USER_ID, ids).items()
                       if skill == ve.RECOGNITION and (t.get("interval") or 0) >= MATURE_DAYS}
        S.wd_pool = db.word_pool(USER_ID)
        S.wd_known = db.grammar_known_vocab(USER_ID)


if "wd_items" not in S and tp.active("words"):
    p_ = tp.params("words")
    begin(True, p_.get("reviews"), p_.get("new"), p_.get("unlocks", True))
    st.rerun()

if "wd_items" not in S:
    db.sync_word_skills(USER_ID)
    due = db.count_due(USER_ID)
    room = ve.new_word_allowance(due, db.introduced_today(USER_ID), VOCAB_NEW_PER_SESSION,
                                 VOCAB_NEW_PER_DAY, VOCAB_BACKLOG_SOFT)
    st.markdown(f"**{due}** reviews due · up to **{room}** new words this session")
    if due > VOCAB_BACKLOG_SOFT:
        st.caption("Reviews have built up, so new words are held back until you catch up.")
    st.caption("Words come with their chunks and sentences. Recognising and producing are "
               "tracked separately; you start producing a word once you recognise it reliably.")
    net = db.network_stats(USER_ID)
    st.caption(f"Your network: recognising **{net['recognition']}** words · producing "
               f"**{net['production']}** · **{net['grammar']}** grammar structures practised")
    working = db.open_diagnoses(USER_ID)
    if working:
        st.markdown("**Words you're working on:** " + " · ".join(
            f"{d['chinese']} ({wd.CAUSE_TITLES[d['cause']].lower()})" for d in working.values()))
    if st.button("▶️ Start", type="primary", width="stretch"):
        begin()
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# content, prepared ahead in the background
# ----------------------------------------------------------------------
def needs_writing(item):
    return item["kind"] in ("new", "step2", "unlock") or item["skill"] == ve.PRODUCTION


def _job(word, allow, known):
    return db.word_content_for(USER_ID, word, allow_generate=allow, known=known)


def prefetch(start, ahead=4):
    for it in S.wd_items[start:start + ahead]:
        vid = it["word"]["id"]
        if vid not in S.wd_content and vid not in S.wd_futures:
            S.wd_futures[vid] = S.words_exec.submit(_job, it["word"], needs_writing(it), S.wd_known)


def content_for(item):
    vid = item["word"]["id"]
    if vid not in S.wd_content:
        fut = S.wd_futures.pop(vid, None) or \
            S.words_exec.submit(_job, item["word"], needs_writing(item), S.wd_known)
        with st.spinner("Preparing this word…"):
            try:
                payload, cid = fut.result(timeout=90)
            except Exception:
                payload, cid = wc.fallback_content(item["word"]), None
        S.wd_content[vid] = (payload, cid)
        # a review word still on stand-in content gets proper content written
        # in the background, ready for next time
        if payload.get("source") != "generated" and S.wd_enriched < MAX_ENRICH \
                and ve.can_produce(item["word"]):
            S.wd_enriched += 1
            S.words_exec.submit(_job, item["word"], True, S.wd_known)
    return S.wd_content[vid]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def play(text):
    cache = S.setdefault("wd_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3")


def big(html, size="1.9rem"):
    st.markdown(f"<div style='font-size:{size};line-height:1.5'>{html}</div>",
                unsafe_allow_html=True)


def marked(sentence, target):
    return sentence.replace(target, f"<span style='{HIGHLIGHT}'>{target}</span>", 1)


def py(text):
    """Pinyin with the answer while the word is still being learned; behind
    a tap once it's mature."""
    if not text:
        return
    if word["id"] in S.get("wd_mature", ()):
        st.markdown(f"<details><summary style='color:#90a4ae;font-size:0.85rem'>pinyin</summary>"
                    f"<span style='color:#78909c;font-size:0.9rem'>{text}</span></details>",
                    unsafe_allow_html=True)
    else:
        st.caption(text)


def grammar_tag(sentence):
    s_ = gc.get((sentence or {}).get("structure") or "")
    if s_:
        st.caption(f"🧩 Grammar: {s_.name}")


def network(word, payload):
    """Everything this word is connected to so far."""
    with st.expander("Word network"):
        chunks = [c["hanzi"] for c in payload.get("chunks") or []]
        if chunks:
            st.caption("Chunks: " + " · ".join(chunks))
        met = sorted({gc.get(x["structure"]).name for x in payload.get("sentences") or []
                      if x.get("structure") and gc.get(x["structure"])})
        if met:
            st.caption("Grammar met with: " + " · ".join(met))
        conf = [c["hanzi"] for c in payload.get("confusables") or []]
        if conf:
            st.caption("Don't confuse with: " + " · ".join(conf))
        tr = db.word_tracks(USER_ID, [word["id"]])
        rec, prod = tr.get((word["id"], ve.RECOGNITION)), tr.get((word["id"], ve.PRODUCTION))
        st.caption(f"Recognition: next {rec['next_review_date'] if rec else '—'} · Production: "
                   + (f"next {prod['next_review_date']}" if prod else
                      "starts once you recognise it reliably" if ve.can_produce(word)
                      else "recognition only"))


def setup(item, payload):
    """Choices for this item (sentence, options, prompt), fixed on first
    render so reruns don't reshuffle them."""
    if S.get("wd_setup_i") == S.wd_i:
        return S.wd_setup
    word, mode = item["word"], item["mode"]
    sents = payload.get("sentences") or []
    k = S.wd_rot.get(word["id"], -1) + 1
    S.wd_rot[word["id"]] = k
    sentence = sents[k % len(sents)] if sents else None
    if mode == "cloze" and not sentence:
        mode = "meaning_to_zh"
    prompts = payload.get("prompts") or []
    if mode == "spoken" and not prompts:
        mode = "meaning_to_zh"
    su = {"mode": mode, "sentence": sentence,
          "chunk": (payload.get("chunks") or [None])[0],
          "prompt": random.choice(prompts) if prompts else None,
          "options": None}
    if mode in ve.REC_MODES:
        confusables = list(payload.get("confusables") or [])
        if item.get("confused_with"):
            confusables.insert(0, {"hanzi": item["confused_with"]})
        su["options"] = wc.meaning_options(word, S.wd_pool, confusables,
                                           audio=(mode == "audio_to_meaning"))
    S.wd_setup, S.wd_setup_i = su, S.wd_i
    return su


def finish(item, mode, result, detail, cid):
    word, skill, vid = item["word"], item["skill"], item["word"]["id"]
    detail = {**detail, "kind": item["kind"]}
    db.log_word_attempt(USER_ID, vid, skill, mode, result, detail)
    if cid:
        db.word_content_used(cid)
    tracks = db.word_tracks(USER_ID, [vid])
    if item["kind"] == "new" and (vid, ve.RECOGNITION) not in tracks:
        # introduced today: a track at the start line; the first check is a
        # learning step and doesn't move it
        db.save_word_track(USER_ID, vid, ve.RECOGNITION,
                           {"interval": 0, "next_review_date": date.today().isoformat()}, mode)
    counts = item["kind"] in ("review", "unlock", "step2")
    if counts and result != "ungraded":
        old = tracks.get((vid, skill)) or {}
        new = ve.update_track(old, result)
        new["introduced_on"] = old.get("introduced_on")
        db.save_word_track(USER_ID, vid, skill, new, mode)
        open_d = db.open_diagnoses(USER_ID, [vid]).get(vid)
        if open_d and result == "correct" and open_d["skill"] == skill and new["streak"] >= 2:
            db.resolve_diagnosis(open_d["id"])          # it holds again
        elif result in ("wrong", "close") and not open_d and S.wd_remedies < MAX_REMEDIES:
            attempts = db.word_attempts_all(USER_ID, vid)
            if wd.is_troubled(new, [a for a in attempts if a["skill"] == skill]):
                diag = wd.diagnose(attempts)
                S.wd_diag = {**diag, "id": db.save_diagnosis(USER_ID, vid, skill, diag),
                             "skill": skill}
                S.wd_remedies += 1
        elif open_d and result != "correct":
            remedy = open_d.get("remedy") or {}
            S.wd_hook = open_d.get("note") or remedy.get("mnemonic")
    if result != "ungraded":
        # every answered card counts towards the day, by the skill it used
        if skill == ve.RECOGNITION:
            kind = "read" if mode == "zh_to_meaning" else "listen"
        else:
            kind = "speak" if detail.get("spoken") else "type"
        try:
            db.log_activity(USER_ID, kind, word["chinese"], ve.GRADES[result])
        except Exception:
            pass
    if result == "wrong" and (vid, skill) not in S.wd_retried:
        # one more go later this session, in a gentler mode; practice only
        S.wd_retried.add((vid, skill))
        retry_mode = ("zh_to_meaning" if mode == "audio_to_meaning" else "audio_to_meaning") \
            if skill == ve.RECOGNITION else "cloze"
        S.wd_items.insert(ve.requeue_position(S.wd_items, S.wd_i),
                          dict(item, kind="retry", mode=retry_mode))
    S.wd_results.append({"chinese": word["chinese"], "english": word["english"],
                         "skill": skill, "mode": mode, "kind": item["kind"],
                         "result": result})
    S.wd_ans = {"result": result, **detail}


def next_item():
    S.wd_i += 1
    for k in ("wd_ans", "wd_setup", "wd_setup_i", "wd_intro_done", "wd_diag", "wd_rem", "wd_hook"):
        S.pop(k, None)


def next_button():
    """After an answer: a memory hook if the word has one, the diagnosis if
    this miss revealed a troubled word, otherwise straight on."""
    if S.get("wd_hook"):
        st.info(f"💡 {S.wd_hook}")
    diag = S.get("wd_diag")
    if diag:
        st.warning(f"**{item['word']['chinese']} keeps slipping — {wd.CAUSE_TITLES[diag['cause']].lower()}.**\n\n"
                   + "\n".join(f"- {e}" for e in diag["evidence"]))
        c1, c2 = st.columns(2)
        if c1.button("Work on it now", type="primary", width="stretch"):
            S.wd_rem = start_remedy(item, diag)
            st.rerun()
        if c2.button("Later", width="stretch"):
            next_item()
            st.rerun()
        return
    if st.button("Next ▶️", type="primary", width="stretch"):
        next_item()
        st.rerun()


# ----------------------------------------------------------------------
# remedies
# ----------------------------------------------------------------------
def start_remedy(item, diag):
    word, cause = item["word"], diag["cause"]
    payload, _cid = S.wd_content.get(word["id"], (wc.fallback_content(word), None))
    R = {"cause": cause, "diag_id": diag["id"], "skill": diag.get("skill", "recognition"),
         "i": 0, "answered": None, "rounds": [],
         "typed": False, "card": [], "difference": "", "mnemonic": ""}
    if cause in ("tone", "sound"):
        R["rounds"] = (wd.tone_rounds if cause == "tone" else wd.sound_rounds)(word, S.wd_pool) \
            or wd.tone_rounds(word, S.wd_pool)
    elif cause == "character":
        card = wd.character_card(word, S.wd_pool)
        R["card"], R["rounds"] = card["components"] + card["compare"], card["rounds"]
    elif cause == "confusion":
        other_zh = diag.get("confused_with") or next(
            (c["hanzi"] for c in payload.get("confusables") or []), None)
        other = db.word_by_chinese(other_zh) if other_zh else None
        if other:
            with st.spinner(f"Building a {word['chinese']} / {other['chinese']} contrast…"):
                contrast = wd.write_contrast(word, other, S.wd_known)
            if contrast:
                R["difference"] = contrast["difference"]
                for it in contrast["items"]:
                    opts = [word["chinese"], other["chinese"]]
                    random.shuffle(opts)
                    R["rounds"].append({"show": it["gap"], "english": it["english"],
                                        "question": "Which word fits?", "options": opts,
                                        "answer": it["answer"], "full": it["hanzi"]})
            else:
                R["difference"] = next((c.get("difference", "") for c in payload.get("confusables") or []
                                        if c["hanzi"] == other["chinese"]), "")
                for w in (word, other):
                    opts = [word["chinese"], other["chinese"]]
                    random.shuffle(opts)
                    R["rounds"].append({"show": wc.short_meaning(w["english"]),
                                        "question": f"Which one means “{wc.short_meaning(w['english'])}”?",
                                        "options": opts, "answer": w["chinese"]})
            R["card"] = [f"{w['chinese']} {w['pinyin']} — {wc.short_meaning(w['english'])}"
                         for w in (word, other)]
    elif cause in ("production_gap", "usage"):
        R["typed"] = True
        R["rounds"] = (wd.production_ladder(word, payload) if cause == "production_gap"
                       else wd.usage_rounds(word, payload))
    if cause == "memory" or not R["rounds"]:
        with st.spinner("Finding a way to make it stick…"):
            R["mnemonic"] = wd.write_mnemonic(word) or ""
        R["card"] = R["card"] or wd.character_card(word, S.wd_pool)["components"]
    db.update_diagnosis(R["diag_id"], remedy={k: R[k] for k in ("cause", "difference", "mnemonic")})
    return R


def render_remedy():
    R, word = S.wd_rem, item["word"]
    st.subheader(f"{word['chinese']} — {wd.CAUSE_TITLES[R['cause']]}")
    for line in R["card"]:
        st.caption(line)
    if R["difference"]:
        st.info(R["difference"])
    if R["i"] >= len(R["rounds"]):
        if R["mnemonic"]:
            st.info(f"💡 {R['mnemonic']}")
        if R["mnemonic"] or R["cause"] == "memory":
            note = st.text_area("Your own hook (optional) — it'll be shown when you miss this word",
                                key=f"wd_note_{S.wd_i}")
            if st.button("Save and continue ▶️", type="primary", width="stretch"):
                if note.strip():
                    db.update_diagnosis(R["diag_id"], note=note.strip())
                next_item()
                st.rerun()
            return
        st.success("Done — it'll come back soon to check it has stuck.")
        if st.button("Back to the session ▶️", type="primary", width="stretch"):
            next_item()
            st.rerun()
        return
    rnd = R["rounds"][R["i"]]
    st.progress(R["i"] / len(R["rounds"]), text=f"Practice {R['i'] + 1} of {len(R['rounds'])}")
    key = f"wd_rem_{S.wd_i}_{R['i']}"
    if rnd.get("play"):
        play(rnd["play"])
    if rnd.get("show"):
        big(rnd["show"], "1.6rem")
    if rnd.get("english"):
        st.caption(rnd["english"])
    if R["typed"]:
        if rnd.get("hint"):
            st.caption(f"Hint: {rnd['hint']}")
        if R["answered"] is None:
            typed = st.text_input("Type pinyin or characters", key=key)
            mic = st.audio_input("🎙️ …or say it", key=key + "_mic")
            if st.button("Check", type="primary", disabled=not (typed.strip() or mic)):
                said = typed.strip()
                if mic is not None:
                    t = transcribe_audio(mic.getvalue())
                    if t is None:
                        st.error("The speech service didn't respond — try again or type it.")
                        return
                    said = _force_simplified(t.get("text", ""))
                if R["cause"] == "usage":
                    result, _d = wd.check_chunk(said, rnd["answer"], rnd["answer_pinyin"], word["chinese"])
                else:
                    result, _d = wc.check_answer(said, rnd["answer"], rnd["answer_pinyin"])
                db.log_word_attempt(USER_ID, word["id"], R.get("skill", "production"),
                                    f"remedy_{R['cause']}", result, {"said": said, "kind": "remedy"})
                R["answered"] = {"result": result, "said": said}
                st.rerun()
            return
    else:
        if R["answered"] is None:
            choice = st.radio(rnd["question"], rnd["options"], index=None, key=key)
            if st.button("Check", type="primary", disabled=choice is None):
                result = "correct" if choice == rnd["answer"] else "wrong"
                db.log_word_attempt(USER_ID, word["id"], "recognition", f"remedy_{R['cause']}",
                                    result, {"chose": choice, "kind": "remedy"})
                R["answered"] = {"result": result, "said": choice}
                st.rerun()
            return
    a = R["answered"]
    st.markdown("✅ Right." if a["result"] == "correct" else
                f"{'🟡' if a['result'] == 'close' else '❌'} It's **{rnd['answer']}**")
    if rnd.get("full"):
        big(rnd["full"], "1.4rem")
        play(rnd["full"])
    elif R["typed"]:
        play(rnd["answer"])
    if st.button("Next ▶️", type="primary", width="stretch", key=key + "_next"):
        R["i"] += 1
        R["answered"] = None
        st.rerun()


# ----------------------------------------------------------------------
# summary
# ----------------------------------------------------------------------
if S.wd_i >= len(S.wd_items):
    res = S.wd_results
    first = [r for r in res if r["kind"] != "retry"]
    right = sum(r["result"] == "correct" for r in first)
    # a session started from the Library still counts if the plan is waiting on Words
    if tp.active("words"):
        S.wd_plan = True            # kept, so the Continue button survives the next rerun
    in_plan = S.get("wd_plan")
    tp.session_done(USER_ID, "words", S.get("wd_t0"), items=len(res),
                    step="words" if in_plan else None, once_key="wd_logged")
    if not S.wd_items:
        st.success("Nothing due and no new words available right now.")
    else:
        st.success(f"Session done — {right} of {len(first)} right first time.")
    new = {r["chinese"]: r["english"] for r in res if r["kind"] in ("new", "step2")}
    if new:
        st.markdown("**New words:** " + " · ".join(f"{zh} — {wc.short_meaning(en)}"
                                                    for zh, en in new.items()))
    missed = sorted({r["chinese"] for r in first if r["result"] == "wrong"})
    if missed:
        st.markdown("**Missed:** " + " · ".join(missed))
    unlocked = sorted({r["chinese"] for r in res if r["kind"] == "unlock"})
    if unlocked:
        st.markdown("**Now producing:** " + " · ".join(unlocked))
    by_mode = {}
    for r in first:
        if r["result"] != "ungraded":
            ok, n = by_mode.get(r["mode"], (0, 0))
            by_mode[r["mode"]] = (ok + (r["result"] == "correct"), n + 1)
    if by_mode:
        st.caption(" · ".join(f"{ve.MODE_TITLES[m]}: {ok}/{n}" for m, (ok, n) in by_mode.items()))
    if in_plan:
        tp.continue_ui(reset)
    elif st.button("▶️ Another session", type="primary", width="stretch"):
        reset()
        st.rerun()
    st.stop()


# ----------------------------------------------------------------------
# the current item
# ----------------------------------------------------------------------
item = S.wd_items[S.wd_i]
word = item["word"]
prefetch(S.wd_i + 1)
payload, cid = content_for(item)
su = setup(item, payload)
mode = su["mode"]
ans = S.get("wd_ans")
target = word["chinese"]
label = {"new": "New word", "step2": "Second look", "unlock": "Now try using it",
         "retry": "Once more", "review": "Review"}[item["kind"]]
st.progress(S.wd_i / len(S.wd_items), text=f"{label} · {ve.MODE_TITLES[mode]}")

if S.get("wd_rem"):
    render_remedy()
    st.stop()

# introduction of a new word: met in its chunks and sentences first
if item["kind"] == "new" and not S.get("wd_intro_done") and ans is None:
    big(f"<span style='{HIGHLIGHT}'>{target}</span>", "2.6rem")
    st.caption(f"{word['pinyin']} — {payload.get('meaning') or wc.short_meaning(word['english'])}")
    play(target)
    for c in payload.get("chunks") or []:
        big(marked(c["hanzi"], target), "1.4rem")
        st.caption(f"{c.get('pinyin', '')} — {c.get('english', '')}")
    for s_ in (payload.get("sentences") or [])[:2]:
        big(marked(s_["hanzi"], target), "1.4rem")
        play(s_["hanzi"])
        st.caption(f"{s_.get('pinyin', '')} — {s_.get('english', '')}")
        grammar_tag(s_)
    for c in payload.get("confusables") or []:
        st.caption(f"Not to be confused with {c['hanzi']}: {c.get('difference', '')}")
    if word.get("tag") == "China":
        st.caption("Mainland usage — learn to recognise it; say the Malaysian word yourself.")
    if st.button("Got it — test me", type="primary", width="stretch"):
        S.wd_intro_done = True
        st.rerun()
    st.stop()


def recognition():
    sentence = su["sentence"]
    if mode == "zh_to_meaning":
        big(marked(sentence["hanzi"], target) if sentence else
            f"<span style='{HIGHLIGHT}'>{target}</span>")
        question = f"What does {target} mean here?"
    else:
        st.caption("The word:")
        play(target)
        if sentence:
            st.caption("…in a sentence:")
            play(sentence["hanzi"])
        question = "What does the word mean?"
    texts = [o["text"] for o in su["options"]]
    choice = st.radio(question, texts, index=None, key=f"wd_mc_{S.wd_i}")
    if ans is None:
        if st.button("Check", type="primary", disabled=choice is None):
            picked = su["options"][texts.index(choice)]
            result = "correct" if picked["kind"] == "correct" else "wrong"
            finish(item, mode, result, {"chose": picked["chinese"], "chose_kind": picked["kind"],
                                        "sentence": sentence["hanzi"] if sentence else None}, cid)
            st.rerun()
        return
    right = next(o["text"] for o in su["options"] if o["kind"] == "correct")
    st.markdown("✅ Right." if ans["result"] == "correct" else f"❌ It means **{right}**")
    if ans["result"] != "correct" and ans.get("chose"):
        st.caption(f"You picked the meaning of {ans['chose']}.")
    if sentence:
        big(marked(sentence["hanzi"], target), "1.4rem")
        py(sentence.get("pinyin"))
        st.caption(sentence.get("english", ""))
        grammar_tag(sentence)
    else:
        py(word["pinyin"])
    network(word, payload)
    next_button()


def production():
    sentence, prompt = su["sentence"], su["prompt"]
    if mode == "cloze":
        big(wc.cloze(sentence["hanzi"], target))
        st.caption(sentence.get("english", ""))
        task = "Fill the gap — type pinyin or characters, or say it."
    elif mode == "meaning_to_zh":
        chunk = su["chunk"]
        big(payload.get("meaning") or wc.short_meaning(word["english"]), "1.6rem")
        if chunk:
            st.caption(f"as in: {chunk.get('english', '')}")
        task = "Say or type the Chinese."
    else:
        big(prompt["situation"], "1.3rem")
        task = f"Answer aloud using {target}."
        st.caption(task)
    if ans is None:
        mic = st.audio_input("🎙️ Say it", key=f"wd_mic_{S.wd_i}")
        typed = st.text_input("…or type it", key=f"wd_type_{S.wd_i}")
        c1, c2 = st.columns(2)
        if c1.button("Check", type="primary", disabled=not (mic or typed.strip())):
            said, spoken = typed.strip(), False
            if mic is not None:
                with st.spinner("Listening…"):
                    t = transcribe_audio(mic.getvalue())
                if t is None:
                    st.error("The speech service didn't respond — record again, or type it.")
                    return
                said, spoken = _force_simplified(t.get("text", "")), True
            if mode == "spoken":
                with st.spinner("Checking…"):
                    g = wc.grade_spoken(word, prompt["situation"], prompt["sample_hanzi"], said, spoken)
                finish(item, mode, g["verdict"], {"said": said, "spoken": spoken, "error": g["error"],
                                                  "feedback": g["feedback"], "better": g["better"]}, cid)
            else:
                result, detail = wc.check_answer(said, target, word["pinyin"])
                if spoken and detail.get("homophone"):
                    result = "correct"      # speech can't show which character you meant
                finish(item, mode, result, {**detail, "said": said, "spoken": spoken}, cid)
            st.rerun()
        if c2.button("Show me"):
            finish(item, mode, "wrong", {"gave_up": True}, cid)
            st.rerun()
        return
    icon = {"correct": "✅", "close": "🟡", "wrong": "❌", "ungraded": "⚪"}[ans["result"]]
    if ans.get("said"):
        st.markdown(f"{icon} You said: {ans['said']}")
    else:
        st.markdown(icon)
    if ans.get("tone_error"):
        st.caption("Right syllables, but check the tones.")
    if ans.get("homophone"):
        st.caption("Same sound — but a different character.")
    if ans.get("feedback"):
        st.caption(ans["feedback"])
    model = prompt["sample_hanzi"] if mode == "spoken" else \
        (sentence["hanzi"] if sentence else target)
    if ans.get("better") and ans["better"] != model:
        st.markdown(f"Better: {ans['better']}")
    big(marked(model, target), "1.6rem")
    play(model)
    py(prompt.get("sample_pinyin") if mode == "spoken" else
       (sentence.get("pinyin") if sentence else word["pinyin"]))
    if mode != "spoken":
        grammar_tag(sentence)
    network(word, payload)
    next_button()


if mode in ve.REC_MODES:
    recognition()
else:
    production()
