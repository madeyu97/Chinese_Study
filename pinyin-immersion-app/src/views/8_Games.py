# src/views/8_Games.py
"""
🎮 Play - picture games for spare minutes: something to open instead of a
feed. Extra practice on top of today's plan, not a replacement for it.

Four quick games linking pictures to words (body, clothing, food, hawker
food, market & local fruit, home, places, nature, animals, TCM clinic, TCM
herbs). Words can be shown with pinyin or as characters only. Answers
register on tap; scores, streaks and best scores keep it light. Time played
goes into the ledger as play.

Every answer is a card you tap: the picture or word cards in the quiz games
(src/choice_board), the face-down cards in memory match (src/memory_board).
A game in progress is saved to the database after every move, so leaving
the page - or the app - and coming back picks up where you left off.
"""

import random
import time
import uuid

import streamlit as st

import db_manager as db
import game_items as gi
import games as gm
import game_components as gc
import session_store as store
from audio_engine import create_audio_file, warm
from auth import require_login, sidebar_user_badge
from game_images import credit_lines, data_uri, img_tag

st.set_page_config(page_title="Play", page_icon="🎮", layout="centered")
USER = require_login()
USER_ID = USER["id"]
S = st.session_state


# what a game in progress is saved as (widget keys and audio are left out)
SAVED = ("gm_game", "gm_sid", "gm_topped", "gm_vocab", "gm_show", "gm_cards", "gm_matched",
         "gm_moves", "gm_rounds", "gm_i", "gm_score", "gm_streak", "gm_best_streak",
         "gm_missed", "gm_ans")


def reset():
    """End the game: forget it here and in the saved copy."""
    for k in [k for k in S if k.startswith("gm_")]:
        del S[k]
    store.drop(USER_ID, "games")


def persist():
    """Save the game in progress, so it survives leaving the page or the app."""
    store.keep(USER_ID, "games", SAVED, clock="gm_t0")


def restore():
    """Pick up a saved game, if there is one from the last day."""
    if store.resume(USER_ID, "games", SAVED, clock="gm_t0", same_day=False, max_age_hours=24):
        if S.get("gm_game") in gm.GAMES:
            return True
        reset()
    return False


SHOW = ["Characters + pinyin", "Characters only"]
WORDS = ["All — learn new ones too", "Only words I've met"]
# kept outside the widgets, which Streamlit forgets while a game is on screen
PREFS = S.setdefault("games_prefs", {"show": SHOW[0], "cats": list(gi.CATEGORIES),
                                     "words": WORDS[0]})

with st.sidebar:
    sidebar_user_badge()

st.title("🎮 Play")
if "gm_game" not in S:
    restore()
show_pinyin = S.get("gm_show", PREFS["show"] == SHOW[0])


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def play(text, autoplay=False):
    cache = S.setdefault("games_audio", {})
    if text not in cache:
        cache[text] = create_audio_file(text)
    if cache[text]:
        st.audio(cache[text], format="audio/mp3", autoplay=autoplay)


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def word_html(item, size="2.2rem"):
    py = (f"<div style='font-size:1rem;color:#78909c'>{item['pinyin']}</div>"
          if show_pinyin else "")
    return f"<div style='font-size:{size};line-height:1.3'>{item['chinese']}</div>{py}"


def card(item, kind):
    """One card for a board: the item's picture or its word."""
    if kind == "image":
        return {"kind": "image", "img": data_uri(item["image"])}
    return {"kind": "word", "zh": item["chinese"], "py": item["pinyin"]}


def record(item, correct, game):
    vid = S.gm_vocab.get(item["chinese"])
    # logged in the background: the game never waits for the database
    if vid:
        db.background(db.log_word_attempt, USER_ID, vid, "recognition", f"game_{game}",
                      "correct" if correct else "wrong", {"kind": "game"})
    db.background(db.log_activity, USER_ID, "games", item["chinese"], 2 if correct else 0)


