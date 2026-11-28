# src/reading_hsk_page.py
"""
📖 Read on the HSK track - graded passages at your reading level.

views/6_Reading.py hands over to run() for people on the HSK track (the
original sentence reader stays as it was for everyone else).

A passage: its title, the audio of the whole thing, the text word by word -
tap a word for its pinyin and meaning; words above your level are gold with
their pinyin showing - then one question to check you understood it, and
the translation. Passages are written ahead (ahead.reading, nightly
tools/fill_bank.py), so the next one is already there; the page only
writes one while you wait if the stock has run out.

As a step of the evening session it reads the plan's number of passages
(one), then moves on.
"""

import csv
import html
import io
import time

import streamlit as st

import ahead
import clock
import db_manager as db
import today_plan as tp
from audio_engine import create_audio_file

MANDARIN_BEAN = {   # Mandarin Bean groups its lessons by stage, not HSK level
    1: ("Beginner", "https://mandarinbean.com/all-lessons/?jsf=epro-loop-builder&tax=category:3"),
    2: ("Beginner", "https://mandarinbean.com/all-lessons/?jsf=epro-loop-builder&tax=category:3"),
    3: ("Intermediate", "https://mandarinbean.com/all-lessons/?jsf=epro-loop-builder&tax=category:4"),
    4: ("Intermediate", "https://mandarinbean.com/all-lessons/?jsf=epro-loop-builder&tax=category:4"),
}

CSS = """
<style>
.rp { font-family: "Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
      font-size: 27px; line-height: 1.35; display:flex; flex-wrap:wrap; gap: 0 5px; }
/* the pinyin and English sit in a band under the word without widening it:
   hidden glosses as wide as "very" spread 很 and 好 far apart */
.rp label { cursor:pointer; position:relative; padding-bottom: 30px; }
.rp input { display:none; }
.rp .w { display:block; }
.rp .py, .rp .en { font-size: 12px; line-height: 1.2; visibility: hidden; white-space: nowrap;
                   position:absolute; left:50%; transform:translateX(-50%); z-index:1; }
.rp .py { top: calc(100% - 30px); }
.rp .en { top: calc(100% - 15px); }
.rp .py { color:#7EB6FF; }
.rp .en { color:#90a4ae; max-width: 13em; overflow:hidden; text-overflow:ellipsis; }
.rp input:checked ~ .py, .rp input:checked ~ .en { visibility: visible; }
.rp .new .w { color:#F5C84C; }
.rp .new .py { visibility: visible; }
.rp.all .py { visibility: visible; position: static; transform: none; display:block;
              text-align:center; }
.rp.all label { padding-bottom: 15px; }
.rp .g { display:inline-flex; white-space:nowrap; }
.rp .p { align-self:flex-start; }
</style>
"""


OPENING = set("“‘（《「『【")


def passage_html(words, all_pinyin=False):
    """The passage as tap-to-reveal word tiles. Punctuation stays with its
    word - a closing mark with the word before, an opening one with the word
    after - so a line never starts with 。 or ：“."""
    groups, opening = [], ""
    for n, w in enumerate(words):
        if w.get("punct"):
            for c in w["w"]:            # ：“ is a closing mark and an opening one
                mark = f'<span class="p">{html.escape(c)}</span>'
                if c in OPENING or not groups or opening:
                    opening += mark
                else:
                    groups[-1] += mark
            continue
        cls = "new" if w.get("new") else ""
        groups.append(opening + f'<label class="{cls}"><input type="checkbox" id="w{n}">'
                      f'<span class="w">{html.escape(w["w"])}</span>'
                      f'<span class="py">{html.escape(w.get("py", ""))}</span>'
                      f'<span class="en">{html.escape(w.get("en", ""))}</span></label>')
        opening = ""
    if opening:
        groups.append(opening)
    cells = "".join(f'<span class="g">{g}</span>' for g in groups)
    return CSS + f'<div class="rp{" all" if all_pinyin else ""}">{cells}</div>'


def anki_csv(words):
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["Chinese", "Pinyin", "English"])
    for w in words:
        out.writerow([w.get("hanzi", ""), w.get("pinyin", ""), w.get("english", "")])
    return buf.getvalue().encode("utf-8")


