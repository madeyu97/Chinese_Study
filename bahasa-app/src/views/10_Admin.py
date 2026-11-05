# src/views/10_Admin.py
"""
🛠️ Settings: the shared word list, its review queue, and the sentence bank.

Kept out of the study flow on purpose. All of it is SHARED: a word edited
or a sentence retired here changes things for everyone on this database.

Review queue: glosses marked 'unsure' when the list was built, plus any
audit sample you draw. Mark each one right, or fix it. A word you edit is
never overwritten by the word-list file again.
"""

import streamlit as st

import db_manager as db
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Word list & sentence bank", page_icon="🛠️", layout="centered")
USER = require_login()

with st.sidebar:
    sidebar_user_badge()

st.title("🛠️ Word list & sentence bank")
st.caption("Changes here are shared: they affect everyone studying on this database.")

tab_review, tab_words, tab_bank = st.tabs(["✅ Review queue", "📝 Word list", "🏦 Sentence bank"])

REGISTERS = ["", "colloquial", "standard", "formal"]
TAGS = ["", "Indonesian", "Utara"]


def edit_form(word, key):
    """Fields for one word; returns True if saved."""
    with st.form(f"{key}_{word['id']}"):
        c1, c2 = st.columns(2)
        ms = c1.text_input("Malay", word["malay"])
        en = c2.text_input("Meaning", word["english"] or "")
        c3, c4, c5 = st.columns(3)
        root = c3.text_input("Root", word.get("root") or "")
        aff = c4.text_input("Affixes", word.get("affixes") or "",
                            help="e.g. meN-, di-, -kan, ke-…-an, +nya. Blank for a bare root.")
        pos = c5.text_input("Part of speech", word.get("pos") or "")
        c6, c7, c8 = st.columns(3)
        reg = c6.selectbox("Register", REGISTERS,
                           index=REGISTERS.index(word.get("register") or ""))
        tag = c7.selectbox("Tag", TAGS, index=TAGS.index(word.get("tag") or ""),
                           help="Indonesian and Utara words are learned for recognition only.")
        eq = c8.text_input("Malaysian form", word.get("my_equivalent") or "",
                           help="For Indonesian forms: the word Malaysians use.")
        if st.form_submit_button("💾 Save", type="primary"):
            db.update_word_in_db(word["id"], malay=ms.lower(), english=en, root=root.lower(),
                                 affixes=aff, pos=pos, register=reg, tag=tag, my_equivalent=eq)
            return True
    return False


def describe(w):
    bits = [f"**{w['malay']}** — {w['english']}"]
    if w.get("root") or w.get("affixes"):
        bits.append(f"`{w.get('root') or w['malay']}` {w.get('affixes') or ''}".strip())
    for k in ("pos", "register", "tag"):
        if w.get(k):
            bits.append(w[k])
    if w.get("my_equivalent"):
        bits.append(f"Malaysian: {w['my_equivalent']}")
    if w.get("freq_rank"):
        bits.append(f"#{w['freq_rank']}")
    return " · ".join(bits)


# ======================================================================
# REVIEW QUEUE
# ======================================================================
with tab_review:
    stats = db.vocab_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Words", stats["total"])
    c2.metric("Lesson words", stats["lessons"])
    c3.metric("Indonesian forms", stats["indonesian"])
    rows, counts = db.review_queue(limit=25)
    audit = db.audit_stats()
    st.caption(f"Waiting: **{counts.get('audit', 0)}** audit · **{counts.get('unsure', 0)}** "
               f"marked unsure")
    if audit["done"]:
        st.caption(f"Audit so far: {audit['done']} checked, {audit['fixed']} needed fixing — "
                   f"**{audit['accuracy']}% right** (the Phase 1 gate is 97% on 200).")
    if not counts.get("audit") and st.button("🎲 Draw 200 random words to audit"):
        n = db.draw_audit(200)
        st.success(f"{n} words added to the queue.")
        st.rerun()
    if not rows:
        st.info("Nothing waiting for a check.")
    for w in rows:
        st.markdown(("🎲 " if w["needs_check"] == "audit" else "❓ ") + describe(w))
        c1, c2 = st.columns([1, 3])
        if c1.button("✅ Right", key=f"ok_{w['id']}"):
            db.mark_word_checked(w["id"])
            st.rerun()
        with c2.expander("Fix it"):
            if edit_form(w, "rq"):
                st.rerun()
        st.divider()


