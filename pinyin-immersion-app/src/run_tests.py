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
        sess = db.get_handwriting_session(new_count=2)
        for e in sess[:2]:
            for k in ("character", "word", "word_pinyin", "word_english",
                      "char_pinyin", "is_new", "stroke_count"):
                assert k in e, k
            assert e["character"] in e["word"]

    t_bank()
    t_flags()
    t_hw_session()


# ======================================================================
if __name__ == "__main__":
    print("Dictionary engine:")
    t_pinyin(); t_numerals(); t_numeral_gloss(); t_classifier()
    t_gloss_corroboration(); t_greedy_split(); t_tone_marks()
    print("Generation pipeline (mocked LLM):")
    t_mismatch(); t_pronouns(); t_classify(); t_grammar_gate()
    t_number_gate(); t_blocklist_and_flags(); t_reviewer_models()
    t_distractor_dedupe()
    print("Handwriting engine:")
    t_hw_quality(); t_hw_context()
    if os.environ.get("DATABASE_URL"):
        print("Database (DATABASE_URL detected):")
        db_tests()
    else:
        print("Database tests skipped (set DATABASE_URL to enable).")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed.")
    sys.exit(1 if FAILED else 0)
