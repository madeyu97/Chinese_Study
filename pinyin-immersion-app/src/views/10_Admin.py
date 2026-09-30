# src/views/10_Admin.py
"""
🛠️ Settings: the sentence bank and the shared word list.

Kept out of the study flow on purpose. Both are SHARED: a sentence retired
here, or a word edited or deleted, changes things for everyone studying on
this database.
"""

import streamlit as st

import db_manager as db
from auth import require_login, sidebar_user_badge

st.set_page_config(page_title="Sentence bank & words", page_icon="🛠️", layout="centered")
USER = require_login()

with st.sidebar:
    sidebar_user_badge()

st.title("🛠️ Sentence bank & words")
st.caption("Changes here are shared: they affect everyone studying on this database.")

tab_bank, tab_words = st.tabs(["🏦 Sentence bank", "📝 Word list"])

# ======================================================================
# SENTENCE BANK
# ======================================================================
with tab_bank:
    stats = db.bank_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Vetted sentences", stats["active_sentences"])
    c2.metric("Words covered", f"{stats['vocab_covered']}/{stats['vocab_total']}")
    c3.metric("Flagged", stats["flagged"])
    if stats["vocab_total"]:
        st.progress(min(1.0, stats["vocab_covered"] / stats["vocab_total"]))
    st.caption(
        "The bank grows automatically as you study (every validated live "
        "generation is deposited). To pre-build coverage in bulk, run "
        "`python src/build_sentence_bank.py` — see the script header for usage. "
        "Human-written Tatoeba sentences can be imported with "
        "`python src/seed_from_tatoeba.py`.")

    st.subheader("🔍 Browse sentences")
    col_a, col_b = st.columns([2, 1])
    word_filter = col_a.text_input(
        "Filter by vocab word (hanzi)", "",
        placeholder="e.g. 巴刹 — leave empty for newest across all words")
    show_status = col_b.selectbox("Status", ["active", "flagged"])

    rows = db.bank_browse(word_filter.strip() or None, status=show_status)
    if not rows:
        st.info("No sentences match.")
    for row in rows:
        ex = row["exercise"]
        label = f"{row['chinese']}  ·  [{row['vocab_chinese']}]  ·  used {row['times_used']}×"
        with st.expander(label):
            st.write(f"**Pinyin:** {ex.get('pinyin', '')}")
            st.write(f"**English:** {ex.get('english_correct', '')}")
            distractors = ex.get("english_distractors", [])
            if distractors:
                st.caption("Distractors: " + " | ".join(distractors))
            st.caption(f"Source: {ex.get('source', 'generated')}")
            if row["status"] == "active":
                if st.button("🚩 Retire this sentence", key=f"retire_{row['chinese']}"):
                    db.flag_sentence(row["chinese"], "retired from bank page")
                    st.rerun()
            elif st.button("♻️ Restore (flagged by mistake)", key=f"restore_{row['chinese']}"):
                db.unflag_sentence(row["chinese"])
                st.rerun()

    st.subheader("🚩 Recent flags")
    st.caption("These are injected into the generation and review prompts as negative "
               "examples — every flag permanently strengthens the pipeline.")
    flags = db.get_recent_flags(limit=15)
    if not flags:
        st.info("Nothing flagged yet.")
    for sentence, reason in flags:
        cols = st.columns([4, 1])
        cols[0].write(f"**{sentence}**" + (f" — {reason}" if reason else ""))
        if cols[1].button("♻️ Restore", key=f"unflag_{sentence}"):
            db.unflag_sentence(sentence)
            st.rerun()

# ======================================================================
# WORD LIST
# ======================================================================
with tab_words:
    st.caption("Fix a word's characters, pinyin or meaning (the meaning also guides the "
               "sentences written for it), or remove a word that shouldn't be there.")
    query = st.text_input("Find a word", placeholder="hanzi, pinyin or English",
                          key="adm_query")
    found = db.find_words(query) if query.strip() else []
    if query.strip() and not found:
        st.info("No word matches.")
    if found:
        pick = st.selectbox("Word", found, key="adm_pick",
                            format_func=lambda w: f"{w['chinese']}  {w['pinyin']}  — "
                                                  f"{(w['english'] or '')[:50]}")
        with st.form(f"adm_edit_{pick['id']}"):
            c1, c2 = st.columns(2)
            zh = c1.text_input("Characters", pick["chinese"])
            py = c2.text_input("Pinyin", pick["pinyin"])
            en = st.text_input("Meaning", pick["english"])
            if st.form_submit_button("💾 Save changes", type="primary"):
                db.update_word_in_db(pick["id"], zh.strip(), py.strip(), en.strip())
                st.success("Saved.")
        with st.expander("Delete this word"):
            st.warning(f"Deleting **{pick['chinese']}** removes it — and its progress — for "
                       "everyone studying on this database.")
            sure = st.checkbox("I understand", key=f"adm_sure_{pick['id']}")
            if st.button("🗑️ Delete permanently", disabled=not sure, key=f"adm_del_{pick['id']}"):
                db.delete_word_from_db(pick["id"])
                st.success(f"Deleted {pick['chinese']}.")
                st.rerun()