def run(user):
    uid = user["id"]
    S = st.session_state
    levels = db.get_hsk_levels(uid) or {}
    level = levels.get("read") or 1

    def reset_plan():
        for k in ("rh_plan", "rh_cur", "rh_answer", "rh_logged"):
            S.pop(k, None)

    if S.get("rh_plan") and S.rh_plan.get("date") != clock.today().isoformat():
        reset_plan()
    if "rh_plan" not in S and tp.active("reading"):
        S.rh_plan = {"n": tp.params("reading").get("passages", 1), "read": 0,
                     "t0": time.time(), "date": clock.today().isoformat()}
    plan = S.get("rh_plan")

    stats = db.reading_passage_stats(uid, level)
    with st.sidebar:
        tp.sidebar("reading", reset_plan)
        st.metric("Passages read", stats["read"])
        if stats["read"]:
            st.caption(f"Questions right: {stats['right']} of {stats['read']}")
        stage, url = MANDARIN_BEAN[level]
        st.markdown(f"**More reading:** [Mandarin Bean — {stage}]({url}) (HSK {level}), with "
                    "audio and questions.")
        new_words = db.reading_passage_new_words(uid)
        if new_words:
            st.download_button(f"⬇️ {len(new_words)} new words for Anki (CSV)",
                               anki_csv(new_words), "reading_new_words.csv", "text/csv",
                               width="stretch")

    st.title(f"📖 Read — HSK {level}")
    # keep passages in stock while this one is read
    ahead.reading(uid, level)

    if plan and plan["read"] >= plan["n"]:
        st.success("Reading done for today.")
        tp.session_done(uid, "reading", plan["t0"], items=plan["read"], step="reading",
                        once_key="rh_logged")
        tp.continue_ui(reset_plan)
        st.stop()
    if plan:
        st.progress(plan["read"] / plan["n"],
                    text=f"Passage {plan['read'] + 1} of {plan['n']}")

    def next_checked():
        """The next passage whose question has passed the blind check (older
        stock is checked here, once; one that fails is taken out)."""
        import reading_hsk as rh
        for _ in range(6):
            nxt = db.reading_passage_next(uid, level)
            if nxt is None or nxt["payload"].get("checked"):
                return nxt
            with st.spinner("Checking the question…"):
                problems, ran = rh.blind_check(nxt["payload"])
            if not ran:                 # no model to ask: it was reviewed when written
                return nxt
            if problems:
                db.reading_passage_flag(nxt["id"], "blind check: " + problems[0])
                continue
            nxt["payload"] = db.reading_passage_mark_checked(nxt["id"], nxt["payload"])
            return nxt
        return None

    cur = S.get("rh_cur")
    if cur is None or cur.get("level") != level:
        cur = next_checked()
        if cur is None:
            with st.spinner("Writing a passage at your level…"):
                ahead.wait_reading(uid, level)
                cur = next_checked()
                if cur is None and ahead.write_passage(uid, level):
                    cur = next_checked()
        if cur is None:
            st.warning("Couldn't write a passage just now. Try again in a minute.")
            if plan:
                tp.continue_ui(reset_plan)
            st.stop()
        S.pop("rh_answer", None)
        S.rh_cur = cur
    p = cur["payload"]

    q = p["question"]
    ans = S.get("rh_answer")
    # listening first (HSK 4's listening paper is a third of the exam): the
    # question is answered by ear, then the text is there to read
    c1, c2 = st.columns(2)
    listen = c1.toggle("🎧 Listen first", value=True, key="rh_listen")
    all_py = c2.toggle("Show all pinyin", key="rh_all_py")
    audio = create_audio_file(p["text"])
    # with no audio (TTS down) there's nothing to listen to: the text shows
    hidden = bool(audio) and listen and ans is None and S.get("rh_shown") != cur["id"]
    st.subheader(p.get("title", ""))
    if audio:
        st.audio(audio, format="audio/mp3")
    if hidden:
        st.caption("Listen — twice if you need — and answer the question. Then read it.")
        if st.button("📄 Show the text", key=f"rh_show_{cur['id']}"):
            S.rh_shown = cur["id"]
            st.rerun()
    else:
        st.html(passage_html(p.get("words") or [], all_py))
        st.caption("Tap a word for its pinyin and meaning. 🟡 Gold words are above HSK "
                   f"{level} — their pinyin shows.")
        with st.expander("Words"):
            seen = set()
            for w in p.get("words") or []:
                if w.get("punct") or w["w"] in seen:
                    continue
                seen.add(w["w"])
                tag = "🟡 " if w.get("new") else ""
                lv = f" · HSK {w['hsk']}" if w.get("hsk") else ""
                st.markdown(f"{tag}**{w['w']}** {w.get('py', '')} — {w.get('en', '')}{lv}")

    en_opts = q.get("options_english") or []
    with st.container(border=True):
        st.markdown(f"**{q['question']}**")
        if q.get("question_english"):           # the question is in Chinese, like the exam's
            with st.expander("Pinyin and English"):
                from pinyin_hsk import sentence_pinyin
                st.caption(sentence_pinyin(q["question"]))
                st.markdown(q["question_english"])
                for opt, en in zip(q["options"], en_opts):
                    st.caption(f"{opt} {sentence_pinyin(opt)} — {en}")
        if ans is None:
            for n, opt in enumerate(q["options"]):
                if st.button(opt, key=f"rh_opt_{cur['id']}_{n}", width="stretch"):
                    S.rh_answer = n
                    db.reading_passage_done(cur["id"], n == q["answer"])
                    db.log_activity(uid, "read", p.get("title", ""))
                    if plan:
                        plan["read"] += 1
                    st.rerun()
        else:
            def opt(n):
                return f"**{q['options'][n]}**" + (f" — {en_opts[n]}" if len(en_opts) == 3 else "")
            if ans == q["answer"]:
                st.markdown("✅ Right: " + opt(ans))
            else:
                st.markdown("❌ You chose " + opt(ans))
                st.markdown("✅ The answer: " + opt(q["answer"]))
            if S.get("rh_flagged") == cur["id"]:
                st.caption("🚩 Reported: this passage is out of your score and won't be shown again.")
            elif st.button("🚩 The question is wrong", key=f"rh_flag_{cur['id']}"):
                db.reading_passage_flag(cur["id"], f"reported (chose {q['options'][ans]})")
                S.rh_flagged = cur["id"]
                st.rerun()
    if ans is not None:
        with st.expander("Translation", expanded=ans != q["answer"]):
            st.write(p.get("english", ""))
        if st.button("📖 Next passage", type="primary", width="stretch"):
            S.pop("rh_cur", None)
            S.pop("rh_answer", None)
            st.rerun()