def start(game):
    reset()
    only_met = PREFS["words"] == WORDS[1]
    met = {w["chinese"] for w in db.introduced_words(USER_ID)} if only_met else None
    pool, topped = gm.word_pool(PREFS["cats"] or list(gi.CATEGORIES), met, only_met)
    S.gm_game, S.gm_topped, S.gm_t0 = game, topped, time.time()
    S.gm_sid, S.gm_show = uuid.uuid4().hex, PREFS["show"] == SHOW[0]
    S.gm_vocab = db.vocab_ids_for([i["chinese"] for i in pool])
    if game == "memory":
        S.gm_cards, S.gm_matched, S.gm_moves = gm.memory_board(pool), set(), 0
    else:
        S.gm_rounds, S.gm_i, S.gm_score, S.gm_streak, S.gm_best_streak = \
            gm.quiz_rounds(pool), 0, 0, 0, 0
        S.gm_missed = []
        warm([r["target"]["chinese"] for r in S.gm_rounds])   # clips made ahead, in the background
    persist()


def end_button():
    st.write("")
    if st.button("✖ End game", key="gm_end"):
        reset()
        st.rerun()


# ----------------------------------------------------------------------
# game picker
# ----------------------------------------------------------------------
if "gm_game" not in S:
    st.caption("Quick picture games for spare minutes — every round still links a word to "
               "its meaning. Today's plan comes first; this is the extra.")
    with st.expander("Topics and display"):
        PREFS["show"] = st.radio("Show words as", SHOW, index=SHOW.index(PREFS["show"]),
                                 key="games_show", horizontal=True)
        PREFS["cats"] = st.multiselect(
            "Topics", list(gi.CATEGORIES), default=PREFS["cats"],
            format_func=lambda c: f"{gi.CATEGORIES[c][2]} {gi.CATEGORIES[c][1]}", key="games_cats")
        PREFS["words"] = st.radio("Words", WORDS, index=WORDS.index(PREFS["words"]),
                                  key="games_words", horizontal=True)
    best = db.game_scores(USER_ID)
    for key, (icon, name, blurb) in gm.GAMES.items():
        b = best.get(key)
        sub = f" · best {b['best']}" if b else ""
        if st.button(f"{icon}  {name}{sub}", key=f"pick_{key}", width="stretch"):
            start(key)
            st.rerun()
        st.caption(blurb)
    with st.expander("Picture credits"):
        st.markdown("Emoji pictures: [Twemoji](https://github.com/jdecked/twemoji) © Twitter, Inc "
                    "and other contributors, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).\n\n"
                    "Photos and illustrations from [Wikimedia Commons](https://commons.wikimedia.org), "
                    "shared under the same licence as the original:\n\n" + "\n".join(credit_lines(gi.ITEMS)))
    st.stop()

game = S.gm_game
store.notice()
if S.get("gm_topped"):
    st.caption("Not enough words you've met in these topics yet — a few new ones are mixed in.")


def finish(score):
    if "gm_saved" not in S:
        S.gm_saved = db.save_game_score(USER_ID, game, score)
        db.log_study_session(USER_ID, "games", time.time() - S.get("gm_t0", time.time()),
                             items=len(S.get("gm_rounds") or S.get("gm_cards") or []))
        store.drop(USER_ID, "games")          # finished: nothing to pick up later
    return S.gm_saved


