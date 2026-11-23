# src/games_hsk_page.py
"""
🎮 Play on the HSK track (views/8_Games.py hands over here): the games in
games_hsk.py over the HSK 1-4 syllabus, and the herb game kept apart.

Answers are cards you tap (src/choice_board, src/memory_board); the
sentence scramble uses word tiles like the grammar Build stage. A game in
progress is saved after every move ("games_hsk"), so leaving the page picks
up where you left off. Scores keep the existing best-score table, under the
game's own key (hsk_listen, herb_name, ...).

The picture games and herb writing live on other pages: "Picture games"
runs the old picture games over HSK words only (S.games_pictures), and "Write
herb names" opens the Write page in herb mode (S.hw_herbs).
"""

import random
import time
import uuid

import streamlit as st

import db_manager as db
import game_components as gc
import games as gm
import games_hsk as gh
import grammar_build as gb
import quiz
import session_store as store
from audio_engine import create_audio_file, warm

S = st.session_state
SAVED = ("gh_game", "gh_sid", "gh_level", "gh_rounds", "gh_i", "gh_score", "gh_streak",
         "gh_best_streak", "gh_missed", "gh_ans", "gh_cards", "gh_matched", "gh_moves",
         "gh_items")
STORE = "games_hsk"
ALL = {**gh.GAMES, **gh.HERB_GAMES}


def _key(game):
    """The best-score key: herb games under their own name, the rest hsk_*."""
    return game if game.startswith("herb_") else f"hsk_{game}"


