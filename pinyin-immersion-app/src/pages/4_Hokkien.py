# src/pages/4_Hokkien.py
"""
福建話 — Penang Hokkien.

Runs alongside the Mandarin app on the same vocabulary, but with a
deliberately different trust model: no LLM ever writes Hokkien here. The
deck is built offline from licensed dictionaries by build_hokkien_deck.py,
and every entry stays unverified — and undrillable — until you confirm it.

Why: there is no open Penang Hokkien lexicon. Machine translation of
Mandarin→Hokkien scores far below usable quality, and Penang Hokkien is
lower-resource still. An entry that says 'consensus' means two Taiwanese
dictionaries agreed; it does NOT mean a Penang speaker would say it.
"""

import streamlit as st

import db_manager as db
from hokkien_engine import tailo_to_taiji, normalise_tailo, answers_match

st.set_page_config(page_title="Hokkien", page_icon="🇲🇾", layout="centered")

TIER_BADGE = {
    "penang": ("🟢 Penang-tagged", "A Penang-specific reading was found in Wiktionary."),
    "consensus": ("🟡 Consensus", "2+ Taiwanese dictionaries agree — may differ in Penang."),
    "single": ("🔴 Single source", "Only one dictionary offered this. Verify before trusting."),
    "core": ("🔵 Core vocabulary", "Foundational Hokkien from the 基礎語句 "
             "basic-vocabulary dictionary — not derived from your Mandarin "
             "list. Characters confirmed against the Mandarin gloss."),
    "composed": ("🟠 Composed", "Built word-by-word from parts because the whole "
                 "phrase wasn't in any dictionary. Often literal and sometimes "
                 "wrong — check carefully."),
}

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("福建話 Hokkien")
    try:
        s = db.hokkien_stats()
    except Exception:
        s = None
    if not s or s["total"] == 0:
        st.info("Deck not built yet.")
    else:
        st.metric("Verified & drillable", s["verified"])
        st.caption(f"{s['unverified']} awaiting verification · "
                   f"{s['penang']} Penang-tagged · {s['consensus']} consensus")
        if s["total"]:
            st.progress(s["verified"] / s["total"])

# ----------------------------------------------------------------------
# EMPTY STATE
# ----------------------------------------------------------------------
stats = None
try:
    stats = db.hokkien_stats()
except Exception as e:
    st.error(f"Hokkien tables unavailable: {e}")
    st.stop()

if stats["total"] == 0:
    st.title("福建話 Penang Hokkien")
    st.info("The Hokkien deck hasn't been built yet.")
    st.markdown(
        "Build it offline from licensed dictionaries — no AI guessing:\n\n"
        "```\n"
        "git clone --depth 1 https://github.com/ChhoeTaigi/ChhoeTaigiDatabase.git\n"
        "python src/build_hokkien_deck.py --chhoetaigi ChhoeTaigiDatabase\n"
        "```\n\n"
        "Optionally add the Penang overlay by downloading the Chinese subset "
        "from kaikki.org and passing `--wiktionary <file.jsonl>`.")
    st.stop()

st.title("福建話 Penang Hokkien")

tab_drill, tab_verify, tab_browse = st.tabs(
    ["📚 Study", f"✅ Verify ({stats['unverified']})", "🔍 Browse"])