# ----------------------------------------------------------------------
# memory match
# ----------------------------------------------------------------------
if game == "memory":
    cards, matched = S.gm_cards, S.gm_matched
    if len(matched) == len(cards):
        score = gm.memory_score(len(cards) // 2, S.gm_moves)
        new_best = finish(score)
        st.success(f"All matched in {S.gm_moves} turns — {score} points"
                   + (" · new best! 🎉" if new_best else ""))
        if S.gm_moves == len(cards) // 2:
            st.balloons()
        c1, c2 = st.columns(2)
        if c1.button("▶️ Play again", type="primary", width="stretch"):
            start(game)
            st.rerun()
        if c2.button("Choose another game", width="stretch"):
            reset()
            st.rerun()
        st.stop()
    board = [{"pair": c["item"]["chinese"], "face": c["face"],
              "img": data_uri(c["item"]["image"]) if c["face"] == "image" else "",
              "zh": c["item"]["chinese"], "py": c["item"]["pinyin"], "en": c["item"]["english"]}
             for c in cards]
    value = gc.memory_board(sid=S.gm_sid, cards=board, show_pinyin=show_pinyin,
                            state={"matched": sorted(matched), "moves": S.gm_moves},
                            key=f"gm_board_{S.gm_sid}", default=None)
    if value and value.get("sid") == S.gm_sid:
        now = gm.accept_matches(cards, value.get("matched"), matched)
        moves = max(S.gm_moves, int(value.get("moves") or 0))
        if now != matched or moves != S.gm_moves:
            for item in {cards[n]["item"]["chinese"]: cards[n]["item"] for n in now - matched}.values():
                record(item, True, game)
            S.gm_matched, S.gm_moves = now, moves
            persist()
            if len(now) == len(cards):
                st.rerun()                    # on to the score
    end_button()
    st.stop()


# ----------------------------------------------------------------------
# quiz games: picture → word, word → picture, listen → picture
# ----------------------------------------------------------------------
rounds, i = S.gm_rounds, S.gm_i
if i >= len(rounds):
    new_best = finish(S.gm_score)
    right = len(rounds) - len(S.gm_missed)
    st.success(f"{right} of {len(rounds)} · {S.gm_score} points · best streak {S.gm_best_streak}"
               + (" · new best! 🎉" if new_best else ""))
    if right == len(rounds):
        st.balloons()
    if S.gm_missed:
        st.caption("Worth another look:")
        html("<div style='display:flex;flex-wrap:wrap;gap:14px'>" + "".join(
            f"<div style='text-align:center'>{img_tag(m['image'], 60)}{word_html(m, '1.2rem')}</div>"
            for m in S.gm_missed) + "</div>")
    c1, c2 = st.columns(2)
    if c1.button("▶️ Play again", type="primary", width="stretch"):
        start(game)
        st.rerun()
    if c2.button("Choose another game", width="stretch"):
        reset()
        st.rerun()
    st.stop()

rnd = rounds[i]
target, options = rnd["target"], rnd["options"]
st.progress(i / len(rounds), text=f"Round {i + 1} of {len(rounds)} · {S.gm_score} points"
            + (f" · 🔥 {S.gm_streak}" if S.gm_streak >= 2 else ""))
ans = S.get("gm_ans")

if game == "listen":
    st.caption("🔊 Listen, then tap the picture.")
    play(target["chinese"], autoplay=ans is None)
prompt = (card(target, "image") if game == "picture" else
          card(target, "word") if game == "word" else None)
answer = options.index(target)
value = gc.choice_board(sid=S.gm_sid, round=i, prompt=prompt,
                        options=[card(o, "word" if game == "picture" else "image") for o in options],
                        answer=answer, answered=(ans or {}).get("chosen"), show_pinyin=show_pinyin,
                        key=f"gm_choice_{S.gm_sid}", default=None)
if (ans is None and value and value.get("sid") == S.gm_sid and value.get("round") == i
        and isinstance(value.get("chosen"), int) and 0 <= value["chosen"] < len(options)):
    chosen = options[value["chosen"]]
    correct = chosen["chinese"] == target["chinese"]
    S.gm_streak = S.gm_streak + 1 if correct else 0
    S.gm_best_streak = max(S.gm_best_streak, S.gm_streak)
    S.gm_score += gm.points(correct, S.gm_streak - 1 if correct else 0)
    if not correct:
        S.gm_missed.append(target)
    record(target, correct, game)
    S.gm_ans = {"correct": correct, "chosen": value["chosen"]}
    persist()
    st.rerun()

if ans is not None:
    if ans["correct"]:
        st.markdown("✅ **Right!**")
    else:
        st.markdown("❌ It was:")
    html("<div style='display:flex;gap:16px;align-items:center'>"
         f"{img_tag(target['image'], 70)}<div>{word_html(target, '1.8rem')}"
         f"<div style='color:#78909c'>{target['english']}</div></div></div>")
    if game != "listen":
        play(target["chinese"])
    if st.button("Next ▶️", type="primary", width="stretch"):
        S.gm_i += 1
        S.pop("gm_ans", None)
        persist()
        st.rerun()
end_button()
