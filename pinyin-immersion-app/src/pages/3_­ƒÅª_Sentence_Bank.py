# src/pages/3_🏦_Sentence_Bank.py
"""Curation view for the vetted sentence bank: coverage stats, browse and
spot-check sentences per word, retire mistakes, restore false flags."""

import streamlit as st

import db_manager as db

st.set_page_config(page_title="Sentence Bank", page_icon="🏦", layout="centered")
st.title("🏦 Sentence Bank")

# ==========================================
# 1. COVERAGE
# ==========================================
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

st.markdown("---")

# ==========================================
# 2. BROWSE / SPOT-CHECK
# ==========================================
st.subheader("🔍 Browse sentences")
col_a, col_b = st.columns([2, 1])
with col_a:
    word_filter = st.text_input(
        "Filter by vocab word (hanzi)", "",
        placeholder="e.g. 巴刹 — leave empty for newest across all words")
with col_b:
    show_status = st.selectbox("Status", ["active", "flagged"])

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
        source = ex.get("source", "generated")
        st.caption(f"Source: {source}")
        if row["status"] == "active":
            if st.button("🚩 Retire this sentence",
                         key=f"retire_{row['chinese']}"):
                db.flag_sentence(row["chinese"], "retired from bank page")
                st.rerun()
        else:
            if st.button("♻️ Restore (flagged by mistake)",
                         key=f"restore_{row['chinese']}"):
                db.unflag_sentence(row["chinese"])
                st.rerun()

st.markdown("---")

# ==========================================
# 3. RECENT FLAGS (feeding the prompts as negative examples)
# ==========================================
st.subheader("🚩 Recent flags")
st.caption("These are injected into the generation and review prompts as "
           "negative examples — every flag permanently strengthens the "
           "pipeline.")
flags = db.get_recent_flags(limit=15)
if not flags:
    st.info("Nothing flagged yet.")
for sentence, reason in flags:
    cols = st.columns([4, 1])
    cols[0].write(f"**{sentence}**" + (f" — {reason}" if reason else ""))
    if cols[1].button("♻️ Restore", key=f"unflag_{sentence}"):
        db.unflag_sentence(sentence)
        st.rerun()