def run(user):
    uid = user["id"]

    def reset():
        for k in [k for k in S if k.startswith("gh_")]:
            del S[k]
        store.drop(uid, STORE)

    def persist():
        store.keep(uid, STORE, SAVED, clock="gh_t0")

    def play(text, autoplay=False):
        cache = S.setdefault("games_audio", {})
        if text not in cache:
            cache[text] = create_audio_file(text)
        if cache[text]:
            st.audio(cache[text], format="audio/mp3", autoplay=autoplay)

    def html(markup):
        st.markdown(markup, unsafe_allow_html=True)

    def big(zh, py="", en=""):
        html(f"<div style='font-size:1.9rem;line-height:1.35'>{zh}</div>"
             + (f"<div style='color:#78909c'>{py}</div>" if py else "")
             + (f"<div>{en}</div>" if en else ""))

    def start(game):
        reset()
        levels = db.get_hsk_levels(uid) or {}
        rng = random.Random()
        S.gh_game, S.gh_sid, S.gh_t0 = game, uuid.uuid4().hex, time.time()
        S.gh_level = gh.level_for(game, levels)
        S.gh_score = S.gh_streak = S.gh_best_streak = S.gh_i = 0
        S.gh_missed = []
        if game == "memory":
            S.gh_cards, S.gh_matched, S.gh_moves = gh.memory_cards(S.gh_level, rng=rng), [], 0
        elif game == "scramble":
            S.gh_items = gh.scramble_items(S.gh_level, rng=rng)
        elif game in gh.HERB_GAMES:
            S.gh_rounds = gh.herb_rounds(game, rng=rng)
        else:
            S.gh_rounds = gh.rounds_for(game, levels, rng=rng)
            warm([r["audio"] or r["reveal"]["zh"] for r in S.gh_rounds])
        persist()

    def finish(score, items):
        if "gh_saved" not in S:
            S.gh_saved = db.save_game_score(uid, _key(S.gh_game), score)
            db.log_study_session(uid, "games", time.time() - S.get("gh_t0", time.time()),
                                 items=items)
            store.drop(uid, STORE)
        return S.gh_saved

    def record(zh, correct):
        db.background(db.log_activity, uid, "games", zh, 2 if correct else 0)

    def score_hit(correct):
        S.gh_streak = S.gh_streak + 1 if correct else 0
        S.gh_best_streak = max(S.gh_best_streak, S.gh_streak)
        S.gh_score += gm.points(correct, S.gh_streak - 1 if correct else 0)

    def again_buttons():
        c1, c2 = st.columns(2)
        if c1.button("▶️ Play again", type="primary", width="stretch"):
            start(S.gh_game)
            st.rerun()
        if c2.button("Choose another game", width="stretch"):
            reset()
            st.rerun()

    def end_button():
        st.write("")
        if st.button("✖ End game", key="gh_end"):
            reset()
            st.rerun()

    def notes_html(notes):
        return "".join(f"<div style='color:#78909c'>{zh} {py}" + (f" — {en}" if en else "")
                       + "</div>" for zh, py, en in notes)

    # ------------------------------------------------------------------
    # picker
    # ------------------------------------------------------------------
    st.title("🎮 Play")
    if "gh_game" not in S:
        if store.resume(uid, STORE, SAVED, clock="gh_t0", same_day=False, max_age_hours=24):
            if S.get("gh_game") not in ALL:
                reset()
    if "gh_game" not in S:
        levels = db.get_hsk_levels(uid) or {}
        st.caption("Quick games over HSK 1–4 for spare minutes — today's plan comes first. "
                   + (f"Listening games use HSK {levels.get('listen') or 1}, reading games "
                      f"HSK {levels.get('read') or 1}, the scramble HSK "
                      f"{gh.level_for('scramble', levels)} grammar." if levels else
                      "Everything is HSK 1 until you take the level test (Settings)."))
        best = db.game_scores(uid)

        def picker(games):
            for key, (icon, name, blurb) in games.items():
                b = best.get(_key(key)) if key not in ("pictures", "herb_write") else None
                sub = f" · best {b['best']}" if b else ""
                if st.button(f"{icon}  {name}{sub}", key=f"ghpick_{key}", width="stretch"):
                    if key == "pictures":
                        S.games_pictures = True
                        st.rerun()
                    elif key == "herb_write":
                        S.hw_herbs = True
                        st.switch_page("views/2_Handwriting.py")
                    else:
                        start(key)
                        st.rerun()
                st.caption(blurb)

        picker(gh.GAMES)
        st.subheader("🌿 Herbs")
        st.caption("Separate from HSK: the herb list from Herb Dojo (data/herbs.csv), "
                   "tier-1 herbs most often.")
        picker(gh.HERB_GAMES)
        st.stop()

    game = S.gh_game
    store.notice()

    # ------------------------------------------------------------------
    # memory match: characters <-> meanings
    # ------------------------------------------------------------------
    if game == "memory":
        cards, matched = S.gh_cards, set(S.gh_matched)
        if len(matched) == len(cards):
            score = gm.memory_score(len(cards) // 2, S.gh_moves)
            new_best = finish(score, len(cards) // 2)
            st.success(f"All matched in {S.gh_moves} turns — {score} points"
                       + (" · new best! 🎉" if new_best else ""))
            again_buttons()
            st.stop()
        value = gc.memory_board(sid=S.gh_sid, cards=cards, show_pinyin=False,
                                state={"matched": sorted(matched), "moves": S.gh_moves},
                                key=f"gh_board_{S.gh_sid}", default=None)
        if value and value.get("sid") == S.gh_sid:
            now = gh.memory_matches(cards, value.get("matched"), matched)
            moves = max(S.gh_moves, int(value.get("moves") or 0))
            if now != matched or moves != S.gh_moves:
                for zh in {cards[n]["zh"] for n in now - matched}:
                    record(zh, True)
                S.gh_matched, S.gh_moves = sorted(now), moves
                persist()
                if len(now) == len(cards):
                    st.rerun()
        end_button()
        st.stop()

    # ------------------------------------------------------------------
    # sentence scramble
    # ------------------------------------------------------------------
    if game == "scramble":
        items, i = S.gh_items, S.gh_i
        if not items:
            st.info("No sentences at this level yet.")
            end_button()
            st.stop()
        if i >= len(items):
            new_best = finish(S.gh_score, len(items))
            right = len(items) - len(S.gh_missed)
            st.success(f"{right} of {len(items)} · {S.gh_score} points"
                       + (" · new best! 🎉" if new_best else ""))
            for m in S.gh_missed:
                big(m["hanzi"], m["sentence_pinyin"], m["english"])
            again_buttons()
            st.stop()
        item = items[i]
        st.progress(i / len(items), text=f"Sentence {i + 1} of {len(items)} · {S.gh_score} points"
                    + (f" · 🔥 {S.gh_streak}" if S.gh_streak >= 2 else ""))
        st.markdown(f"**Build it:** {item['english']}")
        a = S.get("gh_ans") or {"picked": []}
        picked, tiles = a["picked"], item["tiles"]
        built = [tiles[n] for n in picked]
        html(f"<div style='font-size:1.9rem;line-height:1.5;min-height:2.9rem'>"
             f"{' '.join(built) or '…'}</div>")
        key = f"gh_{S.gh_sid}_{i}"
        if "verdict" not in a:
            left = [n for n in range(len(tiles)) if n not in picked]
            cols = st.columns(min(4, max(1, len(left))))
            for c, n in enumerate(left):
                if cols[c % len(cols)].button(tiles[n], key=f"{key}_t{n}", width="stretch"):
                    S.gh_ans = {"picked": picked + [n]}
                    persist()
                    st.rerun()
            c1, c2, c3 = st.columns(3)
            if c1.button("↩️ Undo", disabled=not picked, key=f"{key}_undo", width="stretch"):
                S.gh_ans = {"picked": picked[:-1]}
                st.rerun()
            verdict = None
            if c2.button(quiz.DONT_KNOW, key=f"{key}_dk", width="stretch"):
                verdict = "wrong"
            if not left and c3.button("Check", type="primary", key=f"{key}_check",
                                      width="stretch"):
                verdict = gb.check(built, item)
            if verdict:
                score_hit(verdict == "correct")
                if verdict != "correct":
                    S.gh_missed.append(item)
                record(item["hanzi"], verdict == "correct")
                S.gh_ans = {"picked": picked, "verdict": verdict}
                persist()
                st.rerun()
            end_button()
            st.stop()
        st.markdown("✅ Right." if a["verdict"] == "correct" else "❌ The order is:")
        big(item["hanzi"], item["sentence_pinyin"])
        play(item["hanzi"])
        if st.button("Next ▶️", type="primary", key=f"{key}_next", width="stretch"):
            S.gh_i += 1
            S.pop("gh_ans", None)
            persist()
            st.rerun()
        end_button()
        st.stop()

    # ------------------------------------------------------------------
    # card games: listen, meaning, look-alikes, measure words, herbs
    # ------------------------------------------------------------------
    rounds, i = S.gh_rounds, S.gh_i
    if not rounds:
        st.info("Nothing to play at this level yet.")
        end_button()
        st.stop()
    if i >= len(rounds):
        new_best = finish(S.gh_score, len(rounds))
        right = len(rounds) - len(S.gh_missed)
        st.success(f"{right} of {len(rounds)} · {S.gh_score} points · best streak "
                   f"{S.gh_best_streak}" + (" · new best! 🎉" if new_best else ""))
        if right == len(rounds):
            st.balloons()
        if S.gh_missed:
            st.caption("Worth another look:")
            for r in S.gh_missed:
                big(r["zh"], r["py"], r["en"])
        again_buttons()
        st.stop()

    rnd = rounds[i]
    st.progress(i / len(rounds), text=f"Round {i + 1} of {len(rounds)} · {S.gh_score} points"
                + (f" · 🔥 {S.gh_streak}" if S.gh_streak >= 2 else ""))
    ans = S.get("gh_ans")
    if rnd["audio"]:
        st.caption("🔊 Listen, then tap the characters.")
        play(rnd["audio"], autoplay=ans is None)
    value = gc.choice_board(sid=S.gh_sid, round=i, prompt=rnd["prompt"], options=rnd["options"],
                            answer=rnd["answer"], answered=(ans or {}).get("chosen"),
                            show_pinyin=True, key=f"gh_choice_{S.gh_sid}", default=None)
    tapped = bool(ans is None and value and value.get("sid") == S.gh_sid
                  and value.get("round") == i and isinstance(value.get("chosen"), int)
                  and 0 <= value["chosen"] < len(rnd["options"]))
    dont_know = ans is None and not tapped and st.button(quiz.DONT_KNOW, width="stretch",
                                                         key=f"gh_dk_{S.gh_sid}_{i}")
    if tapped or dont_know:
        chosen = value["chosen"] if tapped else -1
        correct = tapped and chosen == rnd["answer"]
        score_hit(correct)
        if not correct:
            S.gh_missed.append(rnd["reveal"])
        record(rnd["reveal"]["zh"], correct)
        S.gh_ans = {"correct": correct, "chosen": chosen, "dont_know": bool(dont_know)}
        persist()
        st.rerun()

    if ans is not None:
        r = rnd["reveal"]
        st.markdown("✅ **Right!**" if ans["correct"] else
                    f"{'🤷' if ans.get('dont_know') else '❌'} It was:")
        big(r["zh"], r["py"], r["en"])
        if rnd["notes"]:
            html("<div style='margin-top:6px;font-size:0.95rem'>The others: "
                 + notes_html(rnd["notes"]) + "</div>")
        if not rnd["audio"] and game not in gh.HERB_GAMES:
            play(r["zh"])
        if st.button("Next ▶️", type="primary", width="stretch"):
            S.gh_i += 1
            S.pop("gh_ans", None)
            persist()
            st.rerun()
    end_button()
