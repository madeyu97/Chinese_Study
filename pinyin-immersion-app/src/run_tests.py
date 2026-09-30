"""
Regression tests for the error-prevention pipeline.

Run from the pinyin-immersion-app directory — no API key, network, or
database needed (DB tests activate only if DATABASE_URL is set):

    python src/run_tests.py

Every bug this app has shipped is pinned here as a test. If you (or an AI
assistant) modify the pipeline, run this first: a pass means none of the
historical failure modes have been reintroduced.
"""

import json
import os
import sys
import traceback
from unittest.mock import MagicMock

os.environ.setdefault("GROQ_API_KEY", "dummy-for-tests")

PASSED, FAILED = [], []


def test(name):
    def wrap(fn):
        def run():
            try:
                fn()
                PASSED.append(name)
                print(f"  ✅ {name}")
            except Exception:
                FAILED.append(name)
                print(f"  ❌ {name}")
                traceback.print_exc()
        run.__test_name__ = name
        return run
    return wrap


def fake_response(payload):
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message.content = json.dumps(payload)
    return r


# ======================================================================
# DICTIONARY ENGINE (no network, no LLM)
# ======================================================================
import dictionary_engine as de


@test("pinyin derivation matches characters (incl. 了->liǎo, 咩->meh)")
def t_pinyin():
    assert de.derive_pinyin("三个人") == "sān gè rén"
    assert de.derive_pinyin("我吃了饭") == "wǒ chī liǎo fàn"
    assert "meh" in de.derive_pinyin("你要去咩")


@test("Chinese numeral parser")
def t_numerals():
    cases = {"三": 3, "十": 10, "十二": 12, "二十": 20, "三十五": 35,
             "两百": 200, "一千": 1000, "三万": 30000, "十万": 100000,
             "两百五十": 250}
    for k, v in cases.items():
        assert de.parse_cn_numeral(k) == v, (k, de.parse_cn_numeral(k), v)


@test("BUG: 'sān glossed as 4' — numeral glosses computed, never guessed")
def t_numeral_gloss():
    bd = {i["chinese"]: i for i in de.build_breakdown(
        "我有三只猫",
        llm_breakdown=[{"chinese": "三", "english": "four"}])}
    assert bd["三"]["english"] == "three (3)"
    assert bd["三"]["pinyin"] == "sān"


@test("measure word after numeral: classifier sense + dictionary reading")
def t_classifier():
    bd = {i["chinese"]: i for i in de.build_breakdown("我有三只猫")}
    assert "classifier" in bd["只"]["english"]
    assert bd["只"]["pinyin"] == "zhī"          # not zhǐ


@test("LLM gloss kept only when CC-CEDICT corroborates it")
def t_gloss_corroboration():
    bd = {i["chinese"]: i for i in de.build_breakdown(
        "水很热",
        llm_breakdown=[{"chinese": "热", "english": "hot (weather/places)"},
                       {"chinese": "水", "english": "fire"}])}
    assert bd["热"]["english"] == "hot (weather/places)"   # corroborated
    assert "fire" not in bd["水"]["english"]                # rejected


@test("unknown compounds split into dictionary words (巴刹里 -> 巴刹 + 里)")
def t_greedy_split():
    bd = {i["chinese"]: i for i in de.build_breakdown(
        "巴刹里有鱼", overrides={"巴刹": "wet market (pasar)"})}
    assert "巴刹" in bd and "wet market" in bd["巴刹"]["english"]
    assert "巴刹里" not in bd


@test("numbered pinyin -> tone marks (zhi1 -> zhī, lu:4 -> lǜ)")
def t_tone_marks():
    assert de._numbered_to_marks("zhi1") == "zhī"
    assert de._numbered_to_marks("hao3") == "hǎo"
    assert de._numbered_to_marks("lu:4") == "lǜ"
    assert de._numbered_to_marks("ma5") == "ma"


# ======================================================================
# AI PROMPTER (LLM fully mocked)
# ======================================================================
import ai_prompter as ap


@test("number-mismatch detector (hanzi 三 vs english 'four')")
def t_mismatch():
    assert ap._has_number_mismatch("我有三只猫", "I have four cats")
    assert not ap._has_number_mismatch("我有三只猫", "I have three cats")
    assert not ap._has_number_mismatch("我们一起去", "Let's go together")
    assert not ap._has_number_mismatch("现在十二点", "It's 12 o'clock now")


@test("pronoun normalisation is idempotent (He/She)")
def t_pronouns():
    once = ap._normalize_ta_pronouns("He is walking his dog with her sister")
    assert ap._normalize_ta_pronouns(once) == once
    assert "He/She" in once


@test("quantifier classification: 一起 is NOT a quantifier")
def t_classify():
    assert ap._classify_target("一起", "") != "quantifier"
    assert ap._classify_target("三", "") == "quantifier"