# ======================================================================
# STUDY — verified entries only
# ======================================================================
with tab_drill:
    if stats["verified"] == 0:
        st.warning("Nothing verified yet. Confirm some entries in the "
                   "**Verify** tab and they'll appear here.")
    else:
        mode = st.radio(
            "Mode",
            ["認 Recognise (hanji → meaning)",
             "音 Romanise (hanji → Tâi-lô)",
             "講 Produce (English → Hokkien)"],
            horizontal=False)

        if "hk_queue" not in st.session_state:
            st.session_state.hk_queue = []
            st.session_state.hk_i = 0
            st.session_state.hk_shown = False

        if st.button("▶️ Start / refresh session", use_container_width=True):
            st.session_state.hk_queue = db.hokkien_session(limit=20)
            st.session_state.hk_i = 0
            st.session_state.hk_shown = False
            st.rerun()

        q = st.session_state.hk_queue
        if q and st.session_state.hk_i < len(q):
            card = q[st.session_state.hk_i]
            st.caption(f"Card {st.session_state.hk_i + 1} of {len(q)}")

            # ---- prompt side ----
            if mode.startswith("認"):
                st.markdown(f"<div style='font-size:56px;text-align:center'>"
                            f"{card['hokkien_hanji']}</div>",
                            unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center;color:#7EB6FF;"
                            f"font-size:22px'>{card['tailo']}</div>",
                            unsafe_allow_html=True)
            elif mode.startswith("音"):
                st.markdown(f"<div style='font-size:56px;text-align:center'>"
                            f"{card['hokkien_hanji']}</div>",
                            unsafe_allow_html=True)
                typed = st.text_input("Type the Tâi-lô (tones optional)",
                                      key=f"hk_in_{card['id']}")
            else:
                st.markdown(f"### {card['english']}")
                st.caption(f"Mandarin: {card['mandarin_full'] or card['mandarin']}")

            if not st.session_state.hk_shown:
                if st.button("Show answer", type="primary",
                             use_container_width=True):
                    st.session_state.hk_shown = True
                    st.rerun()
            else:
                st.markdown("---")
                st.markdown(f"**Hokkien:** {card['hokkien_hanji']}")
                st.markdown(f"**Tâi-lô:** `{card['tailo']}`")
                st.markdown(f"**Taiji:** `{card['taiji']}`")
                st.markdown(f"**Meaning:** {card['english']}")
                if mode.startswith("音"):
                    guess = st.session_state.get(f"hk_in_{card['id']}", "")
                    if guess:
                        ok = answers_match(guess, card["tailo"])
                        st.success("Match ✓") if ok else st.error(
                            f"You wrote `{guess}`")

                cols = st.columns(4)
                for col, (label, grade) in zip(
                        cols, [("Again", 0), ("Hard", 1), ("Good", 2), ("Easy", 3)]):
                    if col.button(label, key=f"g{grade}_{card['id']}",
                                  use_container_width=True):
                        db.hokkien_grade(card["id"], grade, card)
                        st.session_state.hk_i += 1
                        st.session_state.hk_shown = False
                        st.rerun()
        elif q:
            st.success("Session complete 🎉")
            if st.button("New session", use_container_width=True):
                st.session_state.hk_queue = []
                st.rerun()
        else:
            st.caption("Press start to pull a session of verified cards.")

# ======================================================================
# VERIFY — the queue that gates everything
# ======================================================================
with tab_verify:
    st.caption(
        "Each entry was assembled from dictionaries, not invented. Confirm "
        "what's right, correct what isn't, reject what Penang wouldn't say. "
        "Only confirmed entries enter the study rotation.")
    tier_filter = st.selectbox(
        "Show tier", ["all", "penang", "consensus", "core", "single", "composed"], index=0)
    rows = db.hokkien_queue(limit=20,
                            tier=None if tier_filter == "all" else tier_filter)
    if not rows:
        st.success("Verification queue is empty. 好势!")

    for r in rows:
        badge, why = TIER_BADGE.get(r["tier"], ("?", ""))
        with st.expander(
                f"{r['mandarin']} → {r['hokkien_hanji']}  ·  {r['tailo']}  ·  {badge}"):
            st.caption(why)
            st.write(f"**Mandarin:** {r['mandarin_full'] or r['mandarin']}")
            st.write(f"**English:** {r['english']}")
            st.write(f"**Sources:** {r['sources'] or '—'} · "
                     f"{r['alternatives']} candidate form(s) considered")
            new_tailo = st.text_input("Tâi-lô", value=r["tailo"],
                                      key=f"tl_{r['id']}")
            st.caption(f"Taiji (auto): `{tailo_to_taiji(normalise_tailo(new_tailo))}`")
            note = st.text_input("Note (optional)", value=r.get("note") or "",
                                 key=f"nt_{r['id']}")
            c1, c2 = st.columns(2)
            if c1.button("✅ Confirm", key=f"ok_{r['id']}",
                         use_container_width=True):
                tl = normalise_tailo(new_tailo)
                db.hokkien_set_status(r["id"], "verified", tailo=tl,
                                      taiji=tailo_to_taiji(tl), note=note)
                st.rerun()
            if c2.button("🚫 Reject", key=f"no_{r['id']}",
                         use_container_width=True):
                db.hokkien_set_status(r["id"], "rejected", note=note)
                st.rerun()

# ======================================================================
# BROWSE
# ======================================================================
with tab_browse:
    term = st.text_input("Search Mandarin, English, hàn-jī or Tâi-lô", "")
    if term.strip():
        for r in db.hokkien_search(term.strip()):
            badge = TIER_BADGE.get(r["tier"], ("?", ""))[0]
            mark = {"verified": "✅", "rejected": "🚫"}.get(r["status"], "⏳")
            st.write(f"{mark} **{r['hokkien_hanji']}** `{r['tailo']}` / "
                     f"`{r['taiji']}` — {r['english']}  ·  {badge}")
    else:
        st.caption("Type to search the deck.")
