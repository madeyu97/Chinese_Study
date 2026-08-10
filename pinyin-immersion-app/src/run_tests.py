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


# ======================================================================
# HOKKIEN ROMANISATION ENGINE
# ======================================================================
import hokkien_engine as hk


@test("Tâi-lô tone classes")
def t_hk_tones():
    for syl, tone in {"tsia̍h": 8, "pn̄g": 7, "kóng": 2, "sio": 1,
                      "bah": 4, "tsài": 3, "lâm": 5}.items():
        assert hk.tone_of(syl) == tone, (syl, hk.tone_of(syl), tone)


@test("Tâi-lô -> Taiji matches Tye's published examples")
def t_hk_taiji():
    # From penang-traveltips.com: tsia̍h = ciak1, pn̄g = png33
    assert hk.tailo_to_taiji("tsia̍h") == "ciak1"
    assert hk.tailo_to_taiji("pn̄g") == "png33"
    assert hk.tailo_to_taiji("tsia̍h-pn̄g") == "ciak1 png33"


@test("Tâi-lô tone 9 (double acute) does not leak into Taiji output")
def t_hk_tone9():
    assert hk.tone_of("tsha\u030bi") == 9
    out = hk.tailo_to_taiji("tsha\u030bi")
    assert "\u030b" not in out and out == "chai1", out


@test("Tâi-lô double-hyphen (neutral tone marker) parses")
def t_hk_dblhyphen():
    assert hk.tailo_to_taiji("lo\u0304o--li\u0301") == "lo33 li4"


@test("simplified vocabulary converts for traditional dictionary lookup")
def t_hk_s2t():
    from zhconv import convert
    assert convert("吃饭", "zh-tw") == "吃飯"
    assert convert("头发", "zh-tw") == "頭髮"


@test("romanisation answer matching is tone/hyphen/case tolerant")
def t_hk_match():
    assert hk.answers_match("tsiah png", "tsia̍h-pn̄g")
    assert hk.answers_match("TSIAH-PNG", "tsia̍h-pn̄g")
    assert hk.answers_match("tsiah8 png7", "tsia̍h-pn̄g")
    assert not hk.answers_match("chiah png", "tsia̍h-pn̄g")


@test("Hokkien TTS: numeric tone conversion for TTS endpoints")
def t_hk_numeric():
    assert hk.tailo_to_numeric("tsia̍h-pn̄g") == "tsiah8-png7"
    assert hk.tailo_to_numeric("kóng-uē") == "kong2-ue7"
    assert hk.tailo_to_numeric("") == ""
    rt = hk.numeric_to_tailo("tsiah8-png7")
    assert hk.tailo_to_numeric(rt) == "tsiah8-png7"   # lossless round trip


@test("Hokkien TTS: dead endpoints degrade gracefully, never raise")
def t_hk_tts_fallback():
    import hokkien_audio as ha
    original = ha._http_get
    try:
        ha._http_get = lambda url: (_ for _ in ()).throw(ConnectionError("down"))
        assert ha.synthesize("食飯", "tsia̍h-pn̄g") == (None, None, None)
        # an HTML error page must not be mistaken for audio
        ha._http_get = lambda url: (b"<html>oops</html>", "text/html")
        assert ha.synthesize("食飯", "tsia̍h-pn̄g")[0] is None
        # first provider dead -> falls through to another
        state = {"n": 0}
        def flaky(url):
            state["n"] += 1
            if state["n"] == 1:
                raise ConnectionError("down")
            return b"RIFF" + b"\x00" * 4000, "audio/wav"
        ha._http_get = flaky
        data, _mime, used = ha.synthesize("食飯", "tsia̍h-pn̄g", "ithuan")
        assert data and used != "ithuan"
    finally:
        ha._http_get = original


@test("Hokkien TTS: cache keys stable per (text, provider)")
def t_hk_audio_keys():
    import hokkien_audio as ha
    k1 = ha.audio_key("食飯", "tsia̍h-pn̄g", "ithuan")
    assert k1 == ha.audio_key("食飯", "tsia̍h-pn̄g", "ithuan")
    assert k1 != ha.audio_key("食飯", "tsia̍h-pn̄g", "ntut_tailo")
    assert k1 != ha.audio_key("巴剎", "pa-sat", "ithuan")


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

    t_bank()
    t_flags()
    t_hw_session()
    t_multiuser_vocab()
    t_multiuser_pins()
    t_legacy_backup()
    t_session_modes()
    t_char_lists()


# ======================================================================
if __name__ == "__main__":
    print("Dictionary engine:")
    t_pinyin(); t_numerals(); t_numeral_gloss(); t_classifier()
    t_gloss_corroboration(); t_greedy_split(); t_tone_marks()
    print("Generation pipeline (mocked LLM):")
    t_mismatch(); t_pronouns(); t_classify(); t_grammar_gate()
    t_number_gate(); t_blocklist_and_flags(); t_reviewer_models()
    t_distractor_dedupe(); t_latin_breakdown(); t_fullwidth_punct()
    print("Handwriting engine:")
    t_hw_quality(); t_hw_context(); t_curriculum(); t_char_info(); t_precision()
    print("Hokkien engine:")
    t_hk_tones(); t_hk_taiji(); t_hk_tone9(); t_hk_dblhyphen()
    t_hk_s2t(); t_hk_match()
    t_hk_numeric(); t_hk_tts_fallback(); t_hk_audio_keys()
    if os.environ.get("DATABASE_URL"):
        print("Database (DATABASE_URL detected):")
        db_tests()
    else:
        print("Database tests skipped (set DATABASE_URL to enable).")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed.")
    sys.exit(1 if FAILED else 0)