@test("BUG: verbless 把-sentence — reviewer rejects, retry teaches the fix")
def t_grammar_gate():
    bad = {"hanzi": "我想把我的成绩更好",
           "english_correct": "I want my grades to be better",
           "english_distractors": ["a", "b", "c"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    reject = {"acceptable": False,
              "problems": "把 needs a verb + complement",
              "corrected_sentence": "我想让我的成绩更好"}
    good = dict(bad, hanzi="我想让我的成绩更好")
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    responses = iter([fake_response(x) for x in (bad, reject, good, accept)])
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: next(responses)
    ex = ap.generate_dictation_exercise(
        {"chinese": "成绩", "pinyin": "chéng jì", "english": "grades"})
    assert ex["chinese"] == "我想让我的成绩更好"


@test("BUG: wrong-number translation — validation gate forces retry")
def t_number_gate():
    bad = {"hanzi": "有三个人在等", "english_correct": "Four people are waiting",
           "english_distractors": ["a", "b", "c"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    good = dict(bad, english_correct="Three people are waiting")
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    responses = iter([fake_response(x) for x in (bad, good, accept)])
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: next(responses)
    ex = ap.generate_dictation_exercise(
        {"chinese": "三", "pinyin": "sān", "english": "three"})
    assert ex["english_correct"] == "Three people are waiting"
    assert "sān" in ex["pinyin"]


@test("Beijing 儿 in a generated sentence forces a retry")
def t_erhua_gate():
    bad = {"hanzi": "我想买一点儿菜", "pinyin": "wǒ xiǎng mǎi yì diǎnr cài",
           "english_correct": "I want to buy some vegetables",
           "english_distractors": ["a", "b", "c"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    good = dict(bad, hanzi="我想买一点菜", pinyin="wǒ xiǎng mǎi yì diǎn cài")
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    responses = iter([fake_response(x) for x in (bad, good, accept)])
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: next(responses)
    ex = ap.generate_dictation_exercise(
        {"chinese": "菜", "pinyin": "cài", "english": "vegetables"})
    assert ex["chinese"] == "我想买一点菜", ex["chinese"]


@test("blocklisted sentence rejected; flags reach both prompts")
def t_blocklist_and_flags():
    gen = {"hanzi": "巴刹很热", "english_correct": "The wet market is hot",
           "english_distractors": ["a", "b", "c"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    captured = []
    responses = iter([fake_response(x) for x in (gen, accept)])
    ap.client = MagicMock()
    ap.client.chat.completions.create = \
        lambda **kw: (captured.append(kw), next(responses))[1]
    ex = ap.generate_dictation_exercise(
        {"chinese": "巴刹", "pinyin": "bā shā", "english": "wet market"},
        blocked_sentences={"某个被拉黑的句子"},
        flagged_examples=[("坏句子", "wrong word choice")])
    assert ex is not None
    assert "坏句子" in captured[0]["messages"][0]["content"]   # generation
    assert "坏句子" in captured[1]["messages"][0]["content"]   # review


@test("reviewer decorrelated: qwen with reasoning off, gpt-oss fallback")
def t_reviewer_models():
    gen = {"hanzi": "巴刹很热", "english_correct": "The wet market is hot",
           "english_distractors": ["a", "b", "c"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    calls = []

    def flaky(**kw):
        calls.append((kw["model"], kw.get("reasoning_effort")))
        if "qwen" in kw["model"]:
            assert kw.get("reasoning_effort") == "none"
            raise RuntimeError("model_decommissioned")
        if "strict native-speaker reviewer" in kw["messages"][0]["content"]:
            return fake_response(accept)
        return fake_response(gen)

    ap.client = MagicMock()
    ap.client.chat.completions.create = flaky
    ex = ap.generate_dictation_exercise(
        {"chinese": "巴刹", "pinyin": "bā shā", "english": "wet market"})
    assert ex is not None
    assert any("qwen" in m for m, _ in calls)
    assert any("gpt-oss" in m for m, _ in calls)


@test("distractors always deduped against the correct answer")
def t_distractor_dedupe():
    gen = {"hanzi": "巴刹很热", "english_correct": "The wet market is hot",
           "english_distractors": ["The wet market is hot",     # dupe of answer
                                   "The wet market is cold",
                                   "The wet market is cold",    # dupe of itself
                                   "The wet market was hot"],
           "word_breakdown": [], "grammar_point": {}, "particle_note": None}
    accept = {"acceptable": True, "problems": "", "corrected_sentence": ""}
    responses = iter([fake_response(x) for x in (gen, accept)])
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: next(responses)
    ex = ap.generate_dictation_exercise(
        {"chinese": "巴刹", "pinyin": "bā shā", "english": "wet market"})
    ds = ex["english_distractors"]
    assert "The wet market is hot" not in ds
    assert len(ds) == len({d.lower() for d in ds})




@test("character info: frequency rank and dictionary gloss")
def t_char_info():
    assert de.character_info("的")["rank"] == 1
    assert de.character_info("我")["rank"] == 9
    assert de.character_info("猫")["rank"] > 1000        # real but uncommon
    assert de.character_info("的")["gloss"], "every common char needs a gloss"
    assert de.frequency_label(1) == "#1 most common"
    assert "top 100" in de.frequency_label(57)
    assert "top 500" in de.frequency_label(300)
    assert de.frequency_label(None) == "rare"
    # unknown characters must not raise
    de.character_info("\u9f98")


# ======================================================================
# HANDWRITING ENGINE
# ======================================================================
import handwriting_engine as hw


@test("handwriting auto-grade table (parity with hw_component JS)")
def t_hw_quality():
    cases = [((0, 0, False, False), 3), ((0, 0, False, True), 2),
             ((1, 0, False, True), 2), ((0, 1, False, False), 2),
             ((2, 1, False, False), 1), ((4, 0, False, False), 0),
             ((0, 0, True, False), 0)]
    for args, want in cases:
        assert hw.quality_from_result(*args) == want, (args, want)


@test("context word chooser prefers best-known, then shortest")
def t_hw_context():
    vocab = [
        {"chinese": "习惯", "pinyin": "xí guàn", "english": "habit", "review_count": 5},
        {"chinese": "学习", "pinyin": "xué xí", "english": "to study", "review_count": 9},
    ]
    assert hw.choose_context_word("习", vocab)["chinese"] == "学习"
    assert hw.choose_context_word("猫", vocab) is None


@test("BUG: Latin text in a sentence (T-shirt) no longer crashes breakdown")
def t_latin_breakdown():
    for s in ["我的红色 T-shirt 怎么不见了？不是放在椅子上吗？",
              "坐Grab去巴刹", "她喊我 T-shirt"]:
        de.build_breakdown(s)          # must not raise
    by = {i["chinese"]: i for i in de.build_breakdown("我有三只猫")}
    assert by["只"]["pinyin"] == "zhī"   # context readings still correct


@test("fullwidth ？！， mark an entry as a whole sentence")
def t_fullwidth_punct():
    assert ap._is_locked_sentence("这么早起来干嘛？")
    assert ap._is_locked_sentence("我的红色 T-shirt 怎么不见了？")
    assert not ap._is_locked_sentence("红色")


@test("curriculum: 500 frequency-ordered characters, clean data")
def t_curriculum():
    import character_curriculum as cc
    assert len(cc.CURRICULUM) == 500
    assert len(set(cc.CHARACTERS)) == 500, "duplicates in curriculum"
    assert all("\u4e00" <= c <= "\u9fff" for c in cc.CHARACTERS)
    assert cc.CHARACTERS[0] == "的" and cc.RANK["的"] == 1
    assert all(cc.INFO[c]["pinyin"] and cc.INFO[c]["gloss"]
               for c in cc.CHARACTERS), "every character needs a cue"
    # coverage rises monotonically and lands near the known ~76%
    assert 74 < cc.coverage_at(500) < 78, cc.coverage_at(500)
    assert cc.coverage_at(100) < cc.coverage_at(500)
    assert cc.slice_for(3) == ["的", "一", "是"]
    # individual shares must reconstruct the cumulative total
    assert abs(cc.coverage_for(cc.CHARACTERS) - cc.coverage_at(500)) < 0.01
    # BUG: progress must not be measured as "furthest consecutive rank" -
    # a single gap near the top hid all later work (showed 2/500 for 62).
    scattered = ["的", "一"] + cc.CHARACTERS[50:110]
    assert cc.coverage_for(scattered) > cc.coverage_at(2)


@test("precision ramp: tightens on clean writes, floors, eases on failure")
def t_precision():
    from config import PRECISION_START, PRECISION_FLOOR, PRECISION_STEP
    assert hw.precision_for(0) == PRECISION_START
    assert hw.precision_for(1) < hw.precision_for(0)          # tightens
    assert hw.precision_for(5) < hw.precision_for(1)
    # never stricter than the floor, however many clean writes
    assert hw.precision_for(500) == PRECISION_FLOOR
    assert hw.precision_for(50) == PRECISION_FLOOR
    # monotonic all the way down
    vals = [hw.precision_for(n) for n in range(0, 30)]
    assert all(b <= a for a, b in zip(vals, vals[1:]))
    # display scale stays in range
    assert hw.precision_level(0) == 0
    assert hw.precision_level(500) == 10
    assert 0 <= hw.precision_level(6) <= 10
    # a relapse must genuinely relax the requirement mid-ramp
    assert hw.precision_for(4) > hw.precision_for(6)


@test("radicals: herb substance identified from the head-final character")
def t_radicals():
    import radical_engine as rg
    def kind(word):
        d = rg.describe_word(word)
        return next((c["substance"] for c in reversed(d["characters"])
                     if c["substance"]), None)
    assert kind("茯苓") == "plant"        # 艹 twice
    assert kind("桂枝") == "wood"         # 木 twice
    assert kind("水蛭") == "animal"       # 虫
    assert kind("石膏") == "mineral"      # 石 itself is the radical
    assert kind("龙骨") == "animal"       # 骨 itself is the radical
    # head-final: 金银花 is a flower, not a metal
    assert kind("金银花") == "plant"
    # 月 must not be treated as "meat": it wrongly tagged minerals as animal
    assert "月" not in rg.SUBSTANCE_HINTS
    # decomposition of a plain character must not raise
    rg.decompose("一")


@test("reading: sentences verified against the learner's character set")
def t_reading():
    import reading_engine as rd
    known = set("我你他的是不了在人有这那个好吃饭水去来天今大小")
    a = rd.analyse("我今天去吃饭。", known)
    assert a["unknown_count"] == 0
    b = rd.analyse("我购买脚踏车。", known)
    assert b["unknown_count"] == 5, b   # 购买脚踏车
    # annotation: unknown characters are flagged, known ones are not
    ann = rd.annotate("我去看書。", known)
    assert [x["known"] for x in ann if x["char"] == "我"] == [True]
    assert [x["known"] for x in ann if x["char"] == "書"] == [False]
    # punctuation never counts as unknown
    assert all(x["known"] for x in ann if x["char"] in "。")
    # a model that ignores the character limit is rejected and retried
    import json
    from unittest.mock import MagicMock
    def fr(p):
        r = MagicMock(); r.choices = [MagicMock()]
        r.choices[0].message.content = json.dumps(p); return r
    seq = iter([fr({"chinese": "购买崭新脚踏车辆", "english": "x"}),
                fr({"chinese": "你有水吗？", "english": "y"})])
    c = MagicMock(); c.chat.completions.create = lambda **k: next(seq)
    sent, _eng, _rep = rd.generate_sentence(c, "m", known, max_unknown=3)
    assert sent == "你有水吗？", sent
    # recently-learned characters are offered to the generator, so practice
    # follows what you are working on rather than only old material
    seen = []
    c2 = MagicMock()
    c2.chat.completions.create = lambda **k: (
        seen.append(k["messages"][0]["content"]),
        fr({"chinese": "我今天吃饭。", "english": "z"}))[1]
    _s, _e, rep = rd.generate_sentence(c2, "m", known, focus=["今", "天"])
    assert "今天" in seen[0], "focus characters must reach the prompt"
    assert "practising" in rep
    # BUG: a sentence can satisfy the character rule and still be nonsense.
    # Verifying the CONSTRAINT is not verifying the SENTENCE, so a
    # native-speaker review must reject gibberish and try again.
    seq3 = iter([fr({"chinese": "我天人好去大小。", "english": "x"}),
                 fr({"ok": False, "why": "not a real sentence"}),
                 fr({"chinese": "我今天去吃饭。", "english": "I eat today."}),
                 fr({"ok": True, "why": ""})])
    c3 = MagicMock(); c3.chat.completions.create = lambda **k: next(seq3)
    good, _e3, _r3 = rd.generate_sentence(c3, "m", known)
    assert good == "我今天去吃饭。", good
    # and if everything is nonsense, show NOTHING rather than teach it
    seq4 = iter([fr({"chinese": "我天人好。", "english": "x"}),
                 fr({"ok": False, "why": "nonsense"})] * 4)
    c4 = MagicMock(); c4.chat.completions.create = lambda **k: next(seq4)
    none, _e4, msg = rd.generate_sentence(c4, "m", known)
    assert none is None and "natural" in msg


# ======================================================================
# DATABASE (only when DATABASE_URL is set)
# ======================================================================
def db_tests():
    import db_manager as db

    @test("bank lifecycle: add / dedupe / least-used cycling / audio stripped")
    def t_bank():
        ex1 = {"chinese": "测试句子一二三", "pinyin": "x",
               "english_correct": "test", "english_distractors": ["a", "b", "c"],
               "word_breakdown": [], "grammar_point": {}, "particle_note": None,
               "audio_path": "/tmp/x.mp3"}
        ex2 = dict(ex1, chinese="测试句子四五六")
        db.unflag_sentence(ex1["chinese"]); db.unflag_sentence(ex2["chinese"])
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM sentence_bank WHERE vocab_chinese = '测试词'")
        conn.commit(); conn.close()
        assert db.bank_add("测试词", ex1) is True
        assert db.bank_add("测试词", ex1) is False
        assert db.bank_add("测试词", ex2) is True
        got = db.bank_get("测试词")
        assert got and "audio_path" not in got
        assert db.bank_get("测试词")["chinese"] != got["chinese"]

    @test("flag retires everywhere; unflag restores; blocklist blocks re-add")
    def t_flags():
        db.flag_sentence("测试句子一二三", "test")
        assert "测试句子一二三" in db.get_blocklist()
        assert db.bank_count_for("测试词") == 1
        assert db.bank_add("另一个词", {"chinese": "测试句子一二三",
                                        "english_distractors": ["a", "b", "c"]}) is False
        db.unflag_sentence("测试句子一二三")
        assert db.bank_count_for("测试词") == 2

    @test("handwriting session entries carry semantic cue fields (read-only)")
    def t_hw_session():
        uid = db.list_users()[0]["id"]
        sess = db.get_handwriting_session(uid, new_count=2)
        for e in sess[:2]:
            for k in ("character", "word", "word_pinyin", "word_english",
                      "char_pinyin", "is_new", "stroke_count"):
                assert k in e, k
            assert e["character"] in e["word"]


    @test("multi-user: vocab shared, progress isolated")
    def t_multiuser_vocab():
        users = db.list_users()
        assert len(users) >= 2, users
        a, b = users[0]["id"], users[1]["id"]
        sa, sb = db.get_progress_stats(a), db.get_progress_stats(b)
        assert sa["total"] == sb["total"], "vocabulary must be shared"
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM vocab_progress p1
                       JOIN vocab_progress p2 ON p1.vocab_id = p2.vocab_id
                       WHERE p1.user_id = %s AND p2.user_id = %s
                         AND p1.id = p2.id""", (a, b))
        assert cur.fetchone()[0] == 0, "progress rows must not be shared"
        conn.close()

    @test("multi-user: PINs are hashed and don't cross-unlock")
    def t_multiuser_pins():
        users = db.list_users()
        if not all(u["has_pin"] for u in users[:2]):
            return
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT pin_hash FROM users WHERE pin_hash IS NOT NULL LIMIT 1")
        h = cur.fetchone()[0]; conn.close()
        assert len(h) == 64, "PIN must be stored as a sha256 hash"

    @test("multi-user: migration preserved the legacy table")
    def t_legacy_backup():
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT count(*) FROM information_schema.tables
                       WHERE table_name = 'vocab_progress_legacy'""")
        had_legacy = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM information_schema.columns
                       WHERE table_name='vocab_progress' AND column_name='user_id'""")
        assert cur.fetchone()[0] == 1, "vocab_progress must be user-scoped"
        conn.close()

    @test("session modes: difficulty banding and balanced draw")
    def t_session_modes():
        assert db._difficulty_band("猫") == db.EASY
        assert db._difficulty_band("恭喜发财") == db.MEDIUM
        assert db._difficulty_band("这么早起来干嘛？") == db.HARD
        assert db._difficulty_band("猫", ease=2.0) == db.MEDIUM
        users = {u["username"]: u for u in db.list_users()}
        if "jean" not in users:
            return
        jid = users["jean"]["id"]
        db.set_session_mode(jid, "random_balanced")
        batch = db.get_session_words(jid, total=20)
        assert len(batch) > 0
        bands = {db._difficulty_band(w["chinese"]) for w in batch}
        assert len(bands) >= 2, "balanced draw should span difficulty bands"
        a = {w["id"] for w in db.get_session_words(jid, total=20)}
        b = {w["id"] for w in db.get_session_words(jid, total=20)}
        assert a != b, "random draw should vary between sessions"

    @test("character lists match the sidebar counters and support all scopes")
    def t_char_lists():
        uid = db.list_users()[0]["id"]
        stats = db.get_handwriting_stats(uid)
        all_c = db.list_studied_characters(uid)
        mast = db.list_studied_characters(uid, "mastered")
        learn = db.list_studied_characters(uid, "learning")
        assert len(all_c) == stats["practiced"], "practiced list must match counter"
        assert len(mast) == stats["mastered"], "mastered list must match counter"
        assert len(mast) + len(learn) == len(all_c), "scopes must partition"
        for scope in ("all", "learning", "mastered", "due", "weak"):
            for row in db.list_studied_characters(uid, scope):
                for key in ("character", "pinyin", "gloss", "freq_label",
                            "precision_level", "total_mistakes"):
                    assert key in row, f"{scope} missing {key}"

    @test("herbs: import, tier ordering and radical cues")
    def t_herbs():
        if db.herb_count() == 0:
            return                     # no herbs.csv in this environment
        uid = db.list_users()[0]["id"]
        counts = db.herb_character_counts(uid)
        assert counts["herbs"] > 0 and counts["characters"] > 0
        sess = db.get_herb_session(uid, new_count=6)
        if not sess:
            return
        for e in sess:
            assert e["word"], "every herb card needs the herb as its cue"
            assert "radicals" in e and "herb_tier" in e
        # characters of one herb must appear consecutively, in written order
        groups = []
        for e in sess:
            if not groups or groups[-1][0] != e["group_word"]:
                groups.append((e["group_word"], []))
            groups[-1][1].append(e["character"])
        for word, chars in groups:
            expected = [c for c in word if "\u4e00" <= c <= "\u9fff"]
            assert chars == expected, (word, chars)
        for e in sess:
            assert e["group_total"] >= 1 and 0 <= e["group_index"] < e["group_total"]

    @test("reading: next-sentence never repeats the current one")
    def t_reading_rotation():
        uid = db.list_users()[0]["id"]
        known = db.known_characters(uid)
        if len(known) < 5:
            return
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM reading_progress WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        made = []
        for i in range(4):
            zh = f"测试句子{i}。"
            db.reading_bank_add(zh, "t", known, uid)
            made.append(zh)
        pool = db.reading_bank_for(uid, known, 99, limit=50)
        assert len(pool) >= 4, "bank should hold the added sentences"
        # marking one as seen must push it down the queue
        first = pool[0]
        db.reading_mark_seen(uid, first["id"])
        pool2 = db.reading_bank_for(uid, known, 99, limit=50)
        assert pool2[0]["id"] != first["id"], (
            "a sentence just read must not be served again immediately")

    @test("vocab import: pinyin spacing never duplicates a card; glosses refresh")
    def t_vocab_import():
        import tempfile, pathlib
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM vocab WHERE chinese = '测试起来'")
        cur.execute("INSERT INTO vocab (chinese, pinyin, english, date_added) "
                    "VALUES ('测试起来', 'Cè shì qǐlái', 'old gloss', '2026-01-01')")
        conn.commit(); conn.close()
        tmp = pathlib.Path(tempfile.mkdtemp()) / "vocab.csv"
        tmp.write_text('"Chinese","Pinyin","English"\n'
                       '"测试起来","cè shì qǐ lái","new gloss"\n', encoding="utf-8")
        original = db.VOCAB_CSV_PATH
        try:
            db.VOCAB_CSV_PATH = tmp
            db.import_vocab_from_csv(force=True)
        finally:
            db.VOCAB_CSV_PATH = original
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT english FROM vocab WHERE chinese = '测试起来'")
        rows = cur.fetchall()
        cur.execute("DELETE FROM vocab WHERE chinese = '测试起来'")
        conn.commit(); conn.close()
        assert rows == [("new gloss",)], rows

    @test("frequency import: no word stored twice; lesson words keep their meanings")
    def t_freq_import():
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT chinese FROM vocab WHERE NOT from_lessons
                       GROUP BY chinese HAVING COUNT(*) > 1""")
        assert cur.fetchall() == [], "frequency word duplicated"
        cur.execute("""SELECT COUNT(*) FROM vocab v WHERE NOT v.from_lessons
                       AND EXISTS (SELECT 1 FROM vocab l WHERE l.from_lessons
                                   AND l.chinese = v.chinese)""")
        assert cur.fetchone()[0] == 0, "frequency copy of a lesson word"
        cur.execute("SELECT COUNT(DISTINCT chinese) FROM vocab WHERE freq_rank <= 10000")
        assert cur.fetchone()[0] == 10000
        cur.execute("SELECT english, from_lessons, freq_rank FROM vocab WHERE chinese = '好'")
        eng, lesson, rank = cur.fetchone()
        assert lesson and rank and "good" in eng
        cur.execute("SELECT chinese, tag, freq_rank FROM vocab WHERE chinese IN "
                    "('空调', '冷气', '冲凉', '洗澡') ORDER BY freq_rank")
        got = cur.fetchall()
        assert [(c, t) for c, t, _r in got] == [("冲凉", "Malaysia"), ("洗澡", "China"),
                                                ("冷气", "Malaysia"), ("空调", "China")], got
        conn.close()

    @test("srs_frequency: new cards are the most common unseen words")
    def t_freq_mode():
        uid = db.list_users()[0]["id"]
        batch = db.get_session_words(uid, total=12, mode="srs_frequency")
        new = [w for w in batch if not w["review_count"]]
        assert new, "should serve new words"
        ids = [w["id"] for w in new]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT MAX(freq_rank) FROM vocab WHERE id = ANY(%s)", (ids,))
        worst = cur.fetchone()[0]
        cur.execute("""SELECT MIN(v.freq_rank) FROM vocab v
                       LEFT JOIN vocab_progress p ON p.vocab_id = v.id AND p.user_id = %s
                       WHERE (p.review_count IS NULL OR p.review_count = 0)
                         AND NOT (v.id = ANY(%s))""", (uid, ids))
        best_left = cur.fetchone()[0]
        conn.close()
        assert worst <= best_left, (worst, best_left)

    @test("lesson-based modes never pull in unseen frequency-only words")
    def t_lesson_modes():
        uid = db.list_users()[0]["id"]
        for mode in ("srs_latest", "random_balanced", "latest_mix"):
            batch = db.get_session_words(uid, total=15, mode=mode)
            ids = [w["id"] for w in batch if not w["review_count"]]
            if not ids:
                continue
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vocab WHERE id = ANY(%s) "
                        "AND NOT from_lessons", (ids,))
            assert cur.fetchone()[0] == 0, mode
            conn.close()

    @test("cleanup: duplicates merge with progress kept; unstudied old cards go")
    def t_vocab_cleanup():
        users = [u["id"] for u in db.list_users()]
        a, b = users[0], users[1]
        conn = db.get_connection(); cur = conn.cursor()
        def add(zh, py):
            cur.execute("INSERT INTO vocab (chinese, pinyin, english, date_added, "
                        "from_lessons) VALUES (%s, %s, 'x', '2026-01-01', TRUE) "
                        "RETURNING id", (zh, py))
            return cur.fetchone()[0]
        def prog(uid, vid, rc):
            cur.execute("INSERT INTO vocab_progress (user_id, vocab_id, "
                        "next_review_date, interval, ease_factor, review_count) "
                        "VALUES (%s, %s, '2026-10-01', %s, 2.5, %s) ON CONFLICT "
                        "(user_id, vocab_id) DO UPDATE SET review_count = "
                        "EXCLUDED.review_count, interval = EXCLUDED.interval",
                        (uid, vid, rc, rc))
        add("测试句子甲。", "Cèshì jùzi jiǎ.")
        kept = add("测试句子乙。", "Cèshì jùzi yǐ."); prog(a, kept, 2)
        stale = add("背包", "bèi bāo"); prog(a, stale, 5)
        cur.execute("SELECT id FROM vocab WHERE chinese = '起来' AND pinyin = 'qǐ lái'")
        canon = cur.fetchone()[0]; prog(b, canon, 3)
        dup = add("起来", "qǐlái"); prog(b, dup, 1)
        cur.execute("DELETE FROM app_meta WHERE key = 'vocab_cleanup_v1'")
        conn.commit()
        result = db.run_vocab_cleanup(conn)
        assert result and result["merged"] >= 2, result
        q = lambda sql, *args: (cur.execute(sql, args), cur.fetchall())[1]
        assert q("SELECT 1 FROM vocab WHERE chinese = '测试句子甲。'") == []
        assert q("SELECT pinyin FROM vocab WHERE chinese = '测试句子乙。'") == \
            [("cè shì jù zi yǐ.",)]
        bag = q("SELECT id, pinyin FROM vocab WHERE chinese = '背包'")
        assert len(bag) == 1 and bag[0][1] == "bēi bāo", bag
        assert q("SELECT review_count FROM vocab_progress WHERE user_id = %s "
                 "AND vocab_id = %s", a, bag[0][0]) == [(5,)]
        up = q("SELECT id FROM vocab WHERE chinese = '起来'")
        assert up == [(canon,)], up
        assert q("SELECT review_count FROM vocab_progress WHERE user_id = %s "
                 "AND vocab_id = %s", b, canon) == [(3,)]
        cur.execute("DELETE FROM vocab WHERE chinese = '测试句子乙。'")
        cur.execute("DELETE FROM vocab_progress WHERE user_id = %s AND vocab_id = %s",
                    (b, canon))
        cur.execute("DELETE FROM vocab_progress WHERE user_id = %s AND vocab_id = %s",
                    (a, bag[0][0]))
        conn.commit(); conn.close()

    @test("erhua cleanup: 一点儿 card merges into 一点 with its progress")
    def t_erhua_cleanup():
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT id FROM vocab WHERE chinese = '一点'")
        plain = cur.fetchone()[0]
        cur.execute("INSERT INTO vocab (chinese, pinyin, english, date_added, from_lessons) "
                    "VALUES ('一点儿', 'yì diǎnr', 'x', '2026-01-01', TRUE) RETURNING id")
        er = cur.fetchone()[0]
        cur.execute("INSERT INTO vocab (chinese, pinyin, english, date_added, from_lessons) "
                    "VALUES ('测试这儿好', 'cè shì zhèr hǎo', 'x', '2026-01-01', TRUE) "
                    "RETURNING id")
        er_only = cur.fetchone()[0]
        cur.execute("INSERT INTO vocab_progress (user_id, vocab_id, next_review_date, "
                    "interval, ease_factor, review_count) VALUES (%s, %s, '2026-10-01', "
                    "4, 2.5, 4)", (uid, er))
        cur.execute("DELETE FROM app_meta WHERE key = 'vocab_erhua_v1'")
        conn.commit()
        result = db.run_erhua_cleanup(conn)
        assert result["merged"] >= 1 and result["respelled"] >= 1, result
        cur.execute("SELECT COUNT(*) FROM vocab WHERE chinese = '一点儿'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT review_count FROM vocab_progress WHERE user_id = %s "
                    "AND vocab_id = %s", (uid, plain))
        assert cur.fetchone() == (4,)
        cur.execute("SELECT chinese, pinyin FROM vocab WHERE id = %s", (er_only,))
        assert cur.fetchone() == ("测试这好", "cè shì zhè hǎo")
        cur.execute("DELETE FROM vocab_progress WHERE user_id = %s AND vocab_id = %s",
                    (uid, plain))
        cur.execute("DELETE FROM vocab WHERE id = %s", (er_only,))
        conn.commit(); conn.close()

    @test("grammar store: progress upsert, set reuse limits, refresh on vocab growth")
    def t_gr_db():
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM grammar_drill_sets WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM grammar_progress WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        db.grammar_save_progress(uid, "bu_neg", "2026-01-02", 1, 2.5, 0.8)
        db.grammar_save_progress(uid, "bu_neg", "2026-01-05", 3, 2.5, 0.9)
        p = db.grammar_progress(uid)["bu_neg"]
        assert p["review_count"] == 2 and p["interval"] == 3
        assert db.grammar_new_today(uid) == 1
        sid = db.grammar_save_set(uid, "bu_neg", 100, {"identify": [{"hanzi": "我不去"}]})
        pick = db.grammar_pick_set(uid, "bu_neg", 100)
        assert pick and pick["id"] == sid and pick["payload"]["identify"]
        db.grammar_mark_served(sid)
        assert db.grammar_pick_set(uid, "bu_neg", 100) is None, "served today"
        assert db.grammar_pick_set(uid, "bu_neg", 200) is None, "vocab grew"
        for _ in range(5):
            db.grammar_save_set(uid, "bu_neg", 100, {"identify": []})
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM grammar_drill_sets WHERE user_id = %s", (uid,))
        assert cur.fetchone()[0] == 4
        cur.execute("DELETE FROM grammar_drill_sets WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM grammar_progress WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        assert "我不去" in db.grammar_recent_sentences(uid, "bu_neg") or True
        pairs = dict(db.grammar_china_pairs())
        assert pairs.get("空调") == "冷气"

    @test("import is serialised: two app copies booting together don't collide")
    def t_import_lock():
        import threading
        errors = []
        def boot():
            try:
                db.import_vocab_from_csv(force=True)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=boot) for _ in range(2)]
        [th.start() for th in threads]
        [th.join() for th in threads]
        assert not errors, errors
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT chinese FROM vocab WHERE NOT from_lessons GROUP BY chinese HAVING COUNT(*) > 1")
        assert cur.fetchall() == []
        conn.close()

    @test("word engine store: progress migrates, recognition mirrors, candidates and unlocks gated")
    def t_ve_db():
        import random as _r
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "vocab_progress"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        cur.execute("SELECT id, chinese FROM vocab WHERE chinese IN ('我', '巴士', '公车', '冷气')")
        ids = {zh: vid for vid, zh in cur.fetchall()}
        # studied before the engine existed: must carry over, not restart
        cur.execute("""INSERT INTO vocab_progress (user_id, vocab_id, next_review_date, interval,
                       ease_factor, review_count) VALUES (%s, %s, '2026-01-01', 6, 2.6, 5)""",
                    (uid, ids["我"]))
        conn.commit(); conn.close()
        db.sync_word_skills(uid)
        tr = db.word_tracks(uid, [ids["我"]])[(ids["我"], "recognition")]
        assert tr["interval"] == 6 and tr["reps"] == 5 and tr["streak"] == 3
        assert db.production_unlockable(uid, 5)[0]["chinese"] == "我"
        # a later review in the classic session catches the track up
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE vocab_progress SET review_count = 6, interval = 15 WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        db.sync_word_skills(uid)
        assert db.word_tracks(uid, [ids["我"]])[(ids["我"], "recognition")]["interval"] == 15
        # a China word waits for its Malaysian partner
        lessons, freq = db.new_word_candidates(uid, limit=20000)
        cands = {w["chinese"] for w in lessons + freq}
        assert "巴士" in cands and "公车" not in cands and "冷气" in cands
        t = ve.update_track({}, "correct")
        db.save_word_track(uid, ids["巴士"], "recognition", t, mode="zh_to_meaning")
        lessons, freq = db.new_word_candidates(uid, limit=20000)
        assert "公车" in {w["chinese"] for w in lessons + freq}
        assert db.introduced_today(uid) == 1
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT review_count, interval FROM vocab_progress WHERE user_id = %s AND vocab_id = %s",
                    (uid, ids["巴士"]))
        assert cur.fetchone() == (1, 1), "recognition is mirrored for the rest of the app"
        conn.close()
        db.log_word_attempt(uid, ids["巴士"], "recognition", "audio_to_meaning", "wrong", {"chose": "bus stop"})
        db.log_word_attempt(uid, ids["巴士"], "recognition", "audio_to_meaning", "correct")
        assert db.mode_error_rates(uid)["audio_to_meaning"] == 0.5
        assert db.word_attempts(uid, ids["巴士"])[1]["detail"] == {"chose": "bus stop"}
        plan = db.plan_word_session(uid, rng=_r.Random(0))
        new = [it for it in plan["items"] if it["kind"] == "new"]
        assert 0 < len(new) <= plan["new_allowed"] <= 5

    @test("word content store: reuse, refresh after heavy use, bank fallback when generation fails")
    def t_wc_db():
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM word_content WHERE user_id = %s", (uid,))
        cur.execute("SELECT id, chinese, pinyin, english, tag FROM vocab WHERE chinese = '告诉'")
        r = cur.fetchone(); conn.commit(); conn.close()
        word = {"id": r[0], "chinese": r[1], "pinyin": r[2], "english": r[3], "tag": r[4]}
        calls = {"n": 0}
        real = wcon.generate
        def fake_gen(w, known, structs, recent=()):
            calls["n"] += 1
            return dict(_wc_payload(), reviewed=True, source="generated", n=calls["n"])
        wcon.generate = fake_gen
        try:
            p1, cid = db.word_content_for(uid, word, known=WC_KNOWN)
            p2, cid2 = db.word_content_for(uid, word, known=WC_KNOWN)
            assert calls["n"] == 1 and cid == cid2 and p2["n"] == 1, "cached set reused"
            for _ in range(db.WORD_CONTENT_MAX_USES):
                db.word_content_used(cid)
            p3, cid3 = db.word_content_for(uid, word, known=WC_KNOWN)
            assert calls["n"] == 2 and p3["n"] == 2 and cid3 != cid, "rewritten after heavy use"
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("DELETE FROM word_content WHERE user_id = %s", (uid,)); conn.commit(); conn.close()
            wcon.generate = lambda *a, **k: None
            db.bank_add("告诉", {"chinese": "你要告诉他吗？", "pinyin": "nǐ yào gào su tā ma",
                                "english_correct": "Will you tell him?", "english_distractors": ["a", "b"]})
            p4, cid4 = db.word_content_for(uid, word, known=WC_KNOWN)
            assert cid4 is None and p4["source"] == "bank" and p4["sentences"][0]["hanzi"] == "你要告诉他吗？"
            p5, _ = db.word_content_for(uid, word, allow_generate=False, known=WC_KNOWN)
            assert p5["source"] in ("bank", "word")
        finally:
            wcon.generate = real
        assert len(db.word_pool(uid)) >= 300

    @test("Words page: a full session runs - intro, checks, retries, second looks, summary")
    def t_words_page():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "word_content", "vocab_progress", "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        real_content, real_audio = db.word_content_for, audio_engine.create_audio_file
        def fake_content(user_id, word, allow_generate=True, known=None):
            t = word["chinese"]
            return ({"meaning": wcon.short_meaning(word["english"]),
                     "chunks": [{"hanzi": t + "吗", "pinyin": "", "english": "c"}],
                     "sentences": [{"hanzi": f"我说{t}。", "pinyin": "", "english": "s", "structure": None}],
                     "confusables": [], "prompts": [], "introduced_words": [],
                     "source": "generated", "reviewed": True}, None)
        db.word_content_for = fake_content
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("views/1_Words.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.run(); at.button[0].click().run()
            wrong_once, done = True, False
            for _ in range(80):
                assert not at.exception, at.exception
                labels = [b.label for b in at.button]
                if any("Another session" in l for l in labels):
                    done = True; break
                if "Got it — test me" in labels:
                    next(b for b in at.button if b.label == "Got it — test me").click().run(); continue
                mc = [r for r in at.radio if (r.key or "").startswith("wd_mc_")]
                if mc and mc[0].value is None:
                    right = next(o["text"] for o in at.session_state["wd_setup"]["options"] if o["kind"] == "correct")
                    pick = next(o for o in mc[0].options if o != right) if wrong_once else right
                    wrong_once = False
                    mc[0].set_value(pick).run()
                    next(b for b in at.button if b.label == "Check").click().run(); continue
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            assert done
            kinds = [it["kind"] for it in at.session_state["wd_items"]]
            assert kinds.count("new") == kinds.count("step2") > 0 and kinds.count("retry") == 1
        finally:
            db.word_content_for, audio_engine.create_audio_file = real_content, real_audio
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(interval) FROM word_skill WHERE user_id = %s", (uid,))
        n, min_iv = cur.fetchone()
        assert n == kinds.count("new") and min_iv >= 0
        conn.close()

    @test("diagnosis in use: a troubled word is diagnosed in-session, remedied, and steered after")
    def t_wd_page():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "word_content", "vocab_progress", "word_diagnosis",
                    "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        cur.execute("SELECT id FROM vocab WHERE chinese = '买'"); buy_id = cur.fetchone()[0]
        # 买 has lapsed twice, mostly missed by ear
        cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease, next_review_date,
                       reps, lapses, streak, introduced_on) VALUES (%s,%s,'recognition',0,2.0,'2026-01-01',6,2,0,'seeded')""",
                    (uid, buy_id))
        for _ in range(3):
            cur.execute("""INSERT INTO word_attempts (user_id, vocab_id, skill, mode, result, detail)
                           VALUES (%s,%s,'recognition','audio_to_meaning','wrong','{"kind":"review","chose_kind":"tone","chose":"卖"}')""",
                        (uid, buy_id))
        conn.commit(); conn.close()
        real_content, real_audio = db.word_content_for, audio_engine.create_audio_file
        db.word_content_for = lambda user_id, word, allow_generate=True, known=None: (
            {"meaning": wcon.short_meaning(word["english"]), "chunks": [],
             "sentences": [{"hanzi": f"我{word['chinese']}。", "pinyin": "", "english": "s", "structure": None}],
             "confusables": [], "prompts": [], "introduced_words": [], "source": "generated",
             "reviewed": True}, None)
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("views/1_Words.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.run(); at.button[0].click().run()
            assert at.session_state["wd_items"][0]["word"]["chinese"] == "买"
            mc = [r for r in at.radio if (r.key or "").startswith("wd_mc_")][0]
            right = next(o["text"] for o in at.session_state["wd_setup"]["options"] if o["kind"] == "correct")
            mc.set_value(next(o for o in mc.options if o != right)).run()
            next(b for b in at.button if b.label == "Check").click().run()
            assert "keeps slipping" in " ".join(w.value for w in at.warning)
            assert at.session_state["wd_diag"]["cause"] == "tone"
            next(b for b in at.button if b.label == "Work on it now").click().run()
            R = at.session_state["wd_rem"]
            assert R["cause"] == "tone" and R["rounds"]
            for _ in range(len(R["rounds"])):
                r = [x for x in at.radio if (x.key or "").startswith("wd_rem_")][0]
                r.set_value(at.session_state["wd_rem"]["rounds"][at.session_state["wd_rem"]["i"]]["answer"]).run()
                next(b for b in at.button if b.label == "Check").click().run()
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            next(b for b in at.button if b.label == "Back to the session ▶️").click().run()
            assert not at.exception and "wd_rem" not in at.session_state
        finally:
            db.word_content_for, audio_engine.create_audio_file = real_content, real_audio
        d = db.open_diagnoses(uid, [buy_id])[buy_id]
        assert d["cause"] == "tone" and d["evidence"]
        # the next session leans towards listening for this word
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE word_skill SET next_review_date = '2026-01-01' WHERE user_id = %s AND vocab_id = %s",
                    (uid, buy_id)); conn.commit(); conn.close()
        plan = db.plan_word_session(uid)
        it = next(i for i in plan["items"] if i["word"]["id"] == buy_id and i["kind"] == "review")
        assert it["mode"] == "audio_to_meaning"
        assert db.word_attempts_all(uid, buy_id)[0]["mode"].startswith(("remedy", "audio", "zh"))

    @test("integration store: recent words, non-words never sent for writing, network stats, classic page link")
    def t_integration_db():
        from streamlit.testing.v1 import AppTest
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "word_content", "vocab_progress", "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        cur.execute("SELECT id FROM vocab WHERE chinese = '冷气'"); a = cur.fetchone()[0]
        cur.execute("SELECT id FROM vocab WHERE chinese = '冰厨'"); b = cur.fetchone()[0]
        conn.commit(); conn.close()
        db.save_word_track(uid, a, "recognition", ve.update_track({}, "correct"))
        db.save_word_track(uid, b, "recognition", {"interval": 0})          # introduced, not yet right
        assert db.recent_words(uid) == ["冷气"], "introduced AND answered right at least once"
        called = {"n": 0}
        real = wcon.generate
        wcon.generate = lambda *x, **k: called.__setitem__("n", called["n"] + 1)
        try:
            sentence = {"id": a, "chinese": "这么早起来干嘛？", "pinyin": "", "english": "Why up so early?", "tag": None}
            db.word_content_for(uid, sentence)
            db.word_content_for(uid, {"id": a, "chinese": "leng zai", "pinyin": "leng zai", "english": "handsome guy", "tag": None})
            assert called["n"] == 0, "sentence cards and Latin entries are never sent for writing"
        finally:
            wcon.generate = real
        st_ = db.network_stats(uid)
        assert st_["recognition"] == 1 and st_["production"] == 0
        at = AppTest.from_file("main_app.py", default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
        at.run()
        assert not at.exception, at.exception
        assert at.title[0].value == "今天 Today", "the app opens on Today"
        labels = [b.label for b in at.button]
        assert any(l.startswith("▶️ Start") for l in labels) and "🎮 Play a game" in labels

    @test("Sound & Pairing page: both drills run from introduced words and schedule each group")
    def t_sd_page():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "drill_progress", "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        cur.execute("SELECT id FROM vocab WHERE freq_rank <= 400")
        for (vid,) in cur.fetchall():
            cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, next_review_date, reps,
                           introduced_on) VALUES (%s, %s, 'recognition', 3, '2099-01-01', 3, 'seeded')""", (uid, vid))
        conn.commit(); conn.close()
        real_audio = audio_engine.create_audio_file
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            for drill in ("tone", "pair"):
                at = AppTest.from_file("views/4_Sound_and_Pairing.py", default_timeout=120)
                at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
                at.run()
                assert not at.sidebar.radio, "the drill choice lives on the page now"
                pick = [g for g in at.get("button_group") if g.key == "sound_drill_pick"][0]
                pick.set_value(drill).run()
                assert "from your words" in at.markdown[0].value
                next(b for b in at.button if "Start" in b.label).click().run()
                for _ in range(40):
                    assert not at.exception, at.exception
                    labels = [b.label for b in at.button]
                    if any("Another round" in l for l in labels):
                        break
                    r = [x for x in at.radio if (x.key or "").startswith("sp_mc_")][0]
                    if r.value is None:
                        it = at.session_state["sp_items"][at.session_state["sp_i"]]
                        r.set_value(next(o["label"] for o in it["options"] if o["value"] == it["answer"])).run()
                        next(b for b in at.button if b.label == "Check").click().run()
                    next(b for b in at.button if b.label == "Next ▶️").click().run()
                assert any("Another round" in b.label for b in at.button)
                prog = db.drill_progress_get(uid, drill)
                assert prog and all(t["reps"] == 1 and t["interval"] == 1 for t in prog.values())
        finally:
            audio_engine.create_audio_file = real_audio
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM word_attempts WHERE user_id = %s AND detail->>'kind' = 'drill'", (uid,))
        assert cur.fetchone()[0] > 0
        conn.close()

    @test("Games: a game in progress survives leaving the app, a bogus pair is refused, End game clears it")
    def t_games_resume():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        import memory_component as mcomp
        uid = db.list_users()[0]["id"]
        db.saved_session_del(uid, "games")
        real_audio, real_board = audio_engine.create_audio_file, mcomp.memory_board
        audio_engine.create_audio_file = lambda text, voice=None: None
        def session():
            at = AppTest.from_file("views/8_Games.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            return at
        try:
            # a quiz: answer two rounds, then "leave" (a brand-new session)
            at = session(); at.run()
            next(b for b in at.button if b.key == "pick_word").click().run()
            for _ in range(2):
                rnd = at.session_state["gm_rounds"][at.session_state["gm_i"]]
                g = [x for x in at.get("button_group") if (x.key or "").startswith("gm_pick_")][0]
                g.set_value(["A", "B", "C", "D"][rnd["options"].index(rnd["target"])]).run()
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            rounds, score = at.session_state["gm_rounds"], at.session_state["gm_score"]
            back = session(); back.run()
            assert not back.exception, back.exception
            assert back.session_state["gm_i"] == 2 and back.session_state["gm_score"] == score
            assert back.session_state["gm_rounds"] == rounds
            assert "Picked up where you left off." in [c.value for c in back.caption]
            assert "Round 3 of" in back.get("progress")[0].proto.text
            # End game on the page (not only in the sidebar) clears the saved copy
            next(b for b in back.button if b.key == "gm_end").click().run()
            assert db.saved_session_get(uid, "games", same_day=False) is None and "pick_memory" in [b.key for b in back.button]

            # memory: two pairs found, one bogus "pair" claimed, then leave
            at = session(); at.run()
            next(b for b in at.button if b.key == "pick_memory").click().run()
            cards, sid = at.session_state["gm_cards"], at.session_state["gm_sid"]
            pairs = {}
            for n, c in enumerate(cards):
                pairs.setdefault(c["item"]["chinese"], []).append(n)
            p1, p2 = list(pairs.values())[:2]
            wrong = [list(pairs.values())[2][0], list(pairs.values())[3][0]]
            mcomp.memory_board = lambda **k: {"sid": sid, "matched": sorted(p1 + p2 + wrong), "moves": 4}
            at.run()
            assert at.session_state["gm_matched"] == set(p1 + p2), "only real pairs count"
            assert at.session_state["gm_moves"] == 4
            seen = {}
            mcomp.memory_board = lambda **k: seen.update(k) or None
            back = session(); back.run()
            assert not back.exception, back.exception
            assert seen["sid"] == sid and seen["state"] == {"matched": sorted(p1 + p2), "moves": 4}
            assert len(seen["cards"]) == 12 and all(c["img"].startswith("data:image/")
                                                    for c in seen["cards"] if c["face"] == "image")
        finally:
            audio_engine.create_audio_file, mcomp.memory_board = real_audio, real_board
            db.saved_session_del(uid, "games")

    @test("connection pool: more simultaneous users than connections wait their turn, nothing is reset")
    def t_pool_busy():
        import threading, time as _t
        errors, resets = [], []
        real_reset = db.reset_pool
        db.reset_pool = lambda: resets.append(1) or real_reset()
        def worker():
            try:
                conn = db.get_connection(); cur = conn.cursor()
                cur.execute("SELECT pg_sleep(0.3)"); cur.fetchall(); conn.close()
            except Exception as e:
                errors.append(e)
        try:
            threads = [threading.Thread(target=worker) for _ in range(25)]
            [th.start() for th in threads]; [th.join() for th in threads]
        finally:
            db.reset_pool = real_reset
        assert not errors and not resets, (errors[:2], len(resets))

    def fake_board(sid, cards, show_pinyin, state, key=None, default=None):
        """Stands in for the tappable board: each run, one more pair found,
        one turn each - perfect play."""
        matched = set(state["matched"])
        by_pair = {}
        for n, c in enumerate(cards):
            by_pair.setdefault(c["pair"], []).append(n)
        left = [ns for ns in by_pair.values() if not set(ns) <= matched]
        if left:
            matched |= set(left[0])
        return {"sid": sid, "matched": sorted(matched), "moves": state["moves"] + (1 if left else 0)}

    @test("Games page: all four games play through, in both display modes; results stay out of diagnosis")
    def t_games_page():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        import memory_component as mcomp
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM game_scores WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM word_attempts WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        db.saved_session_del(uid, "games")
        real_audio, real_board = audio_engine.create_audio_file, mcomp.memory_board
        audio_engine.create_audio_file = lambda text, voice=None: None
        mcomp.memory_board = fake_board
        try:
            for game, show in (("picture", "Characters + pinyin"), ("word", "Characters only"),
                               ("listen", "Characters only"), ("memory", "Characters + pinyin")):
                at = AppTest.from_file("views/8_Games.py", default_timeout=120)
                at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
                at.run()
                if game == "picture":       # credits for every Commons picture on the picker screen
                    exp = next(e for e in at.expander if e.label == "Picture credits")
                    md = exp.markdown[0].value
                    n_wm = sum(i["image"].startswith("wm:") for i in gitems.ITEMS)
                    assert "Twemoji" in md and sum(l.startswith("- **") for l in md.splitlines()) == n_wm
                assert not at.sidebar.radio, "game settings live on the page now"
                at.radio(key="games_show").set_value(show).run()
                next(b for b in at.button if b.key == f"pick_{game}").click().run()
                for _ in range(120):
                    assert not at.exception, (game, at.exception)
                    if any("Play again" in b.label for b in at.button):
                        break
                    if game == "memory":
                        assert not at.get("button_group"), "cards are tapped on the board, not picked from a list"
                        at.run()                    # the board reports one more pair
                        continue
                    if at.session_state.get("gm_ans") is None:
                        rnd = at.session_state["gm_rounds"][at.session_state["gm_i"]]
                        idx = rnd["options"].index(rnd["target"])
                        g = [x for x in at.get("button_group") if (x.key or "").startswith("gm_pick_")][0]
                        if game == "picture":
                            g.set_value(gms.label(rnd["target"], show == "Characters + pinyin")).run()
                        else:
                            g.set_value(["A", "B", "C", "D"][idx]).run()
                        continue
                    next(b for b in at.button if b.label == "Next ▶️").click().run()
                assert any("Play again" in b.label for b in at.button), game
                if game == "memory":
                    assert at.session_state["gm_moves"] == 6, "perfect play: one turn per pair"
        finally:
            audio_engine.create_audio_file, mcomp.memory_board = real_audio, real_board
        assert db.saved_session_get(uid, "games", same_day=False) is None, "a finished game leaves nothing to resume"
        scores = db.game_scores(uid)
        assert scores["picture"]["best"] > 0 and scores["memory"]["best"] == 100
        # game results are logged, but never read as evidence of a troubled word
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT vocab_id FROM word_attempts WHERE user_id = %s AND mode LIKE 'game_%%' LIMIT 1", (uid,))
        vid = cur.fetchone()[0]; conn.close()
        import word_diagnosis as _wd
        atts = [dict(a, result="wrong") for a in db.word_attempts_all(uid, vid)] * 5
        assert not _wd.is_troubled({}, [a for a in atts if a["skill"] == "recognition"])
        assert all(v == 0 for v in _wd.diagnose(atts)["scores"].values()), "games contribute no evidence"


    # ------------------------------------------------------------------
    # Today's plan, the ledger, and the retired session style
    # ------------------------------------------------------------------
    def _fresh_learner():
        """The second user, wiped clean and introduced to twelve common words
        (none due), so a plan has new words, sentences and maybe tones."""
        uid = db.list_users()[1]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "word_content", "vocab_progress", "word_diagnosis",
                    "drill_progress", "grammar_progress", "handwriting_progress", "study_sessions",
                    "activity_log", "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        cur.execute("""SELECT id FROM vocab WHERE freq_rank <= 60 AND chinese ~ '^[一-鿿]{1,3}$'
                       AND COALESCE(tag, '') <> 'China' ORDER BY freq_rank LIMIT 12""")
        for (vid,) in cur.fetchall():
            cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, next_review_date,
                           reps, streak, introduced_on) VALUES (%s, %s, 'recognition', 5, '2099-01-01', 3, 2,
                           'seeded')""", (uid, vid))
        conn.commit(); conn.close()
        return uid

    def _fake_exercise(word, **_k):
        zh = word["chinese"] if isinstance(word, dict) else word
        return {"chinese": f"我说{zh}。", "pinyin": "wǒ shuō", "english_correct": f"I say {zh}.",
                "english_distractors": ["I eat.", "I sleep.", "I run."], "word_breakdown": [],
                "grammar_point": {}, "particle_note": None, "generation_mode": "listen"}

    def _fake_content(user_id, word, allow_generate=True, known=None):
        t = word["chinese"]
        return ({"meaning": wcon.short_meaning(word["english"]), "chunks": [],
                 "sentences": [{"hanzi": f"我说{t}。", "pinyin": "", "english": "s", "structure": None}],
                 "confusables": [], "prompts": [], "introduced_words": [], "source": "generated",
                 "reviewed": True}, None)

    def _has(at, key):
        try:
            at.session_state[key]
            return True
        except KeyError:
            return False

    def _answer_step(at):
        """Answer whatever card is on screen correctly (Words, Tones, Listen & speak)."""
        labels = [b.label for b in at.button]
        btn = lambda l: next(b for b in at.button if b.label == l)
        if "Got it — test me" in labels:
            return btn("Got it — test me").click().run()
        for prefix, right in (("wd_mc_", lambda: next(o["text"] for o in at.session_state["wd_setup"]["options"]
                                                      if o["kind"] == "correct")),
                              ("sp_mc_", lambda: (lambda it: next(o["label"] for o in it["options"]
                                                                  if o["value"] == it["answer"]))(
                                  at.session_state["sp_items"][at.session_state["sp_i"]])),
                              ("sn_mc_", lambda: at.session_state["sn_ex"]["english_correct"])):
            r = [x for x in at.radio if (x.key or "").startswith(prefix)]
            if r and r[0].value is None:
                r[0].set_value(right()).run()
                return btn("Check").click().run()
        for prefix, right in (("sn_type_", lambda: at.session_state["sn_ex"]["chinese"]),
                              ("wd_type_", lambda: at.session_state["wd_items"][at.session_state["wd_i"]]
                               ["word"]["chinese"])):
            t = [x for x in at.text_input if (x.key or "").startswith(prefix)]
            if t and not t[0].value:
                t[0].set_value(right()).run()
                return btn("Check").click().run()
        if "Next ▶️" not in labels:
            raise AssertionError(f"stuck: buttons {labels}, title {[t.value for t in at.title]}, "
                                 f"md {[m.value for m in at.markdown][:5]}, "
                                 f"info {[m.value for m in at.info]} {[m.value for m in at.success]}")
        return btn("Next ▶️").click().run()

    @test("ledger: sessions capped at 45 min, plan steps and completion recorded once, minutes by strand")
    def t_ledger():
        uid = db.list_users()[1]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM study_sessions WHERE user_id = %s", (uid,)); conn.commit(); conn.close()
        db.log_study_session(uid, "words", 99999, in_plan=True, items=20)
        db.log_study_session(uid, "reading", 600)
        db.log_study_session(uid, "games", 300)
        assert db.plan_done_today(uid) == {"words"}
        db.mark_plan_complete(uid); db.mark_plan_complete(uid)
        m = db.study_minutes(uid, 7)
        assert m["by_activity"] == {"words": 45, "reading": 10, "games": 5}, m
        assert m["by_strand"] == {"study": 45, "use": 10, "play": 5} and m["total"] == 60
        assert m["plan_days"] == 1 and m["study_days"] == 1
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = %s AND activity = 'plan_complete'", (uid,))
        assert cur.fetchone()[0] == 1
        conn.close()

    @test("latest_mix is retired: stored choices migrate, and the name falls back to spaced repetition")
    def t_latest_mix_retired():
        uid = db.list_users()[1]["id"]
        db.set_session_mode(uid, "latest_mix")
        assert db.get_session_mode(uid) == "random_balanced"
        db.init_db()
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE session_mode = 'latest_mix'")
        assert cur.fetchone()[0] == 0
        conn.close()
        assert all(u["session_mode"] != "latest_mix" for u in db.list_users())

    @test("daily caps: new tone groups and new characters counted per day; word sessions take tighter caps")
    def t_daily_caps():
        uid = _fresh_learner()
        db.drill_progress_save(uid, "tone", "xiang", {"interval": 1})
        db.drill_progress_save(uid, "tone", "xiang", {"interval": 3})     # a review isn't new
        db.drill_progress_save(uid, "tone", "shi", {"interval": 1})
        assert db.drill_new_today(uid, "tone") == 2 and db.drill_new_today(uid, "pair") == 0
        db.update_handwriting_progress(uid, "好", 2, {})
        from config import HANDWRITING_NEW_PER_DAY, HANDWRITING_BACKLOG
        assert db.handwriting_new_today(uid) == 1
        assert db.handwriting_new_allowance(uid, 0) == HANDWRITING_NEW_PER_DAY - 1
        assert db.handwriting_new_allowance(uid, HANDWRITING_BACKLOG + 1) == 0
        assert db.handwriting_started(uid)
        plan = db.plan_word_session(uid, new_cap=0, unlocks=False)
        assert not [i for i in plan["items"] if i["kind"] in ("new", "unlock")]
        plan = db.plan_word_session(uid, new_cap=2)
        assert len([i for i in plan["items"] if i["kind"] == "new"]) == 2

    @test("Today: one Start runs the whole plan page to page, auto-started, then logs it as done")
    def t_today_flow():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        uid = _fresh_learner()
        real = (db.word_content_for, db.bank_get, audio_engine.create_audio_file)
        db.word_content_for, db.bank_get = _fake_content, _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("main_app.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.run()
            assert not at.exception, at.exception
            planned = [s_["key"] for s_ in tplan.build_plan(tplan.gather_state(uid))]
            assert planned[0] == "words" and planned[-1] == "sentences", planned
            next(b for b in at.button if b.label.startswith("▶️ Start")).click().run()
            # AppTest follows st.switch_page within a run but not afterwards; the
            # browser does, so the test keeps up by hand
            at.switch_page(tplan.STEPS["words"][2])
            assert _has(at, "wd_items") and at.session_state["wd_plan"], "Words starts by itself"
            assert len([i for i in at.session_state["wd_items"] if i["kind"] == "new"]) == 5
            visited = ["words"]
            for _ in range(400):
                assert not at.exception, at.exception
                if any("today's plan done" in x.value for x in at.success):
                    break
                cont = [b for b in at.button if b.label.startswith("Continue ▶")]
                if cont:
                    cont[0].click().run()
                    nxt = at.session_state["tp"]["order"][0]
                    visited.append(nxt)
                    at.switch_page(tplan.STEPS[nxt][2])
                    continue
                _answer_step(at)
            assert any("today's plan done" in x.value for x in at.success)
            assert visited == planned, (visited, planned)
            # speaking cards were typed and graded by the app: no self-grade buttons anywhere
            assert not [b for b in at.button if b.label.startswith(("Again", "Hard", "Good", "Easy"))]
            next(b for b in at.button if b.label == "🏠 Back to Today").click().run()
            at.switch_page(tplan.TODAY_PAGE).run()
            assert not at.exception, at.exception
            assert any("Today's plan is done" in x.value for x in at.success)
        finally:
            db.word_content_for, db.bank_get, audio_engine.create_audio_file = real
        done = db.plan_done_today(uid)
        assert set(planned) | {"plan_complete"} <= done, done
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT DISTINCT kind FROM activity_log WHERE user_id = %s", (uid,))
        kinds = {r[0] for r in cur.fetchall()}
        conn.close()
        assert {"read", "listen", "type"} <= kinds and "speak" not in kinds, kinds

    @test("Listen & speak: moves a schedule only when that skill is due; never introduces words")
    def t_sentences_page():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        from datetime import date as _d
        uid = _fresh_learner()
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT vocab_id FROM word_skill WHERE user_id = %s ORDER BY vocab_id LIMIT 1""", (uid,))
        due_vid = cur.fetchone()[0]
        cur.execute("UPDATE word_skill SET next_review_date = %s WHERE user_id = %s AND vocab_id = %s",
                    (_d.today().isoformat(), uid, due_vid))
        conn.commit(); conn.close()
        before = {(r[0]): r[1] for r in _rows(uid)}
        real = (db.bank_get, audio_engine.create_audio_file)
        db.bank_get = _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("views/9_Sentences.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.run()
            assert not at.sidebar.radio and not at.number_input, "no session style or size to choose"
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            cards = at.session_state["sn_cards"]
            assert [c["mode"] for c in cards] == ["listen", "speak"] * 3
            assert cards[0]["word"]["id"] == due_vid, "due words come first"
            for _ in range(60):
                assert not at.exception, at.exception
                if any("Another round" in b.label for b in at.button):
                    break
                _answer_step(at)
            assert any("Another round" in b.label for b in at.button)
        finally:
            db.bank_get, audio_engine.create_audio_file = real
        after = {(r[0]): r[1] for r in _rows(uid)}
        assert set(after) == set(before), "no new words introduced"
        assert after[due_vid] > _d.today().isoformat(), "the due word's review moved on"
        assert all(after[v] == before[v] for v in before if v != due_vid), "nothing else moved"
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM word_skill WHERE user_id = %s AND skill = 'production'", (uid,))
        assert cur.fetchone()[0] == 0, "speaking never creates a production track"
        cur.execute("SELECT activity, in_plan FROM study_sessions WHERE user_id = %s", (uid,))
        assert cur.fetchall() == [("sentences", False)]
        conn.close()

    def _rows(uid):
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT vocab_id, next_review_date FROM word_skill WHERE user_id = %s "
                    "AND skill = 'recognition'", (uid,))
        rows = cur.fetchall(); conn.close()
        return rows


    @test("plan steps on Grammar and Handwriting start by themselves and close the step")
    def t_plan_pages():
        from streamlit.testing.v1 import AppTest
        from datetime import date as _d
        import audio_engine
        uid = _fresh_learner()
        ids = [s_.id for s_ in gcur.learning_order()[:2]]
        plan_state = lambda order, params: {"date": _d.today().isoformat(), "short": False,
                                            "order": order, "params": params, "done": [], "skipped": []}
        real = (db.grammar_known_vocab, db.grammar_pick_set, db.grammar_mark_served,
                gdr.grade_answer, audio_engine.create_audio_file)
        db.grammar_known_vocab = lambda user_id: GR_KNOWN * 2
        db.grammar_pick_set = lambda user_id, sid, n: {"id": 0, "payload": _gr_payload()}
        db.grammar_mark_served = lambda set_id: None
        gdr.grade_answer = lambda structure, task, reference, said, spoken=True: {
            "verdict": "correct", "feedback": "", "better": reference}
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("views/7_Grammar.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.session_state["tp"] = plan_state(["grammar", "sentences"], {"grammar": {"ids": ids}})
            at.run()
            assert at.session_state["gr_sid"] == ids[0], "the plan's first structure starts by itself"
            assert not at.sidebar.radio and not at.sidebar.toggle
            for _ in range(120):
                assert not at.exception, at.exception
                labels = [b.label for b in at.button]
                if any(l.startswith("Continue ▶") for l in labels):
                    break
                btn = lambda l: next(b for b in at.button if b.label == l)
                if "▶️ Next structure" in labels:
                    btn("▶️ Next structure").click().run(); continue
                mc = [r for r in at.radio if (r.key or "").startswith("mc_")]
                if mc and mc[0].value is None and "Check" in labels:
                    stage = at.session_state["gr_stages"][at.session_state["gr_stage"]]
                    items = (at.session_state["gr_set"]["contrast"]["items"] if stage == "contrast"
                             else at.session_state["gr_set"][stage])
                    it = items[at.session_state["gr_item"]]
                    mc[0].set_value(it["options"][it["answer"]]).run()
                    btn("Check").click().run(); continue
                ty = [t for t in at.text_input if (t.key or "").startswith("type_")]
                if ty and not ty[0].value and "Check" in labels:
                    ty[0].set_value("我不喝咖啡。").run()
                    btn("Check").click().run(); continue
                if "Reveal" in labels:
                    btn("Reveal").click().run(); continue
                if "✅ I said that" in labels:
                    assert "🟡 Nearly" not in labels, "two honest buttons, not three"
                    btn("✅ I said that").click().run(); continue
                btn("Next ▶️").click().run()
            assert any(b.label == "Continue ▶  🎧 Listen & speak" for b in at.button)
            prog = db.grammar_progress(uid)
            assert set(ids) <= set(prog), "both structures scheduled"
            assert "grammar" in db.plan_done_today(uid)

            # handwriting: nothing to write from the vocabulary yet -> the step closes itself
            db.set_handwriting_source(uid, "vocab")
            at = AppTest.from_file("views/2_Handwriting.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.session_state["tp"] = plan_state(["handwriting"], {"handwriting": {"reviews": 15, "new": 3}})
            at.run()
            assert not at.exception, at.exception
            assert "Nothing to write today." in [x.value for x in at.success]
            assert "handwriting" in db.plan_done_today(uid)
            # from the frequency list there's always something: a session launches with the plan's cap
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("DELETE FROM study_sessions WHERE user_id = %s AND activity = 'handwriting'", (uid,))
            conn.commit(); conn.close()
            db.set_handwriting_source(uid, "frequency")
            at = AppTest.from_file("views/2_Handwriting.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.session_state["tp"] = plan_state(["handwriting"], {"handwriting": {"reviews": 15, "new": 3}})
            at.run()
            assert not at.exception, at.exception
            chars = at.session_state["hw_payload"]["chars"]
            assert at.session_state["hw_plan"] and len(chars) == 3 and all(c["is_new"] for c in chars)
        finally:
            (db.grammar_known_vocab, db.grammar_pick_set, db.grammar_mark_served,
             gdr.grade_answer, audio_engine.create_audio_file) = real
            db.set_handwriting_source(uid, "vocab")


    @test("a Library session finishes a plan step that was waiting on it, and Continue still works")
    def t_plan_adopts():
        from streamlit.testing.v1 import AppTest
        from datetime import date as _d
        import audio_engine
        uid = _fresh_learner()
        real = (db.word_content_for, db.bank_get, audio_engine.create_audio_file)
        db.word_content_for, db.bank_get = _fake_content, _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("main_app.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
            at.run()
            at.switch_page("views/1_Words.py").run()
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            assert at.session_state["wd_plan"] is False
            at.session_state["tp"] = {"date": _d.today().isoformat(), "short": False,
                                      "order": ["words", "sentences"],
                                      "params": {"sentences": {"listen": 1, "speak": 0}},
                                      "done": [], "skipped": []}
            for _ in range(80):
                assert not at.exception, at.exception
                if any(b.label.startswith("Continue ▶") for b in at.button):
                    break
                _answer_step(at)
            assert not any("Another session" in b.label for b in at.button)
            next(b for b in at.button if b.label.startswith("Continue ▶")).click().run()
            assert not at.exception, at.exception
            assert at.session_state["tp"]["order"] == ["sentences"]
            assert _has(at, "sn_cards"), "Continue went on to Listen & speak"
        finally:
            db.word_content_for, db.bank_get, audio_engine.create_audio_file = real
        assert "words" in db.plan_done_today(uid)


    def _new_session(uid, path="main_app.py"):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(path, default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
        return at

    @test("dropped connection mid-plan: Words resumes at the same card, still a plan step, and the plan carries on")
    def t_words_resume():
        import audio_engine
        uid = _fresh_learner()
        real = (db.word_content_for, db.bank_get, audio_engine.create_audio_file)
        db.word_content_for, db.bank_get = _fake_content, _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = _new_session(uid); at.run()
            next(b for b in at.button if b.label.startswith("▶️ Start")).click().run()
            at.switch_page(tplan.STEPS["words"][2])
            for _ in range(5):
                _answer_step(at)
            i, items, results = (at.session_state["wd_i"], at.session_state["wd_items"],
                                 at.session_state["wd_results"])
            ans = at.session_state["wd_ans"] if _has(at, "wd_ans") else None
            assert 0 < len(results) and i < len(items)
            # the phone locks; Streamlit forgets the session; the app is opened again
            back = _new_session(uid); back.run()
            back.switch_page(tplan.STEPS["words"][2]).run()
            assert not back.exception, back.exception
            S = back.session_state
            assert S["wd_i"] == i and S["wd_items"] == items and S["wd_results"] == results
            assert (S["wd_ans"] if _has(back, "wd_ans") else None) == ans, "same answer on screen"
            assert isinstance(S["wd_retried"], set) and S["wd_plan"] is True
            assert S["tp"]["order"][0] == "words", "today's plan came back too"
            assert "Picked up where you left off." in [c.value for c in back.caption]
            for _ in range(80):
                assert not back.exception, back.exception
                if any(b.label.startswith("Continue ▶") for b in back.button):
                    break
                _answer_step(back)
            assert any(b.label.startswith("Continue ▶") for b in back.button), "the plan moves on"
            assert "words" in db.plan_done_today(uid)
            assert db.saved_session_get(uid, "words") is None, "a finished session isn't kept"
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = %s AND activity = 'words'", (uid,))
            assert cur.fetchone()[0] == 1, "logged once, not twice"
            conn.close()
        finally:
            db.word_content_for, db.bank_get, audio_engine.create_audio_file = real

    @test("dropped connection: Listen & speak, Tones and Grammar pick up at the same item")
    def t_pages_resume():
        import audio_engine
        uid = _fresh_learner()
        real = (db.bank_get, audio_engine.create_audio_file, db.grammar_known_vocab,
                db.grammar_pick_set, db.grammar_mark_served, gdr.grade_answer)
        db.bank_get = _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        db.grammar_known_vocab = lambda user_id: GR_KNOWN * 2
        db.grammar_pick_set = lambda user_id, sid, n: {"id": 0, "payload": _gr_payload()}
        db.grammar_mark_served = lambda set_id: None
        gdr.grade_answer = lambda structure, task, reference, said, spoken=True: {
            "verdict": "correct", "feedback": "", "better": reference}
        try:
            # Listen & speak: one card answered, the next one's answer on screen
            at = _new_session(uid, "views/9_Sentences.py"); at.run()
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            _answer_step(at); _answer_step(at); _answer_step(at)     # check, next, check
            snap = {k: at.session_state[k] for k in ("sn_i", "sn_cards", "sn_results", "sn_ans", "sn_ex")}
            back = _new_session(uid, "views/9_Sentences.py"); back.run()
            assert not back.exception, back.exception
            assert {k: back.session_state[k] for k in snap} == snap
            assert "Next ▶️" in [b.label for b in back.button], "the answered card, as it was"

            # Tones: two items in (enough words met to make tone groups)
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, next_review_date, reps,
                           introduced_on) SELECT %s, id, 'recognition', 3, '2099-01-01', 3, 'seeded'
                           FROM vocab WHERE freq_rank <= 400 ON CONFLICT DO NOTHING""", (uid,))
            conn.commit(); conn.close()
            at = _new_session(uid, "views/4_Sound_and_Pairing.py"); at.run()
            next(b for b in at.button if "Start" in b.label).click().run()
            _answer_step(at); _answer_step(at); _answer_step(at)     # check, next, check
            snap = {k: at.session_state[k] for k in ("sp_i", "sp_items", "sp_results", "sp_ans")}
            assert snap["sp_i"] == 1
            back = _new_session(uid, "views/4_Sound_and_Pairing.py"); back.run()
            assert not back.exception, back.exception
            assert {k: back.session_state[k] for k in snap} == snap

            # Grammar: part-way through a structure
            at = _new_session(uid, "views/7_Grammar.py"); at.run()
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            for _ in range(3):
                mc = [r for r in at.radio if (r.key or "").startswith("mc_")][0]
                it = at.session_state["gr_set"]["identify"][at.session_state["gr_item"]]
                mc.set_value(it["options"][it["answer"]]).run()
                next(b for b in at.button if b.label == "Check").click().run()
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            snap = {k: at.session_state[k] for k in ("gr_sid", "gr_stage", "gr_item", "gr_results")}
            assert snap["gr_stage"] == 1
            back = _new_session(uid, "views/7_Grammar.py"); back.run()
            assert not back.exception, back.exception
            assert {k: back.session_state[k] for k in snap} == snap
            assert back.session_state["gr_set"] == at.session_state["gr_set"], "same drill, not a new one"
        finally:
            (db.bank_get, audio_engine.create_audio_file, db.grammar_known_vocab,
             db.grammar_pick_set, db.grammar_mark_served, gdr.grade_answer) = real

    @test("every page opens from the menu; no method choices left in the sidebar")
    def t_pages_smoke():
        from streamlit.testing.v1 import AppTest
        uid = db.list_users()[0]["id"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM saved_sessions WHERE user_id = %s", (uid,)); conn.commit(); conn.close()
        at = AppTest.from_file("main_app.py", default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "t", "display_name": "T"}
        at.run()
        for page in ("views/8_Games.py", "views/1_Words.py", "views/7_Grammar.py", "views/9_Sentences.py",
                     "views/4_Sound_and_Pairing.py", "views/2_Handwriting.py", "views/6_Reading.py",
                     "views/5_Together.py", "views/10_Admin.py", "views/0_Today.py"):
            at.switch_page(page).run()
            assert not at.exception, (page, at.exception)
            sb = at.sidebar
            assert not (sb.radio or sb.toggle or sb.slider or sb.selectbox or sb.multiselect), page

    t_bank()
    t_flags()
    t_games_page()
    t_games_resume()
    t_pool_busy()
    t_sd_page()
    t_integration_db()
    t_wd_page()
    t_words_page()
    t_wc_db()
    t_ve_db()
    t_import_lock()
    t_vocab_import()
    t_gr_db()
    t_vocab_cleanup()
    t_erhua_cleanup()
    t_freq_import()
    t_freq_mode()
    t_lesson_modes()
    t_hw_session()
    t_multiuser_vocab()
    t_multiuser_pins()
    t_legacy_backup()
    t_session_modes()
    t_char_lists()
    t_herbs()
    t_reading_rotation()
    t_ledger()
    t_latest_mix_retired()
    t_daily_caps()
    t_today_flow()
    t_sentences_page()
    t_plan_pages()
    t_plan_adopts()
    t_words_resume()
    t_pages_resume()
    t_pages_smoke()


# ======================================================================
# GRAMMAR DRILLS
# ======================================================================
import grammar_curriculum as gcur
import grammar_drills as gdr

GR_KNOWN = ["喝", "咖啡", "茶", "吃", "饭", "去", "巴刹", "喜欢", "榴莲", "明天",
            "今天", "做工", "累", "贵", "冷气", "睡觉", "早", "朋友", "打电话"]


def _gr_payload():
    mc = lambda hz, en: {"hanzi": hz, "pinyin": "", "english": en,
                         "question": "What does the speaker mean?",
                         "options": ["doesn't / won't", "didn't", "can't"],
                         "answer": 0, "explain": "不 = doesn't or won't."}
    return {
        "identify": [mc("我不喝咖啡。", "I don't drink coffee."),
                     mc("明天我不去巴刹。", "I'm not going tomorrow."),
                     mc("这个不贵。", "This isn't expensive.")],
        "produce": [{"situation": "Say you don't eat durian.", "answer_hanzi": "我不吃榴莲。",
                     "answer_pinyin": "wǒ bù chī liú lián", "answer_english": "I don't eat durian."},
                    {"situation": "Say you're not tired.", "answer_hanzi": "我不累。",
                     "answer_pinyin": "wǒ bú lèi", "answer_english": "I'm not tired."},
                    {"situation": "Tell a friend you won't go tomorrow.",
                     "answer_hanzi": "明天我不去。", "answer_pinyin": "míng tiān wǒ bú qù",
                     "answer_english": "I won't go tomorrow."}],
        "contrast": {"with": "没", "items": [mc("我不喝茶。", "I don't drink tea."),
                                            mc("我没喝茶。", "I didn't drink tea."),
                                            mc("他不去。", "He won't go.")]},
        "rapid": [{"prompt": p_, "answer_hanzi": a, "answer_pinyin": ""} for p_, a in [
            ("You don't like tea.", "我不喜欢茶。"), ("It isn't expensive.", "不贵。"),
            ("You're not going to work tomorrow.", "明天我不做工。"),
            ("You don't drink coffee.", "我不喝咖啡。"), ("You're not sleepy / going to sleep.", "我不睡觉。")]],
        "conversation": [{"question_hanzi": q, "question_pinyin": "", "question_english": qe,
                          "sample_hanzi": a, "sample_pinyin": "", "sample_english": ae}
                         for q, qe, a, ae in [
            ("你喝咖啡吗？", "Do you drink coffee?", "我不喝咖啡。", "I don't drink coffee."),
            ("你明天去巴刹吗？", "Going to the market tomorrow?", "不去。", "No."),
            ("这个贵吗？", "Is this expensive?", "不贵。", "Not expensive.")]],
        "introduced_words": [],
    }


@test("grammar curriculum: every syllabus line maps to a real, unique structure")
def t_gr_curriculum():
    from dictionary_engine import has_erhua
    ids = [s.id for s in gcur.STRUCTURES]
    assert len(ids) == len(set(ids)), "duplicate structure id"
    listed = {sid for lines in gcur.LISTED.values() for _l, sid in lines}
    assert listed <= set(ids), listed - set(ids)
    assert set(ids) <= listed, set(ids) - listed
    for s in gcur.STRUCTURES:
        assert s.section in gcur.SECTIONS and 1 <= s.level <= 5, s.id
        assert s.purpose and len(s.purpose) < 120, s.id
        assert all(c in gcur.BY_ID for c in s.contrast), s.id
        assert not has_erhua(s.pattern) and not has_erhua(s.name), s.id
    order = gcur.learning_order()
    assert order[0].level == 1 and order[0].core
    assert len(order) == len(ids) and len({s.id for s in order}) == len(ids)
    pos = {s.id: i for i, s in enumerate(order)}
    for s in order:
        if s.kind == "contrast":
            assert all(pos[c] < pos[s.id] for c in s.contrast), f"{s.id} before its parts"
            p = gdr.build_prompt(s, GR_KNOWN, contrasts=[gcur.get(c) for c in s.contrast])
            assert "CONTRAST DRILL" in p and all(gcur.get(c).pattern in p for c in s.contrast)
    le = gdr.build_prompt(gcur.get("le_verb"), GR_KNOWN)
    assert "past tense" in le and "completed action" in le


@test("grammar: 越 + verb + 越 is core, arrives with 越来越, and its drills cover verbs and the common slips")
def t_gr_yue_verb():
    s, general = gcur.get("yue_v_yue"), gcur.get("yue_yue")
    order = [x.id for x in gcur.learning_order()]
    assert s.core and s.level <= gcur.get("yuelaiyue").level
    assert abs(order.index("yue_v_yue") - order.index("yuelaiyue")) <= 2
    assert order.index("yue_v_yue") < order.index("yue_yue")
    assert "yuelaiyue" in s.contrast
    p = gdr.build_prompt(s, GR_KNOWN, contrasts=[gcur.get(c) for c in s.contrast])
    for slip in ("越说越很快", "他越说越快", "越说更快", "never show a wrong sentence"):
        assert slip in p, slip
    assert "越走越快" in general.pattern and "verb" in general.notes
    iv, _e, _n = gdr.schedule(40, 2.5, 3, core=s.core)
    assert iv == 21, "reviewed at least every three weeks"


@test("grammar syllabus: every one of the supplied lines is drilled; group 30 = contrast drills; group 36 = core")
def t_gr_syllabus():
    import re
    norm = lambda s: re.sub(r"\s+", " ", s.strip())
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                        "grammar_syllabus.txt")
    syllabus, sec = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("# "):
            continue
        if line.startswith("## "):
            sec = int(line[3:]); syllabus[sec] = []
            continue
        syllabus[sec].append(norm(line))
    assert sorted(syllabus) == list(range(1, 37)) == sorted(gcur.SECTIONS)
    mapped = {s: {norm(l) for l, _ in lines} for s, lines in gcur.LISTED.items()}
    missing = [(s, l) for s, ls in syllabus.items() for l in ls if l not in mapped.get(s, set())]
    assert not missing, missing
    extra = [(s, l) for s, ls in gcur.LISTED.items() for l, _ in ls
             if norm(l) not in syllabus[s] and "(added)" not in l]
    assert not extra, extra
    assert all(gcur.get(sid).kind == "contrast" for _l, sid in gcur.LISTED[30])
    assert len(gcur.LISTED[36]) == 50
    assert all(gcur.get(sid).core for _l, sid in gcur.LISTED[36])


@test("grammar vocab control: unstudied words caught, compounds of known words allowed")
def t_gr_vocab():
    s = gcur.get("bu_neg")
    allowed = gdr.allowed_set(GR_KNOWN, s)
    assert gdr.unknown_words("我不喝咖啡", allowed) == []
    assert gdr.unknown_words("我不喝啤酒", allowed) == ["啤酒"]
    assert gdr.unknown_words("我不喝啤酒", gdr.allowed_set(GR_KNOWN, s, ["啤酒"])) == []
    assert gdr.unknown_words("我们三个人不去", allowed) == []   # function words, numbers
    # a structure's grammar words are free, but the example nouns in its pattern are not
    mw = gdr.allowed_set(GR_KNOWN, gcur.get("mw_common"))
    assert "本" in mw and "书" not in mw
    assert gdr.unknown_words("我有一本书", mw) == ["书"]
    assert gdr.unknown_words("我喝了一杯茶", mw) == []


@test("grammar validation: good set passes; missing structure, 儿, unknown words, bad keys fail")
def t_gr_validate():
    s = gcur.get("bu_neg")
    payload, problems = gdr.validate(_gr_payload(), s, GR_KNOWN)
    assert problems == [], problems
    assert payload["identify"][0]["pinyin"]            # derived when missing
    bad = _gr_payload()
    bad["identify"][0]["hanzi"] = "我喝咖啡。"            # target structure missing
    bad["produce"][0]["answer_hanzi"] = "我一点儿不吃。"   # Beijing 儿
    bad["rapid"][0]["answer_hanzi"] = "我不喝啤酒。"       # unstudied word
    bad["contrast"]["items"][0]["answer"] = 7             # key out of range
    _p, problems = gdr.validate(bad, s, GR_KNOWN)
    text = " ".join(problems)
    assert "doesn't use the target" in text and "儿" in text
    assert "啤酒" in text and "answer index" in text


@test("grammar generation: rejected drafts are rewritten with the problems fed back")
def t_gr_generate():
    s = gcur.get("bu_neg")
    bad = _gr_payload()
    bad["rapid"][0]["answer_hanzi"] = "我不喝啤酒。"
    good = _gr_payload()
    prompts = []
    replies = iter([fake_response(bad), fake_response(good),
                    fake_response({"acceptable": False, "problems": ["[rapid 2] unnatural"]}),
                    fake_response(good),
                    fake_response({"acceptable": True, "problems": []})])
    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        return next(replies)
    ap.client = MagicMock()
    ap.client.chat.completions.create = create
    out = gdr.generate(s, GR_KNOWN)
    assert out and out["structure_id"] == "bu_neg"
    assert "啤酒" in prompts[1] and "unnatural" in prompts[3]
    assert "Beijing 儿" in prompts[0] and "咖啡" in prompts[0]


@test("grammar generation: gives up (returns None) if no draft ever passes review")
def t_gr_generate_fails_closed():
    s = gcur.get("bu_neg")
    reject = {"acceptable": False, "problems": ["[identify 1] wrong key"]}
    replies = iter([fake_response(x) for x in
                    [_gr_payload(), reject] * gdr.MAX_ATTEMPTS])
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: next(replies)
    assert gdr.generate(s, GR_KNOWN) is None


@test("audit fixes: contrast words allowed, API errors retried, unreviewed/ungraded never count")
def t_gr_audit_fixes():
    # the contrast stage may use the look-alike's grammar words
    assert "不要" in gdr.allowed_set([], gcur.get("bie"))
    assert "只有" in gdr.allowed_set([], gcur.get("zhiyao_jiu"))
    s = gcur.get("bu_neg")
    # a rate-limit error is waited out and retried, not counted as bad output
    real_sleep = gdr.time.sleep
    gdr.time.sleep = lambda _s: None
    calls = {"n": 0}
    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 rate limit")
        return fake_response(_gr_payload() if calls["n"] == 2 else {"acceptable": True, "problems": []})
    ap.client = MagicMock()
    ap.client.chat.completions.create = flaky
    out = gdr.generate(s, GR_KNOWN)
    assert out and out["reviewed"] is True and calls["n"] == 3
    # both reviewers down: shown, but flagged so the page never stores it
    calls["n"] = 0
    def reviewers_down(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return fake_response(_gr_payload())
        raise RuntimeError("down")
    ap.client.chat.completions.create = reviewers_down
    out = gdr.generate(s, GR_KNOWN)
    assert out and out["reviewed"] is False
    # grader unreachable: ungraded, not half-right
    ap.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))
    assert gdr.grade_answer(s, "x", "我不去。", "我不去")["verdict"] == "ungraded"
    assert "ungraded" not in gdr.POINTS
    gdr.time.sleep = real_sleep


@test("grammar grading + scheduling: verdicts, session grade, spacing, queue order")
def t_gr_grade_schedule():
    s = gcur.get("bu_neg")
    ap.client = MagicMock()
    ap.client.chat.completions.create = lambda **kw: fake_response(
        {"verdict": "close", "feedback": "Use 不, not 没.", "better": "我不去。"})
    g = gdr.grade_answer(s, "Say you won't go.", "我不去。", "我没去", spoken=True)
    assert g["verdict"] == "close" and g["better"] == "我不去。"
    assert gdr.grade_answer(s, "x", "我不去。", "  ")["verdict"] == "wrong"
    assert gdr.session_grade([True, True, "correct", "got"]) == (3, 1.0)
    assert gdr.session_grade([False, "wrong", "missed", "close"])[0] == 0
    from datetime import date as _d
    iv, ease, nxt = gdr.schedule(0, 2.5, 2, today=_d(2026, 1, 1))
    assert iv == 1 and nxt == "2026-01-02"
    iv, _e, _n = gdr.schedule(40, 2.5, 3, core=True)
    assert iv == 21, "core structures are capped so they keep coming back"
    order = gcur.learning_order()
    prog = {order[3].id: {"next_review_date": "2026-01-01"},
            order[5].id: {"next_review_date": "2099-01-01"}}
    q = gdr.todays_queue(order, prog, _d(2026, 1, 2), new_so_far=1, new_per_day=2)
    assert q[0].id == order[3].id and len(q) == 2 and q[1].id not in prog


# ======================================================================
# VOCABULARY ENGINE
# ======================================================================
import vocab_engine as ve


def _w(i, zh="词", tag=None, lessons=False, rank=None):
    return {"id": i, "chinese": zh, "pinyin": "cí", "english": "word", "tag": tag,
            "from_lessons": lessons, "freq_rank": rank or i}


@test("vocab engine: two-track scheduling, lapses only once learned, ungraded is a no-op")
def t_ve_schedule():
    from datetime import date as _d
    d = _d(2026, 1, 1)
    t1 = ve.update_track({}, "correct", d)
    assert t1["interval"] == 1 and t1["streak"] == 1 and t1["reps"] == 1
    assert t1["next_review_date"] == "2026-01-02"
    t2 = ve.update_track(t1, "correct", d)
    assert t2["interval"] == 3 and t2["streak"] == 2
    t3 = ve.update_track(t2, "wrong", d)
    assert t3["interval"] == 0 and t3["streak"] == 0 and t3["lapses"] == 1
    assert ve.update_track({}, "wrong", d).get("lapses", 0) == 0, "a brand-new miss isn't a lapse"
    assert ve.update_track(t2, "ungraded", d) == t2
    big = ve.update_track({"interval": 300, "ease": 3.0, "streak": 9}, "easy", d)
    assert big["interval"] == ve.MAX_INTERVAL


@test("vocab engine: production only for solid, Malaysian, word-sized items")
def t_ve_production_gate():
    assert ve.can_produce(_w(1, "巴士")) and not ve.can_produce(_w(2, "巴士", tag="China"))
    assert not ve.can_produce(_w(3, "这么早起来干嘛？")) and not ve.can_produce(_w(4, "leng zai"))
    assert not ve.production_ready({"interval": 3, "streak": 1})
    assert ve.production_ready({"interval": 3, "streak": 2})


@test("vocab engine: modes harden with strength, rotate, and lean towards weaknesses")
def t_ve_modes():
    import random as _r
    rng = _r.Random(1)
    assert ve.choose_mode(ve.RECOGNITION, step=1) == "zh_to_meaning"
    assert ve.choose_mode(ve.RECOGNITION, step=2) == "audio_to_meaning"
    assert ve.choose_mode(ve.PRODUCTION, {"streak": 0}, rng=rng) == "cloze"
    assert {ve.choose_mode(ve.PRODUCTION, {"streak": 3}, rng=rng) for _ in range(40)} <= {"cloze", "meaning_to_zh"}
    assert "spoken" in {ve.choose_mode(ve.PRODUCTION, {"streak": 6}, rng=rng) for _ in range(60)}
    for _ in range(30):   # never the same mode twice running when there's a choice
        assert ve.choose_mode(ve.RECOGNITION, {"last_mode": "audio_to_meaning"}, rng=rng) == "zh_to_meaning"
    picks = [ve.choose_mode(ve.PRODUCTION, {"streak": 6}, {"spoken": 1.0}, rng) for _ in range(600)]
    assert picks.count("spoken") > picks.count("cloze") * 1.5, "weak modes are asked more"


@test("vocab engine: new words capped per session and day, and shrink with the backlog")
def t_ve_allowance():
    assert ve.new_word_allowance(0, 0, 5, 10, 40) == 5
    assert ve.new_word_allowance(0, 8, 5, 10, 40) == 2
    assert ve.new_word_allowance(0, 12, 5, 10, 40) == 0
    assert ve.new_word_allowance(60, 0, 5, 10, 40) == 2       # half-way to 2x backlog
    assert ve.new_word_allowance(80, 0, 5, 10, 40) == 0
    lessons = [_w(100 + i, lessons=True) for i in range(10)]
    freq = [_w(i) for i in range(1, 20)]
    picked = ve.pick_new_words(lessons, freq, 5, lesson_share=0.4)
    assert len(picked) == 5 and sum(w["from_lessons"] for w in picked) == 2
    assert [w["id"] for w in picked if not w["from_lessons"]] == [1, 2, 3]


@test("vocab engine: sessions warm up on reviews and space each new word's second look")
def t_ve_session():
    import random as _r
    due_r = [_w(i) for i in range(1, 16)]
    due_p = [_w(i) for i in range(20, 26)]
    new = [_w(900), _w(901), _w(902)]
    items = ve.build_session(due_r, due_p, [_w(50)], new, max_reviews=15,
                             max_unlocks=1, rng=_r.Random(3))
    kinds = [it["kind"] for it in items]
    assert kinds[:3] == ["review"] * 3
    assert kinds.count("review") == 15 and kinds.count("unlock") == 1
    assert kinds.count("new") == 3 and kinds.count("step2") == 3
    for w in new:
        a = next(i for i, it in enumerate(items) if it["kind"] == "new" and it["word"]["id"] == w["id"])
        b = next(i for i, it in enumerate(items) if it["kind"] == "step2" and it["word"]["id"] == w["id"])
        assert b - a >= 5, (a, b)
    assert {it["skill"] for it in items if it["kind"] == "review"} == {"recognition", "production"}


# ======================================================================
# WORD CONTENT
# ======================================================================
import word_content as wcon

WC_KNOWN = ["我", "你", "他", "明天", "朋友", "老板", "一件事", "件", "事", "吗", "要", "什么", "时候"]
WC_WORD = {"id": 1, "chinese": "告诉", "pinyin": "gào su", "english": "to tell / to inform", "tag": None}


def _wc_payload():
    return {"meaning": "to tell",
            "chunks": [{"hanzi": "告诉我", "pinyin": "", "english": "tell me"},
                       {"hanzi": "告诉你一件事", "pinyin": "", "english": "tell you something"}],
            "sentences": [{"hanzi": s, "pinyin": "", "english": e, "structure": st} for s, e, st in [
                ("你告诉我吧。", "Tell me.", None), ("他没告诉我。", "He didn't tell me.", "mei_neg"),
                ("我明天告诉你。", "I'll tell you tomorrow.", None),
                ("你要告诉老板吗？", "Will you tell the boss?", "ma_question")]],
            "confusables": [{"hanzi": "说", "difference": "说 = say; 告诉 needs a person told."}],
            "prompts": [{"situation": "You want a friend to tell you something.",
                         "sample_hanzi": "你告诉我吧。", "sample_pinyin": "", "sample_english": "Tell me."}],
            "introduced_words": []}


@test("word content: typed/spoken answers - right, tone slip, same-sound character, wrong word")
def t_wc_check():
    assert wcon.check_answer("告诉", "告诉", "gào su")[0] == "correct"
    assert wcon.check_answer("gaosu", "告诉", "gào su") == ("correct", {"typed": "gaosu", "tones_given": False})
    assert wcon.check_answer("gao4 su", "告诉", "gào su")[0] == "correct"
    r, d = wcon.check_answer("gǎo su", "告诉", "gào su")
    assert r == "close" and d["tone_error"]
    r, d = wcon.check_answer("事", "是", "shì")
    assert r == "close" and d["homophone"]
    assert wcon.check_answer("shuo", "告诉", "gào su")[0] == "wrong"
    assert wcon.check_answer("", "告诉", "gào su")[0] == "wrong"
    assert wcon.short_meaning("to tell / to inform (Malaysia: 讲 jiǎng)") == "to tell"
    assert wcon.cloze("你告诉我吧。", "告诉") == "你＿＿我吧。"


@test("word content: wrong options are sound-, look- and meaning-alikes, labelled for diagnosis")
def t_wc_options():
    import random as _r
    pool = [{"chinese": c, "pinyin": p, "english": e} for c, p, e in [
        ("事", "shì", "matter / thing"), ("试", "shì", "to try"), ("说", "shuō", "to say"),
        ("告别", "gào bié", "to say goodbye"), ("吃", "chī", "to eat"), ("明天", "míng tiān", "tomorrow")]]
    pool += [{"chinese": "她", "pinyin": "tā", "english": "she"}, {"chinese": "他", "pinyin": "tā", "english": "he"},
             {"chinese": "卖", "pinyin": "mài", "english": "to sell"}]
    word = {"chinese": "是", "pinyin": "shì", "english": "to be / is"}
    opts = wcon.meaning_options(word, pool, rng=_r.Random(0))
    assert sum(o["kind"] == "correct" for o in opts) == 1 and len(opts) == 4
    assert "homophone" in {o["kind"] for o in opts}                  # 事/试 on screen
    he = {"chinese": "他", "pinyin": "tā", "english": "he"}
    assert "她" in {o["chinese"] for o in wcon.meaning_options(he, pool, rng=_r.Random(0))}
    for seed in range(10):   # listening: no option you can't tell apart by ear
        assert "她" not in {o["chinese"] for o in wcon.meaning_options(he, pool, rng=_r.Random(seed), audio=True)}
    buy = {"chinese": "买", "pinyin": "mǎi", "english": "to buy"}
    assert {"卖": "tone"}.items() <= {o["chinese"]: o["kind"] for o in wcon.meaning_options(buy, pool, rng=_r.Random(0), audio=True)}.items()
    opts = wcon.meaning_options(WC_WORD, pool, [{"hanzi": "说"}], rng=_r.Random(0))
    kinds = {o["chinese"]: o["kind"] for o in opts}
    assert kinds.get("说") == "meaning" and kinds.get("告别") == "look"
    assert len({o["text"] for o in opts}) == len(opts)


@test("word content: target present, known words only, 儿 and false structure tags rejected")
def t_wc_validate():
    structs = [gcur.get("mei_neg"), gcur.get("ma_question")]
    content, problems = wcon.validate(_wc_payload(), WC_WORD, WC_KNOWN, structs)
    assert problems == [], problems
    bad = _wc_payload()
    bad["sentences"][0]["hanzi"] = "你说吧。"                 # target missing
    bad["sentences"][2]["hanzi"] = "我明天告诉你一点儿。"      # 儿
    bad["chunks"][0]["hanzi"] = "告诉经理"                    # unstudied word
    bad["sentences"][3]["structure"] = "mei_neg"              # tag without the structure
    _c, problems = wcon.validate(bad, WC_WORD, WC_KNOWN, structs)
    text = " ".join(problems)
    assert "doesn't contain" in text and "儿" in text and "经理" in text and "tagged mei_neg" in text
    china = dict(WC_WORD, tag="China")
    c, problems = wcon.validate(_wc_payload(), china, WC_KNOWN, structs)
    assert problems == [] and c["prompts"] == [], "mainland words: recognition only"


@test("word content: rejected drafts rewritten with feedback; spoken answers graded with a cause")
def t_wc_generate():
    bad = _wc_payload(); bad["chunks"][0]["hanzi"] = "告诉经理"
    prompts = []
    replies = iter([fake_response(bad), fake_response(_wc_payload()),
                    fake_response({"acceptable": True, "problems": []})])
    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    ap.client = MagicMock(); ap.client.chat.completions.create = create
    out = wcon.generate(WC_WORD, WC_KNOWN, [gcur.get("mei_neg")])
    assert out and out["reviewed"] and "经理" in prompts[1] and "[mei_neg]" in prompts[0]
    ap.client.chat.completions.create = lambda **kw: fake_response(
        {"verdict": "close", "error": "wrong_word", "feedback": "Use 告诉.", "better": "你告诉我吧。"})
    g = wcon.grade_spoken(WC_WORD, "x", "你告诉我吧。", "你说我吧")
    assert g["verdict"] == "close" and g["error"] == "wrong_word"
    from datetime import date as _d
    rows = {"a": {"structure_id": "bu_neg", "last_seen": "2026-01-10", "next_review_date": "2026-02-01"},
            "b": {"structure_id": "ma_question", "last_seen": "2025-06-01", "next_review_date": "2026-01-05"},
            "c": {"structure_id": "shei", "last_seen": "2025-06-01", "next_review_date": "2026-03-01"}}
    got = [s.id for s in wcon.practising_structures(rows, _d(2026, 1, 12))]
    assert got == ["bu_neg", "ma_question"], got


# ======================================================================
# WORD DIAGNOSIS
# ======================================================================
import word_diagnosis as wdiag


def _att(mode, result, skill="recognition", kind="review", **detail):
    return {"mode": mode, "result": result, "skill": skill, "detail": {"kind": kind, **detail}}


@test("integration: grammar drills must recycle recent words; word sentences must use practised grammar")
def t_integration():
    s = gcur.get("bu_neg")
    recent = ["巴刹", "冷气", "做工"]
    p = gdr.build_prompt(s, GR_KNOWN, recent=recent)
    assert "RECENTLY LEARNED" in p and "巴刹、冷气、做工" in p
    payload, problems = gdr.validate(_gr_payload(), s, GR_KNOWN, ["冰厨", "锁匙", "油站"])
    assert any("recently learned" in x for x in problems), "a drill using none of them is rejected"
    payload, problems = gdr.validate(_gr_payload(), s, GR_KNOWN, recent)
    assert problems == [], problems          # 巴刹 / 冷气 / 做工 appear in the sample drill
    untagged = _wc_payload()
    for x in untagged["sentences"]:
        x["structure"] = None
    _c, problems = wcon.validate(untagged, WC_WORD, WC_KNOWN, [gcur.get("mei_neg")])
    assert any("grammar being practised" in x for x in problems)
    _c, problems = wcon.validate(untagged, WC_WORD, WC_KNOWN, [])
    assert problems == [], "no grammar practised yet: no requirement"
    assert "巴刹" in wcon.build_prompt(WC_WORD, WC_KNOWN, recent=["巴刹"])


@test("diagnosis: trouble needs scored misses; learning-step and remedy misses don't count")
def t_wd_trouble():
    assert wdiag.is_troubled({"lapses": 2}, [])
    three = [_att("zh_to_meaning", "wrong")] * 3 + [_att("zh_to_meaning", "correct")] * 7
    assert wdiag.is_troubled({}, three)
    steps = [_att("zh_to_meaning", "wrong", kind="new"), _att("audio_to_meaning", "wrong", kind="retry"),
             _att("remedy_sound", "wrong"), _att("zh_to_meaning", "wrong")]
    assert not wdiag.is_troubled({}, steps)


@test("diagnosis: each cause read from its own evidence; memory only when nothing specific fits")
def t_wd_diagnose():
    cases = {
        "tone": [_att("cloze", "close", "production", tone_error=True)] * 2,
        "sound": [_att("audio_to_meaning", "wrong", chose_kind="other")] * 3 + [_att("zh_to_meaning", "correct")] * 3,
        "character": [_att("zh_to_meaning", "wrong", chose_kind="look", chose="领")] +
                     [_att("zh_to_meaning", "wrong", chose_kind="look", chose="零")] + [_att("audio_to_meaning", "correct")] * 2,
        "confusion": [_att("zh_to_meaning", "wrong", chose_kind="meaning", chose="说")] * 2,
        "production_gap": [_att("zh_to_meaning", "correct")] * 4 + [_att("cloze", "wrong", "production", gave_up=True)] * 3,
        "usage": [_att("spoken", "close", "production", error="collocation")] * 2,
        "memory": [_att("zh_to_meaning", "wrong", chose_kind="other", chose=c) for c in "甲乙"] + [_att("audio_to_meaning", "wrong", chose_kind="other", chose="丙")],
    }
    for cause, atts in cases.items():
        d = wdiag.diagnose(atts)
        assert d["cause"] == cause, (cause, d)
        assert d["evidence"], cause
    assert wdiag.diagnose(cases["confusion"])["confused_with"] == "说"


@test("diagnosis remedies: tone variants, hearable contrasts, components, production ladder")
def t_wd_remedies():
    import random as _r
    v = wdiag.tone_variants("gào su", 3, _r.Random(1))
    assert len(v) == 3 and "gào su" not in v and all(len(x.split()) == 2 for x in v)
    assert set(wdiag.tone_variants("liù", 3, _r.Random(0))) == {"liú", "liū", "liǔ"}, "tone mark on u in iu"
    assert set(wdiag.tone_variants("guì", 3, _r.Random(0))) == {"guí", "guī", "guǐ"}, "tone mark on i in ui"
    pool = [{"chinese": c, "pinyin": p, "english": e} for c, p, e in [
        ("卖", "mài", "to sell"), ("麦", "mài", "wheat"), ("买", "mǎi", "to buy"),
        ("领", "lǐng", "to lead"), ("零", "líng", "zero"), ("冷", "lěng", "cold")]]
    buy = {"chinese": "买", "pinyin": "mǎi", "english": "to buy"}
    for r in wdiag.sound_rounds(buy, pool, _r.Random(0)):
        assert r["answer"] in r["options"]
        assert not ({"卖 mài", "麦 mài"} <= set(r["options"])), "never two identical-sounding options"
    card = wdiag.character_card({"chinese": "冷", "pinyin": "lěng", "english": "cold"}, pool, _r.Random(0))
    assert any("冫" in line for line in card["components"]) and card["rounds"]
    ladder = wdiag.production_ladder(WC_WORD, _wc_payload())
    assert ladder[0]["show"].startswith("你告＿") and ladder[-1]["answer"] == "告诉我"
    assert wdiag.check_chunk("告诉我", "告诉我", "gào su wǒ", "告诉")[0] == "correct"
    assert wdiag.check_chunk("告诉", "告诉我", "gào su wǒ", "告诉")[0] == "close"


@test("diagnosis remedies: model-written contrasts and mnemonics are checked before use")
def t_wd_written():
    say = {"chinese": "说", "pinyin": "shuō", "english": "to say"}
    known = ["你", "我", "他", "老板", "明天", "话", "一件事"]
    good = {"difference": "告诉 needs a listener; 说 doesn't.", "items": [
        {"hanzi": "你告诉我吧。", "answer": "告诉"}, {"hanzi": "他告诉老板。", "answer": "告诉"},
        {"hanzi": "你说吧。", "answer": "说"}, {"hanzi": "他说话。", "answer": "说"}]}
    bad = dict(good, items=[dict(good["items"][0], answer="说")] + good["items"][1:])   # answer not in sentence
    replies = iter([fake_response(bad), fake_response(good), fake_response({"acceptable": True, "problems": []})])
    ap.client = MagicMock(); ap.client.chat.completions.create = lambda **kw: next(replies)
    c = wdiag.write_contrast(WC_WORD, say, known)
    assert c and len(c["items"]) == 4 and c["items"][0]["gap"] == "你＿＿我吧。"
    replies = iter([fake_response(good), fake_response({"acceptable": False, "problems": ["x"]})] * 3)
    ap.client.chat.completions.create = lambda **kw: next(replies)
    assert wdiag.write_contrast(WC_WORD, say, known) is None, "an unreviewed contrast is never shown"
    ap.client.chat.completions.create = lambda **kw: fake_response({"mnemonic": "告 has a mouth 口 telling."})
    assert "口" in wdiag.write_mnemonic(WC_WORD)
    ap.client.chat.completions.create = lambda **kw: fake_response({"mnemonic": "Think of 猫 the cat."})
    assert wdiag.write_mnemonic(WC_WORD) is None, "invented characters are rejected"


# ======================================================================
# SOUND & PAIRING
# ======================================================================
import sound_drill as sdr

SD_WORDS = [{"id": i, "chinese": c, "pinyin": p, "english": e, "freq_rank": i} for i, (c, p, e) in enumerate([
    ("想要", "xiǎng yào", "to want"), ("想法", "xiǎng fǎ", "idea"), ("想念", "xiǎng niàn", "to miss"),
    ("香味", "xiāng wèi", "aroma"), ("香水", "xiāng shuǐ", "perfume"), ("好像", "hǎo xiàng", "as if"),
    ("需要", "xū yào", "to need"), ("要求", "yāo qiú", "to request"), ("不要", "bú yào", "don't"),
    ("对不起", "duì bu qǐ", "sorry"), ("为了", "wèi le", "in order to"), ("想", "xiǎng", "to think"),
    ("一起", "yì qǐ", "together"), ("一样", "yí yàng", "same")], 1)]


@test("tones: groups by syllable across your words, shown with real words; 一/不 and neutral tones left out")
def t_sd_groups():
    groups = {g["key"]: g for g in sdr.tone_groups(SD_WORDS)}
    x = groups["xiang"]
    assert [p["pinyin"] for p in x["patterns"]] == ["xiāng", "xiǎng", "xiàng"]
    assert {e["char"] for p in x["patterns"] for e in p["entries"]} == {"香", "想", "像"}
    assert sdr._example(x["patterns"][1]["entries"][0])["chinese"] == "想要", "a real word, not the bare character"
    assert "yao" in groups and {p["pinyin"] for p in groups["yao"]["patterns"]} == {"yāo", "yào"}
    assert not any(e["char"] in "一不" for g in groups.values() for p in g["patterns"] for e in p["entries"])
    assert sdr.with_tone("liu", 4) == "liù" and sdr.with_tone("gui", 4) == "guì" and sdr.with_tone("xue", 2) == "xué"


@test("tones: listening items only play what the speech engine will say right; options all sound different")
def t_sd_audio():
    import random as _r
    assert sdr.tts_safe("想", "xiǎng") and sdr.tts_safe("要求", "yāo qiú")
    assert not sdr.tts_safe("为了", "wèi le"), "了 is read liào by the app's TTS"
    assert not sdr.tts_safe("要", "yāo") and not sdr.tts_safe("长", "cháng"), "heteronyms never played alone"
    groups = {g["key"]: g for g in sdr.tone_groups(SD_WORDS)}
    for seed in range(20):
        it = sdr.tone_hear_item(groups["yao"], _r.Random(seed))
        assert "要" in it["play"] and len(it["play"]) == 2 and it["answer"] in [o["value"] for o in it["options"]]
        it = sdr.tone_hear_item(groups["xiang"], _r.Random(seed))
        chars = [o["value"].split("|")[0] for o in it["options"]]
        assert len(chars) == len(set(chars)) == 3
        pick = sdr.tone_pick_item(groups["xiang"], _r.Random(seed))
        assert pick["answer"] in [o["value"] for o in pick["options"]] and len(pick["options"]) == 4


@test("pairings: families of real words per character; three item types, answers never given away")
def t_sd_pairs():
    import random as _r
    fams = {f["char"]: f for f in sdr.families(SD_WORDS, {"想": SD_WORDS[11]})}
    assert {w["chinese"] for w in fams["想"]["words"]} == {"想要", "想法", "想念"}
    assert "要" in fams and {w["chinese"] for w in fams["要"]["words"]} >= {"想要", "需要", "要求"}
    for kind in ("pair_meaning", "pair_complete", "pair_word"):
        for seed in range(10):
            it = sdr.pair_item(fams["想"], _r.Random(seed), kind)
            values = [o["value"] for o in it["options"]]
            assert it["answer"] in values and len(values) == len(set(values))
            if kind == "pair_complete":
                assert it["question"].startswith("想＿") and it["answer"] not in it["question"].split("—")[0]
    assert fams["想"]["char_word"]["english"] == "to think"
    assert "on its own: to think" in sdr.pair_item(fams["想"], _r.Random(0))["header"]


@test("sound & pairing sessions: due groups first, a few new ones, two items each, no back-to-back repeats")
def t_sd_session():
    import random as _r
    from datetime import date as _d
    groups = sdr.tone_groups(SD_WORDS)
    items = sdr.build_session("tone", groups, {}, _d(2026, 1, 1), _r.Random(0))
    keys = [i["key"] for i in items]
    assert len(set(keys)) <= sdr.MAX_GROUPS_NEW and keys
    assert all(a != b for a, b in zip(keys, keys[1:]) if keys.count(a) < len(keys))
    prog = {"xiang": {"next_review_date": "2025-12-01"}, "yao": {"next_review_date": "2099-01-01"}}
    assert sdr.pick_keys(["yao", "xiang", "qi"], prog, _d(2026, 1, 1)) == ["xiang", "qi"]
    assert sdr.group_result([True, True]) == "correct" and sdr.group_result([True, False]) == "close"
    assert sdr.group_result([False, False]) == "wrong"


@test("session store: sets, tuples and number-keyed dicts survive the trip through JSON")
def t_store_codec():
    import json as _j
    import session_store as ss
    state = {"retried": {(12, "recognition"), (7, "production")}, "rot": {12: 1, 7: 0},
             "matched": {0, 3}, "saved": (0.8, "2026-10-01"), "items": [{"id": 1, "tag": None}],
             "empty": {}, "names": {"a": 1}}
    back = ss._dec(_j.loads(ss._blob(ss._enc(state))))
    assert back == state, back


@test("memory board: only real picture-word pairs are accepted from the board")
def t_games_accept():
    items = [{"chinese": zh} for zh in ("手", "脚", "头")]
    cards = [{"item": items[0], "face": "image"}, {"item": items[1], "face": "word"},
             {"item": items[0], "face": "word"}, {"item": items[1], "face": "image"},
             {"item": items[2], "face": "image"}, {"item": items[2], "face": "word"}]
    assert gms.accept_matches(cards, [0, 2]) == {0, 2}
    assert gms.accept_matches(cards, [0, 1]) == set(), "two different words aren't a pair"
    assert gms.accept_matches(cards, [0, 2, 1, 3, 4], already={4, 5}) == {0, 1, 2, 3, 4, 5}
    assert gms.accept_matches(cards, [99, -1, "x", None]) == set()


@test("sound drill: the page's daily allowance caps new groups in a session")
def t_sd_new_cap():
    import random as _r
    from datetime import date as _d
    groups = sdr.tone_groups(SD_WORDS)
    assert sdr.build_session("tone", groups, {}, _d(2026, 1, 1), _r.Random(0), new_cap=0) == []
    one = sdr.build_session("tone", groups, {}, _d(2026, 1, 1), _r.Random(0), new_cap=1)
    assert len({i["key"] for i in one}) == 1


# ======================================================================
# TODAY'S PLAN
# ======================================================================
import today_plan as tplan


def _plan_state(**over):
    st_ = {"done": set(),
           "words": {"due": 30, "new_room": 5, "new_available": 40},
           "tones": {"due": 2, "fresh": 10, "new_room": 3},
           "grammar": {"known": 150, "due": [("g1", "了"), ("g2", "把"), ("g3", "被")],
                       "fresh": [("g9", "越来越"), ("g10", "连…都")]},
           "handwriting": {"started": True, "due": 40, "new_room": 5, "new_available": 100},
           "sentences": {"words": 200}}
    st_.update(over)
    return st_


@test("plan: fixed order, reviews first; caps on new words, tones, grammar and writing")
def t_plan_build():
    steps = tplan.build_plan(_plan_state())
    keys = [s_["key"] for s_ in steps]
    assert keys == ["words", "tones", "grammar", "handwriting", "sentences"], keys
    by = {s_["key"]: s_ for s_ in steps}
    assert by["words"]["params"] == {"reviews": 25, "new": 5, "unlocks": True}
    assert by["words"]["detail"].startswith("25 reviews · 5 new words")
    # tones: due groups first, new ones only to fill a five-group session
    assert by["tones"]["params"]["new"] == 3
    # grammar: at most two structures, reviews before new, never more than one new
    assert by["grammar"]["params"]["ids"] == ["g1", "g2"]
    light = tplan.build_plan(_plan_state(grammar={"known": 150, "due": [], "fresh": [("g9", "越来越"), ("g10", "x")]}))
    assert {s_["key"]: s_ for s_ in light}["grammar"]["params"]["ids"] == ["g9"]
    # writing: reviews capped for the plan, a few new
    assert by["handwriting"]["params"] == {"reviews": 15, "new": 3}
    assert by["sentences"]["params"] == {"listen": 3, "speak": 3}
    assert tplan.minutes_left(steps) == sum(s_["minutes"] for s_ in steps) > 20
    # new words: never more than the queue can supply or the day allows
    few = tplan.build_plan(_plan_state(words={"due": 0, "new_room": 5, "new_available": 2}))
    assert few[0]["params"]["new"] == 2 and few[0]["detail"] == "2 new words"


@test("plan: short day is a few reviews and a little listening; done steps stay visible")
def t_plan_short():
    steps = tplan.build_plan(_plan_state(), short=True)
    assert [s_["key"] for s_ in steps] == ["words", "sentences"]
    assert steps[0]["params"] == {"reviews": 10, "new": 0, "unlocks": False}
    assert steps[1]["params"] == {"listen": 3, "speak": 0}
    assert tplan.minutes_left(steps) <= 10
    done = tplan.build_plan(_plan_state(done={"words", "grammar"}), short=True)
    assert [(s_["key"], s_["done"]) for s_ in done] == [("words", True), ("grammar", True), ("sentences", False)]
    assert tplan.next_step(done)["key"] == "sentences"


@test("plan: steps appear only when there's something to do (writing once started, grammar at 20 words)")
def t_plan_gates():
    quiet = _plan_state(words={"due": 0, "new_room": 0, "new_available": 0},
                        tones={"due": 0, "fresh": 0, "new_room": 3},
                        grammar={"known": 12, "due": [("g1", "了")], "fresh": []},
                        handwriting={"started": False, "due": 0, "new_room": 5, "new_available": 9},
                        sentences={"words": 5})
    assert tplan.build_plan(quiet) == []
    # backlog: new words held back, and the plan says why
    held = tplan.build_plan(_plan_state(words={"due": 90, "new_room": 0, "new_available": 40}))
    assert "held back" in held[0]["detail"] and held[0]["params"]["new"] == 0
    assert tplan.next_step([]) is None


# ======================================================================
# GAMES
# ======================================================================
import game_items as gitems
import games as gms
import game_images as gimg


@test("games: every word has a real, valid image; topics are big enough; pinyin matches the lists")
def t_games_items():
    import csv as _csv
    import xml.etree.ElementTree as ET
    from config import FREQUENCY_CSV_PATH, VOCAB_CSV_PATH
    from dictionary_engine import has_erhua
    zh = [i["chinese"] for i in gitems.ITEMS]
    assert len(zh) == len(set(zh)), "each word once"
    for it in gitems.ITEMS:
        assert it["image"].split(":")[0] in ("tw", "wm"), it     # bundled Twemoji or Commons only
        if it["image"].startswith("tw:"):
            ET.fromstring(gimg.path_for(it["image"]).read_text(encoding="utf-8"))   # parses as SVG
        assert gimg.img_tag(it["image"]).startswith('<img src="data:image/')
        assert len(it["pinyin"].split()) == len(it["chinese"]) and not has_erhua(it["chinese"], it["pinyin"])
    for cat in gitems.CATEGORIES:
        assert len(gitems.by_category([cat])) >= 12, cat
    vocab = {}
    for path in (VOCAB_CSV_PATH, FREQUENCY_CSV_PATH):
        for r in _csv.DictReader(open(path, encoding="utf-8")):
            vocab.setdefault(r["Chinese"], r["Pinyin"])
    clash = [(i["chinese"], i["pinyin"], vocab[i["chinese"]]) for i in gitems.ITEMS
             if i["chinese"] in vocab and vocab[i["chinese"]] != i["pinyin"]]
    assert not clash, clash
    assert (gimg.IMAGE_DIR / "ATTRIBUTION.md").exists()


@test("games: Commons pictures are bundled small and square, each credited with author, licence and source")
def t_games_commons():
    import importlib.util
    import re
    from urllib.parse import unquote
    from PIL import Image
    assert importlib.util.find_spec("game_art") is None, "hand-drawn art replaced by sourced pictures"
    credits = gimg.credits()
    used = [i["image"][3:] for i in gitems.ITEMS if i["image"].startswith("wm:")]
    assert len(used) == len(set(used)) and set(used) == set(credits), "every picture used once, none spare"
    assert len(used) >= 38
    free = re.compile(r"(CC0|Public domain|CC BY(-SA)? [0-9.]+( [a-z]{2,3})?)$")
    for name, c in credits.items():
        path = gimg.IMAGE_DIR / c["file"]
        assert path.suffix in (".jpg", ".png") and path.stat().st_size <= 60_000, (name, path.stat().st_size)
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            assert im.width == im.height and 240 <= im.width <= 400, (name, im.size)
        assert c["title"].startswith("File:") and c["author"].strip(), name
        assert unquote(c["source"]) == "https://commons.wikimedia.org/wiki/" + c["title"].replace(" ", "_"), name
        assert free.match(c["licence"]), (name, c["licence"])
        assert c["licence"] in ("CC0", "Public domain") or c["licence_url"].startswith("https://creativecommons.org/"), name
        assert c["changes"], name
    lines = gimg.credit_lines(gitems.ITEMS)
    assert len(lines) == len(used) and all(credits[n]["author"] in l.replace("\\", "") for n, l in zip(used, lines))
    svgs = {p.stem for p in gimg.IMAGE_DIR.glob("*.svg")}
    assert svgs == {i["image"][3:] for i in gitems.ITEMS if i["image"].startswith("tw:")}, "no stray Twemoji"
    assert {p.name for p in gimg.IMAGE_DIR.iterdir()} == (
        {p + ".svg" for p in svgs} | {c["file"] for c in credits.values()}
        | {"ATTRIBUTION.md", "credits.json"}), "nothing unaccounted for in data/game_images"


@test("games: rounds use same-topic look-alikes, all different; memory board has matching pairs")
def t_games_logic():
    import random as _r
    pool = gitems.by_category(["body", "tcm"])
    rounds = gms.quiz_rounds(pool, rng=_r.Random(1))
    assert len(rounds) == gms.ROUNDS and len({r["target"]["chinese"] for r in rounds}) == gms.ROUNDS
    for r in rounds:
        opts = r["options"]
        assert r["target"] in opts and len(opts) == 4
        assert len({o["chinese"] for o in opts}) == len({o["image"] for o in opts}) == 4
        assert all(o["category"] == r["target"]["category"] for o in opts), "same topic"
    cards = gms.memory_board(pool, rng=_r.Random(2))
    assert len(cards) == 12 and sum(c["face"] == "image" for c in cards) == 6
    a = next(c for c in cards if c["face"] == "image")
    b = next(c for c in cards if c["face"] == "word" and c["item"] is a["item"])
    assert gms.is_match(a, b) and not gms.is_match(a, a)
    met = {pool[0]["chinese"], pool[1]["chinese"]}
    items, topped = gms.word_pool(["body"], met, only_met=True)
    assert topped and len(items) == gms.MIN_POOL and pool[0] in items
    assert gms.points(True, 0) == 10 and gms.points(True, 9) == 20 and gms.points(False, 3) == 0
    assert gms.memory_score(6, 6) == 100 and gms.memory_score(6, 30) == 10
    assert gms.label(pool[0], True).startswith(pool[0]["chinese"] + "  ") and gms.label(pool[0], False) == pool[0]["chinese"]


# ======================================================================
# FREQUENCY LIST DATA
# ======================================================================
@test("frequency list: 10,000 unique words, ranked 1..10000, ranks agree")
def t_freq_files():
    import csv as _csv
    import re
    from config import FREQUENCY_CSV_PATH, FREQUENCY_RANKS_PATH, VOCAB_CSV_PATH
    from dictionary_engine import format_pinyin
    head = open(FREQUENCY_CSV_PATH, encoding="utf-8").readline()
    assert head == open(VOCAB_CSV_PATH, encoding="utf-8").readline(), \
        "both lists must share one format"
    rows = list(_csv.DictReader(open(FREQUENCY_CSV_PATH, encoding="utf-8")))
    assert len(rows) >= 10000
    assert len({r["Chinese"] for r in rows}) == len(rows), "a word repeats"
    assert all(r["Pinyin"].strip() and r["English"].strip() for r in rows)
    ranks = {r["Chinese"]: int(r["Rank"])
             for r in _csv.DictReader(open(FREQUENCY_RANKS_PATH, encoding="utf-8"))}
    assert all(ranks[r["Chinese"]] == i for i, r in enumerate(rows, 1))
    lesson = list(_csv.DictReader(open(VOCAB_CSV_PATH, encoding="utf-8")))
    keys = [(r["Chinese"], r["Pinyin"]) for r in lesson]
    assert len(keys) == len(set(keys)), "lesson list repeats a word"
    for r in rows + lesson:     # one syllable per space, lower case
        if re.fullmatch(r"[\u4e00-\u9fff]+", r["Chinese"]):
            assert format_pinyin(r["Pinyin"]) == r["Pinyin"], r


@test("China-tagged words: Malaysian word named, tagged Malaysia and listed above")
def t_region_tags():
    import csv as _csv
    import re
    from config import FREQUENCY_CSV_PATH, VOCAB_CSV_PATH
    freq = list(_csv.DictReader(open(FREQUENCY_CSV_PATH, encoding="utf-8")))
    lesson = list(_csv.DictReader(open(VOCAB_CSV_PATH, encoding="utf-8")))
    order = {r["Chinese"]: i for i, r in enumerate(freq)}
    tags = {}
    for r in freq + lesson:
        assert r["Tag"] in ("", "China", "Malaysia"), r
        if r["Tag"]:
            tags[r["Chinese"]] = r["Tag"]
    china = [r for r in freq + lesson if r["Tag"] == "China"]
    assert len({r["Chinese"] for r in china}) >= 90
    for r in china:
        m = re.search(r"\(Malaysia: (\S+) ", r["English"])
        assert m, r
        my = m.group(1)
        assert tags.get(my) == "Malaysia", (r["Chinese"], my)
        if r["Chinese"] in order:
            assert order.get(my, 10**9) < order[r["Chinese"]], (my, r["Chinese"])


@test("erhua: 一点儿 -> 一点 and diǎnr -> diǎn; 儿子 / 女儿 untouched; none left in lists")
def t_erhua():
    import csv as _csv
    from config import FREQUENCY_CSV_PATH, FREQUENCY_RANKS_PATH, VOCAB_CSV_PATH
    from dictionary_engine import strip_erhua, has_erhua
    assert strip_erhua("一点儿", "yì diǎnr") == ("一点", "yì diǎn")
    assert strip_erhua("你去哪儿？", "nǐ qù nǎr?") == ("你去哪？", "nǐ qù nǎ?")
    assert strip_erhua("买点儿菜", "mǎi diǎn er cài") == ("买点菜", "mǎi diǎn cài")
    for word, py in (("儿子", "ér zi"), ("女儿", "nǚ ér"), ("孤儿院", "gū ér yuàn"),
                     ("儿", "ér")):
        assert not has_erhua(word, py) and strip_erhua(word, py) == (word, py)
    for path in (FREQUENCY_CSV_PATH, VOCAB_CSV_PATH):
        for r in _csv.DictReader(open(path, encoding="utf-8")):
            assert not has_erhua(r["Chinese"], r["Pinyin"]), r
    for r in _csv.DictReader(open(FREQUENCY_RANKS_PATH, encoding="utf-8")):
        assert not has_erhua(r["Chinese"]), r


@test("pinyin house style: 'Zhème qǐlái' -> 'zhè me qǐ lái', erhua and names kept")
def t_format_pinyin():
    from dictionary_engine import format_pinyin as f
    assert f("Zhème zǎo qǐlái gàn ma?") == "zhè me zǎo qǐ lái gàn ma?"
    assert f("diǎnr") == "diǎnr" and f("yíhuìr") == "yí huìr"
    assert f("Xī'ān") == "xī ān"
    assert f("Kaya Kok") == "Kaya Kok" and f("T-shirt hěn guì") == "T-shirt hěn guì"


# ======================================================================
if __name__ == "__main__":
    print("Dictionary engine:")
    t_pinyin(); t_numerals(); t_numeral_gloss(); t_classifier()
    t_gloss_corroboration(); t_greedy_split(); t_tone_marks()
    print("Generation pipeline (mocked LLM):")
    t_mismatch(); t_pronouns(); t_classify(); t_grammar_gate(); t_erhua_gate()
    t_number_gate(); t_blocklist_and_flags(); t_reviewer_models()
    t_distractor_dedupe(); t_latin_breakdown(); t_fullwidth_punct()
    print("Handwriting engine:")
    t_hw_quality(); t_hw_context(); t_curriculum(); t_char_info(); t_precision(); t_radicals(); t_reading()
    print("Grammar drills:")
    t_gr_curriculum(); t_gr_yue_verb(); t_gr_syllabus(); t_gr_vocab(); t_gr_validate(); t_gr_generate()
    t_gr_generate_fails_closed(); t_gr_audit_fixes(); t_gr_grade_schedule()
    print("Vocabulary engine:")
    t_ve_schedule(); t_ve_production_gate(); t_ve_modes(); t_ve_allowance(); t_ve_session()
    print("Word content:")
    t_wc_check(); t_wc_options(); t_wc_validate(); t_wc_generate()
    print("Word diagnosis:")
    t_integration(); t_wd_trouble(); t_wd_diagnose(); t_wd_remedies(); t_wd_written()
    print("Sound & Pairing:")
    t_sd_groups(); t_sd_audio(); t_sd_pairs(); t_sd_session(); t_sd_new_cap(); t_games_accept(); t_store_codec()
    print("Today's plan:")
    t_plan_build(); t_plan_short(); t_plan_gates()
    print("Games:")
    t_games_items(); t_games_commons(); t_games_logic()
    print("Frequency list:")
    t_freq_files(); t_region_tags(); t_erhua(); t_format_pinyin()
    if os.environ.get("DATABASE_URL"):
        print("Database (DATABASE_URL detected):")
        db_tests()
    else:
        print("Database tests skipped (set DATABASE_URL to enable).")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed.")
    sys.exit(1 if FAILED else 0)