# ======================================================================
# WORD LIST
# ======================================================================
with tab_words:
    st.caption("Fix a word's meaning, root, affixes, register or tag — the meaning also "
               "guides the sentences written for it — or remove a word that shouldn't be there.")
    query = st.text_input("Find a word", placeholder="Malay, root or English", key="adm_query")
    found = db.find_words(query) if query.strip() else []
    if query.strip() and not found:
        st.info("No word matches.")
    if found:
        pick = st.selectbox("Word", found, key="adm_pick",
                            format_func=lambda w: f"{w['malay']}  — {(w['english'] or '')[:50]}")
        st.markdown(describe(pick))
        if edit_form(pick, "adm_edit"):
            st.success("Saved.")
        with st.expander("Delete this word"):
            st.warning(f"Deleting **{pick['malay']}** removes it — and its progress — for "
                       "everyone studying on this database.")
            sure = st.checkbox("I understand", key=f"adm_sure_{pick['id']}")
            if st.button("🗑️ Delete permanently", disabled=not sure, key=f"adm_del_{pick['id']}"):
                db.delete_word_from_db(pick["id"])
                st.success(f"Deleted {pick['malay']}.")
                st.rerun()


# ======================================================================
# SENTENCE BANK
# ======================================================================
with tab_bank:
    bstats = db.bank_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Vetted sentences", bstats["active_sentences"])
    c2.metric("Words covered", f"{bstats['vocab_covered']}/{bstats['vocab_total']}")
    c3.metric("Flagged", bstats["flagged"])
    if bstats["vocab_total"]:
        st.progress(min(1.0, bstats["vocab_covered"] / bstats["vocab_total"]))
    st.caption("The bank fills from human-written Malay first, then grows with every "
               "sentence that passes the checks (Listen & speak arrives in Phase 3).")

    st.subheader("🔍 Browse sentences")
    col_a, col_b = st.columns([2, 1])
    word_filter = col_a.text_input("Filter by word", "",
                                   placeholder="e.g. makan — leave empty for the newest")
    show_status = col_b.selectbox("Status", ["active", "flagged"])
    brows = db.bank_browse(word_filter.strip().lower() or None, status=show_status)
    if not brows:
        st.info("No sentences match.")
    for row in brows:
        ex = row["exercise"]
        with st.expander(f"{row['sentence']}  ·  [{row['vocab_word']}]  ·  used {row['times_used']}×"):
            st.write(f"**English:** {ex.get('english_correct', '')}")
            distractors = ex.get("english_distractors", [])
            if distractors:
                st.caption("Distractors: " + " | ".join(distractors))
            st.caption(f"Source: {ex.get('source', 'generated')}")
            if row["status"] == "active":
                if st.button("🚩 Retire this sentence", key=f"retire_{row['sentence']}"):
                    db.flag_sentence(row["sentence"], "retired from bank page")
                    st.rerun()
            elif st.button("♻️ Restore (flagged by mistake)", key=f"restore_{row['sentence']}"):
                db.unflag_sentence(row["sentence"])
                st.rerun()

    st.subheader("🚩 Recent flags")
    st.caption("Flagged sentences are fed to the writer and reviewer as examples of what "
               "not to do, so every flag strengthens the checks.")
    flags = db.get_recent_flags(limit=15)
    if not flags:
        st.info("Nothing flagged yet.")
    for sentence, reason in flags:
        cols = st.columns([4, 1])
        cols[0].write(f"**{sentence}**" + (f" — {reason}" if reason else ""))
        if cols[1].button("♻️ Restore", key=f"unflag_{sentence}"):
            db.unflag_sentence(sentence)
            st.rerun()
