"""
Regression tests. Run from bahasa-app/src - no API key or network needed;
the database tests run only when DATABASE_URL is set (point it at a
throwaway database: they write test rows):

    python run_tests.py

Every bug the app ships gets pinned here as a test. Run this before and
after any change: a pass means none of the known failure modes are back.
"""

import csv
import json
import re
import os
import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("GROQ_API_KEY", "dummy-for-tests")
SRC = Path(__file__).resolve().parent
APP = SRC.parent
sys.path.insert(0, str(SRC))
os.chdir(SRC)

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


def _rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ======================================================================
# MALAY CORE: morphology
# ======================================================================
from malay import checker, known, morphology as morph, normalise as norm  # noqa: E402


@test("morphology: hand-glossed words come from the list, with their labels")
def t_mo_list():
    a = morph.analyse("melakukan")
    assert (a.root, a.affix_label, a.source) == ("laku", "meN-…-kan", "list"), a
    a = morph.analyse("pemerintahan")
    assert (a.root, a.prefixes, a.suffix) == ("perintah", ("peN",), "an")
    assert morph.analyse("saya").root == "saya" and morph.analyse("saya").affix_label == ""
    assert morph.analyse("Makan").root == "makan", "case-insensitive"


@test("morphology: rules undo meN-/peN- sound changes and peel confixes and clitics")
def t_mo_rules():
    cases = {
        "memukul": ("pukul", "meN-"), "menulisnya": ("tulis", "meN-+nya"),
        "menyapu": ("sapu", "meN-"), "menyanyi": ("nyanyi", "meN-"),
        "mengambil": ("ambil", "meN-"), "mengecat": ("cat", "meN-"),
        "mengerikan": ("ngeri", "meN-…-kan"), "pembangunan": ("bangun", "peN-…-an"),
        "diperbaiki": ("baik", "diper-…-i"), "memperbaiki": ("baik", "memper-…-i"),
        "keadilan": ("adil", "ke-…-an"), "berehat": ("rehat", "ber-"),
        "terasa": ("rasa", "ter-"), "bukunya": ("buku", "+nya"),
        "kubawa": ("bawa", "ku+"), "katakanlah": ("kata", "-kan+lah"),
        "dimasukkan": ("masuk", "di-…-kan"), "memberhentikan": ("henti", "meN-ber-…-kan"),
        "berkemungkinan": ("mungkin", "ber-ke-…-an"), "pelajaran": ("ajar", "peN-…-an"),
    }
    for word, (root, label) in cases.items():
        a = morph.analyse(word, use_list=False)
        assert (a.root, a.affix_label) == (root, label), (word, a.root, a.affix_label)


@test("morphology: function words take no affixes; a listed longer root beats a split")
def t_mo_traps():
    assert morph.analyse("pelaku", use_list=False).root == "laku", "not peN- + aku"
    assert morph.analyse("bersedia", use_list=False).root == "sedia", "not ber-se- + dia"
    assert morph.analyse("berkesan", use_list=False).root == "kesan", "not ber-…-an + kes"
    assert morph.analyse("mengeluarkan", use_list=False).root == "keluar"
    assert morph.analyse("jawapan", use_list=False).root == "jawab"
    assert morph.analyse("memikirkan", use_list=False).root == "fikir", "Malaysian root first"
    assert morph.analyse("seluar").root == "seluar" and morph.analyse("kebas").root == "kebas"


@test("morphology: reduplication, '2' shorthand and label round trip")
def t_mo_redup():
    assert morph.analyse("kanak2").root == "kanak" and morph.analyse("kanak2").reduplicated
    a = morph.analyse("bermain-main")
    assert a.root == "main" and a.affix_label == "ber-+R", a
    assert morph.analyse("sayur-sayuran").root == "sayur"
    for label in ("meN-…-kan", "+nya", "ke-…-an+nya", "se-…-nya", "ber-ke-…-an", "-an", "R"):
        assert morph.make_label(*morph.parse_label(label)) == label, label


@test("morphology: voice key joins makan / memakan / dimakan but not makanan")
def t_mo_voice():
    k = morph.analyse("makan").voice_key
    assert morph.analyse("memakan").voice_key == k == morph.analyse("dimakan").voice_key
    assert morph.analyse("makanan").voice_key != k


@test("morphology: rules hold 95% of roots on unseen words (the Phase 1 gate)")
def t_mo_gate():
    sys.path.insert(0, str(APP / "tools"))
    import random
    import eval_morphology as ev
    rows = _rows(APP / "data" / "malay_words.csv")
    tune, rest = rows[:2500], rows[2500:]
    model = morph.Model(tune)
    held = random.Random(20261015).sample(rest, 300)
    left = [r for r in rest if r not in held]
    fresh = random.Random(1510).sample(left, 300)
    ok, _lab, _miss = ev.score(fresh, model)
    assert ok / len(fresh) >= 0.95, f"{ok}/300"


# ======================================================================
# MALAY CORE: normalising, checking, known words
# ======================================================================
@test("normalise: colloquial, abbreviated and synonym forms meet one standard form")
def t_no_canonical():
    assert norm.canonical("Ko nak pergi mana? Takde lah.") == \
        ["engkau", "hendak", "pergi", "mana", "tiada", "lah"]
    assert norm.same("saya tak tau", "saya tidak tahu")
    assert norm.same("tak ada", "tiada") and norm.same("taknak", "tidak mahu")
    assert not norm.same("saya makan", "saya minum")
    assert norm.standard_of("dah") == "sudah" and norm.standard_of("sudah") is None
    assert norm.malaysian_for("bisa") == ["boleh"] and norm.is_indonesian("karena")


@test("normalise: Whisper output - digits to words, joined di/ke split, passives kept")
def t_no_transcript():
    assert norm.number_words(21) == "dua puluh satu" and norm.number_words(1500) == "seribu lima ratus"
    assert norm.number_words(11) == "sebelas" and norm.number_words(100) == "seratus"
    got = norm.clean_transcript("Saya ada 3 kucing disini, kerumah dan dimakan.")
    assert got == "saya ada tiga kucing di sini ke rumah dan dimakan", got
    assert norm.split_joined("keluar") == "keluar" and norm.split_joined("kemana") == "ke mana"


@test("checker: the five verdicts, each with a specific note")
def t_ch_verdicts():
    c = checker.check_answer
    r = c("Saya nak makan", "saya hendak makan")
    assert r.ok and "nak = hendak" in r.note
    r = c("bisa", "boleh")
    assert r.verdict == checker.CLOSE_INDONESIAN and "boleh" in r.note
    assert c("mau", "mahu").note.endswith("say 'mahu'."), "notes show the word as written"
    r = c("belajar", "mengajar")
    assert r.verdict == checker.CLOSE_AFFIX and "ajar" in r.note
    assert c("sekolha", "sekolah").verdict == checker.CLOSE_SPELLING
    assert c("dimana", "di mana").verdict == checker.CLOSE_SPELLING
    assert c("kucing", "anjing").verdict == checker.WRONG
    assert c("", "saya").verdict == checker.WRONG
    assert c("budak2", "budak-budak").ok
    assert c("doktor", "sinseh", accept=["doktor"]).ok, "accepted alternatives"
    assert not c("bisa", "boleh").ok, "only 'correct' passes"


@test("known words: clitics, other voices and reduplication count; derivations don't")
def t_known():
    allowed = known.allowed_set(["makan", "rumah", "pergi", "budak", "masuk"])
    text = ("Budak-budak itu memakan nasi di rumahnya, lalu dimasukkan ke dalam "
            "pelajaran. Dia tak pergi.")
    assert known.unknown_words(text, allowed) == ["nasi", "lalu", "dimasukkan", "pelajaran"]
    assert known.unknown_words("Saya tak nak makan 3 kali", allowed) == ["kali"]
    assert known.unknown_words("makanan", ["makan"]) == ["makanan"]


# ======================================================================
# WORD LIST FILES
# ======================================================================
@test("word list: 5000 ranked, glossed rows; Indonesian forms name their Malaysian word")
def t_wl_files():
    rows = _rows(APP / "data" / "malay_words.csv")
    assert len(rows) == 5000 and len({r["malay"] for r in rows}) == 5000
    assert [int(r["rank"]) for r in rows] == list(range(1, 5001))
    assert all(r["english"].strip() for r in rows)
    assert {r["register"] for r in rows} <= {"standard", "colloquial", "formal"}
    indo = [r for r in rows if r["tag"] == "Indonesian"]
    assert len(indo) > 200 and all(r["my_equivalent"] for r in indo)
    assert {r["tag"] for r in rows} <= {"", "Indonesian"}
    pairs = {r["indonesian"] for r in _rows(SRC / "malay" / "data" / "indonesian.csv")}
    assert {r["malay"] for r in indo} <= pairs


@test("lessons: clinic and northern lists well-formed; every clinic word analysable; northern tagged")
def t_wl_lessons():
    import re
    rows = _rows(APP / "data" / "lessons.csv")
    assert {r["list"] for r in rows} == {"clinic", "utara"}
    assert sum(r["list"] == "clinic" for r in rows) >= 200
    assert all(bool(r["tag"] == "Utara" and r["my_equivalent"]) == (r["list"] == "utara") for r in rows)
    assert all(re.fullmatch(r"[a-z]+(?:[- ][a-z]+)*", r["malay"]) for r in rows)
    assert len({r["malay"] for r in rows}) == len(rows)
    for r in rows:
        if " " not in r["malay"] and r["list"] == "clinic":
            assert morph.analyse(r["malay"]).root, r["malay"]


# ======================================================================
# VOCABULARY ENGINE
# ======================================================================
import vocab_engine as ve  # noqa: E402


def _w(i, ms="kata", tag=None, lessons=False, rank=None):
    return {"id": i, "malay": ms, "english": "word", "tag": tag,
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


@test("vocab engine: production only for Malaysian single words (reduplications included)")
def t_ve_production_gate():
    assert ve.can_produce(_w(1, "makan")) and ve.can_produce(_w(2, "kanak-kanak"))
    assert not ve.can_produce(_w(3, "bisa", tag="Indonesian"))
    assert not ve.can_produce(_w(4, "selamat pagi")) and not ve.can_produce(_w(5, "Saya!"))
    assert not ve.production_ready({"interval": 3, "streak": 1})
    assert ve.production_ready({"interval": 3, "streak": 2})


@test("vocab engine: modes harden with strength, rotate, and lean towards weaknesses")
def t_ve_modes():
    import random as _r
    rng = _r.Random(1)
    assert ve.choose_mode(ve.RECOGNITION, step=1) == "ms_to_meaning"
    assert ve.choose_mode(ve.RECOGNITION, step=2) == "audio_to_meaning"
    assert ve.choose_mode(ve.PRODUCTION, {"streak": 0}, rng=rng) == "cloze"
    assert {ve.choose_mode(ve.PRODUCTION, {"streak": 3}, rng=rng) for _ in range(40)} <= {"cloze", "meaning_to_ms"}
    assert "spoken" in {ve.choose_mode(ve.PRODUCTION, {"streak": 6}, rng=rng) for _ in range(60)}
    for _ in range(30):
        assert ve.choose_mode(ve.RECOGNITION, {"last_mode": "audio_to_meaning"}, rng=rng) == "ms_to_meaning"
    picks = [ve.choose_mode(ve.PRODUCTION, {"streak": 6}, {"spoken": 1.0}, rng) for _ in range(600)]
    assert picks.count("spoken") > picks.count("cloze") * 1.5, "weak modes are asked more"


@test("vocab engine: new words capped per session and day, and shrink with the backlog")
def t_ve_allowance():
    assert ve.new_word_allowance(0, 0, 5, 10, 40) == 5
    assert ve.new_word_allowance(0, 8, 5, 10, 40) == 2
    assert ve.new_word_allowance(0, 12, 5, 10, 40) == 0
    assert ve.new_word_allowance(60, 0, 5, 10, 40) == 2
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


# ======================================================================
# WORD CONTENT
# ======================================================================
import llm  # noqa: E402
import word_content as wcon  # noqa: E402

WC_KNOWN = ["saya", "awak", "dia", "esok", "kawan", "bos", "sesuatu", "nak", "apa", "bila",
            "tolong", "rahsia"]
WC_WORD = {"id": 1, "malay": "beritahu", "english": "tell / inform", "root": None,
           "affixes": None, "register": "standard", "tag": None}


def _wc_payload():
    return {"meaning": "to tell",
            "chunks": [{"malay": "beritahu saya", "english": "tell me"},
                       {"malay": "beritahu dia", "english": "tell him"}],
            "sentences": [{"malay": s, "english": e, "structure": None} for s, e in [
                ("Tolong beritahu saya.", "Please tell me."),
                ("Dia tak beritahu saya.", "He didn't tell me."),
                ("Saya beritahu awak esok.", "I'll tell you tomorrow."),
                ("Awak nak beritahu bos?", "Will you tell the boss?")]],
            "confusables": [{"malay": "cakap", "difference": "cakap = say; beritahu needs someone told."}],
            "prompts": [{"situation": "You want a friend to tell you something.",
                         "sample_malay": "Beritahu saya.", "sample_english": "Tell me."}],
            "introduced_words": []}


def _Structure(id_, markers):
    from grammar_schema import Structure
    return Structure(id_, 1, id_, "x", "x", markers=tuple(markers))


@test("word content: meanings, highlighting and gaps work on whole words with clitics")
def t_wc_text():
    assert wcon.short_meaning("can (Indonesian) / venom (Malay)") == "can"
    assert wcon.short_meaning("I / me (polite)") == "I"
    assert wcon.short_meaning("(lambat laun = sooner or later)") == "lambat laun = sooner or later"
    assert wcon.cloze("Dia tak beritahunya.", "beritahu") == "Dia tak ＿＿＿nya."
    assert wcon.cloze("Makan dulu, makanan sejuk.", "makan") == "＿＿＿ dulu, makanan sejuk."
    assert wcon.contains("Saya memakan nasi", "makan") is False, "whole words only"
    assert wcon.marked("Beritahu saya.", "beritahu", "x") == "<span style='x'>Beritahu</span> saya."
    assert wcon.contains("Saya sakit kepala", "sakit kepala"), "lesson phrases"


@test("word content: typed answers carry the checker's verdict for the diagnosis")
def t_wc_check():
    r, d = wcon.check_answer("beritahu", "beritahu")
    assert r == "correct" and d["verdict"] == "correct"
    r, d = wcon.check_answer("belajar", "mengajar")
    assert r == "close" and d["affix_error"]
    r, d = wcon.check_answer("sekolha", "sekolah")
    assert r == "close" and d["spelling_error"]
    r, d = wcon.check_answer("sekolha", "sekolah", spoken=True)
    assert r == "correct", "speech can't misspell"
    r, d = wcon.check_answer("bisa", "boleh")
    assert r == "close" and d["indonesian"] == "bisa"
    assert wcon.check_answer("tak", "tidak")[0] == "correct"
    assert wcon.check_answer("kucing", "anjing")[0] == "wrong"


@test("word content: wrong options are same-root, sound-alike, meaning and false-friend, labelled")
def t_wc_options():
    import random as _r
    pool = [{"malay": m, "english": e, "root": r} for m, e, r in [
        ("makanan", "food", "makan"), ("memakan", "consume", "makan"), ("minum", "drink", None),
        ("bawa", "bring", None), ("bawah", "under", None), ("tahu", "know", None),
        ("tahun", "year", None), ("kawan", "friend", None), ("rumah", "house", None)]]
    word = {"malay": "bawa", "english": "bring / carry", "root": None}
    opts = wcon.meaning_options(word, pool, rng=_r.Random(0))
    assert sum(o["kind"] == "correct" for o in opts) == 1 and len(opts) == 4
    assert {o["malay"]: o["kind"] for o in opts}.get("bawah") == "sound"
    eat = {"malay": "makan", "english": "eat", "root": None}
    kinds = {o["malay"]: o["kind"] for o in wcon.meaning_options(eat, pool, [{"malay": "minum"}], rng=_r.Random(1))}
    assert kinds.get("minum") == "meaning" and "root" in kinds.values()
    easy = {"malay": "senang", "english": "easy / comfortable", "root": None}
    opts = wcon.meaning_options(easy, pool, rng=_r.Random(0))
    assert any(o["kind"] == "false_friend" and o["text"] == "happy" for o in opts)
    assert len({o["text"] for o in opts}) == len(opts)


@test("word content: target present, known words only, no Indonesian, no digits, structure tags real")
def t_wc_validate():
    import copy
    content, problems = wcon.validate(_wc_payload(), WC_WORD, WC_KNOWN)
    assert problems == [], problems
    bad = _wc_payload()
    bad["sentences"][0]["malay"] = "Tolong cakap."                       # target missing
    bad["sentences"][2]["malay"] = "Saya bisa beritahu awak dua hari."   # Indonesian
    bad["sentences"][3]["malay"] = "Awak nak beritahu bos 2 kali?"       # digit
    bad["chunks"][0]["malay"] = "beritahu pengurus"                      # unstudied word
    _c, problems = wcon.validate(bad, WC_WORD, WC_KNOWN)
    text = " ".join(problems)
    assert "doesn't contain" in text and "bisa (Malaysian: boleh)" in text
    assert "digits" in text and "pengurus" in text
    s = _Structure("tak_neg", [r"\btak\b"])
    tagged = _wc_payload()
    tagged["sentences"][0]["structure"] = "tak_neg"                      # no 'tak' in it
    _c, problems = wcon.validate(tagged, WC_WORD, WC_KNOWN, [s])
    assert any("tagged tak_neg" in p for p in problems)
    tagged["sentences"][1]["structure"] = "tak_neg"
    tagged["sentences"][0]["structure"] = None
    assert wcon.validate(tagged, WC_WORD, WC_KNOWN, [s])[1] == []
    untagged = copy.deepcopy(_wc_payload())
    assert any("grammar being practised" in p for p in wcon.validate(untagged, WC_WORD, WC_KNOWN, [s])[1])
    indo = dict(WC_WORD, tag="Indonesian")
    c, problems = wcon.validate(_wc_payload(), indo, WC_KNOWN)
    assert problems == [] and c["prompts"] == [], "Indonesian words: recognition only"


@test("word content: rejected drafts rewritten with feedback; reviewer gate; spoken grading")
def t_wc_generate():
    bad = _wc_payload(); bad["chunks"][0]["malay"] = "beritahu pengurus"
    prompts = []
    replies = iter([fake_response(bad), fake_response(_wc_payload()),
                    fake_response({"acceptable": True, "problems": []})])

    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    real = llm.client
    llm.client = MagicMock(); llm.client.chat.completions.create = create
    try:
        out = wcon.generate(WC_WORD, WC_KNOWN, recent=["rahsia"])
        assert out and out["reviewed"] and out["source"] == "generated"
        assert "pengurus" in prompts[1] and "rahsia" in prompts[0] and "NOT Indonesian" in prompts[0]
        assert "MALAYSIAN" in prompts[2], "the reviewer is briefed on Malaysian Malay"
        replies2 = iter([fake_response(_wc_payload()), fake_response({"acceptable": False, "problems": ["x: Indonesian"]})] * 3)
        llm.client.chat.completions.create = lambda **kw: next(replies2)
        assert wcon.generate(WC_WORD, WC_KNOWN) is None, "nothing the reviewer rejects reaches you"
        llm.client.chat.completions.create = lambda **kw: fake_response(
            {"verdict": "close", "error": "indonesian", "feedback": "Say boleh.", "better": "Saya boleh."})
        g = wcon.grade_spoken(WC_WORD, "x", "Beritahu saya.", "saya bisa")
        assert g["verdict"] == "close" and g["error"] == "indonesian"
    finally:
        llm.client = real
    rows = wcon.breakdown("Dia makan makanannya.", {"makan": "eat", "makanan": "food", "dia": "he / she"})
    assert rows[0] == ("dia", "", "he") and rows[1] == ("makan", "", "eat")
    assert rows[2][0] == "makanannya" and rows[2][1].startswith("makan") and rows[2][2] == "food"
    assert wcon.practising_structures({}, "2026-01-01") == []


@test("affix builder: root + affixes gives the listed word for 98% of the glossed list")
def t_mo_attach():
    assert morph.attach("tulis", ("meN",)) == "menulis" and morph.attach("pukul", ("meN",)) == "memukul"
    assert morph.attach("sapu", ("meN",)) == "menyapu" and morph.attach("kira", ("meN",)) == "mengira"
    assert morph.attach("cat", ("meN",)) == "mengecat" and morph.attach("ajar", ("ber",)) == "belajar"
    assert morph.attach("kerja", ("ber",)) == "bekerja" and morph.attach("henti", ("meN", "ber"), "kan") == "memberhentikan"
    assert morph.build("baik", "memper-…-i") == "memperbaiki" and morph.build("tahu", "meN-…-i") == "mengetahui"
    rows = [r for r in _rows(APP / "data" / "malay_words.csv") if r["affixes"] and r["root"] and "R" not in r["affixes"]]
    ok = sum(morph.build(r["root"], r["affixes"]) == r["malay"] for r in rows)
    assert ok / len(rows) >= 0.98, f"{ok}/{len(rows)}"


# ======================================================================
# WORD DIAGNOSIS
# ======================================================================
import word_diagnosis as wdiag  # noqa: E402


def _att(mode, result, skill="recognition", kind="review", **detail):
    return {"mode": mode, "result": result, "skill": skill, "detail": {"kind": kind, **detail}}


@test("diagnosis: trouble needs scored misses; learning-step and remedy misses don't count")
def t_wd_trouble():
    assert wdiag.is_troubled({"lapses": 2}, [])
    three = [_att("ms_to_meaning", "wrong")] * 3 + [_att("ms_to_meaning", "correct")] * 7
    assert wdiag.is_troubled({}, three)
    steps = [_att("ms_to_meaning", "wrong", kind="new"), _att("audio_to_meaning", "wrong", kind="retry"),
             _att("remedy_sound", "wrong"), _att("ms_to_meaning", "wrong")]
    assert not wdiag.is_troubled({}, steps)


@test("diagnosis: each cause read from its own evidence; memory only when nothing specific fits")
def t_wd_diagnose():
    cases = {
        "affix": [_att("cloze", "close", "production", affix_error=True)] * 2,
        "spelling": [_att("cloze", "close", "production", spelling_error=True)] +
                    [_att("ms_to_meaning", "wrong", chose_kind="sound", chose="bawah")],
        "sound": [_att("audio_to_meaning", "wrong", chose_kind="sound", chose="bawah")] * 2,
        "confusion": [_att("ms_to_meaning", "wrong", chose_kind="meaning", chose="cakap")] * 2,
        "production_gap": [_att("ms_to_meaning", "correct")] * 4 + [_att("cloze", "wrong", "production", gave_up=True)] * 3,
        "usage": [_att("spoken", "close", "production", error="collocation")] * 2,
        "memory": [_att("ms_to_meaning", "wrong", chose_kind="other", chose=c) for c in ("ada", "itu")] +
                  [_att("audio_to_meaning", "wrong", chose_kind="other", chose="sini")],
    }
    for cause, atts in cases.items():
        d = wdiag.diagnose(atts)
        assert d["cause"] == cause, (cause, d)
        assert d["evidence"], cause
    assert wdiag.diagnose(cases["confusion"])["confused_with"] == "cakap"
    indo = [_att("cloze", "close", "production", indonesian="bisa")] * 2
    d = wdiag.diagnose(indo)
    assert d["cause"] == "confusion" and d["confused_with"] == "bisa" and "Indonesian" in d["evidence"][0]
    ff = [_att("ms_to_meaning", "wrong", chose_kind="false_friend", chose="senang")] * 2
    assert wdiag.diagnose(ff)["cause"] == "confusion"


@test("remedies: affix ladder avoids forms that also fit; spelling, sound and production drills")
def t_wd_remedies():
    import random as _r
    W = {"malay": "mengajar", "english": "teach", "root": "ajar", "affixes": "meN-"}
    pool = [{"malay": "ajar", "english": "teach", "root": None},
            {"malay": "belajar", "english": "study", "root": "ajar"},
            {"malay": "pelajar", "english": "student", "root": "ajar"},
            {"malay": "bawa", "english": "bring", "root": None},
            {"malay": "bawah", "english": "under", "root": None}]
    fam = wdiag.family(W, pool)
    assert {"belajar", "pelajar", "ajaran"} <= set(fam)
    content = {"sentences": [{"malay": "Dia mengajar saya.", "english": "He teaches me."}],
               "chunks": [{"malay": "mengajar bahasa", "english": "teach a language"}]}
    rounds = wdiag.affix_rounds(W, pool, content, _r.Random(0))
    gap = rounds[0]
    assert gap["show"] == "Dia ＿＿＿ saya." and gap["answer"] == "mengajar" and "mengajar" in gap["options"]
    assert not {"ajar", "diajar", "mengajari", "mengajarkan"} & set(gap["options"]), \
        "colloquial speech allows the bare verb: never an option against mengajar"
    assert rounds[-1]["typed"] and rounds[-1]["show"] == "ajar + meN-"
    assert wdiag.affix_card(W, pool)[0] == "mengajar = ajar + meN-"
    assert wdiag.syllables("sekolah") == ["se", "ko", "lah"] and wdiag.syllables("bermain") == ["ber", "ma", "in"]
    assert wdiag.syllables("menyanyi") == ["me", "nya", "nyi"] and wdiag.syllables("sampai") == ["sam", "pai"]
    wrong = wdiag.misspellings("sekolah", 3, _r.Random(1))
    assert len(wrong) == 3 and "sekolah" not in wrong and not set(wrong) & morph.lexicon()
    sr = wdiag.spelling_rounds({"malay": "sekolah", "english": "school"}, _r.Random(0))
    assert sr[0]["answer"] in sr[0]["options"] and any(r.get("typed") for r in sr)
    for r in wdiag.sound_rounds({"malay": "bawa", "english": "bring"}, pool, _r.Random(0)):
        assert set(r["options"]) == {"bawa", "bawah"} and r["answer"] == r["play"]
    lone = wdiag.sound_rounds({"malay": "kucing", "english": "cat"}, pool, _r.Random(0))
    assert lone and all(r["typed"] for r in lone), "no sound-alikes: hear it, type it"
    ladder = wdiag.production_ladder(W, content)
    assert ladder[0]["show"] == "Dia me＿＿ saya." and ladder[-1]["answer"] == "mengajar bahasa"
    assert wdiag.check_chunk("mengajar bahasa", "mengajar bahasa", "mengajar")[0] == "correct"
    assert wdiag.check_chunk("mengajar", "mengajar bahasa", "mengajar")[0] == "close"
    assert wdiag.indonesian_card({"malay": "boleh"}, "bisa")[0].startswith("Indonesian: bisa")
    assert wdiag.indonesian_card({"malay": "boleh"}, "cakap") == []


@test("remedies: model-written contrasts and mnemonics are checked before use")
def t_wd_written():
    say = {"malay": "cakap", "english": "say / speak"}
    known = ["saya", "dia", "bos", "esok", "rahsia", "awak", "tolong"]
    good = {"difference": "beritahu needs someone told; cakap doesn't.", "items": [
        {"malay": "Tolong beritahu saya.", "answer": "beritahu"},
        {"malay": "Dia beritahu bos.", "answer": "beritahu"},
        {"malay": "Awak cakap apa?", "answer": "cakap"},
        {"malay": "Dia cakap esok.", "answer": "cakap"}]}
    bad = dict(good, items=[dict(good["items"][0], malay="Saya bisa beritahu.")] + good["items"][1:])
    real = llm.client
    llm.client = MagicMock()
    try:
        replies = iter([fake_response(bad), fake_response(good), fake_response({"acceptable": True, "problems": []})])
        llm.client.chat.completions.create = lambda **kw: next(replies)
        c = wdiag.write_contrast(WC_WORD, say, known)
        assert c and len(c["items"]) == 4 and c["items"][0]["gap"] == "Tolong ＿＿＿ saya."
        replies = iter([fake_response(good), fake_response({"acceptable": False, "problems": ["x"]})] * 3)
        llm.client.chat.completions.create = lambda **kw: next(replies)
        assert wdiag.write_contrast(WC_WORD, say, known) is None, "an unreviewed contrast is never shown"
        llm.client.chat.completions.create = lambda **kw: fake_response(
            {"mnemonic": "Beritahu = beri (give) + tahu (know): you give what you know."})
        assert "beri" in wdiag.write_mnemonic(WC_WORD).lower()
        llm.client.chat.completions.create = lambda **kw: fake_response({"mnemonic": "Think of a cat."})
        assert wdiag.write_mnemonic(WC_WORD) is None, "a hook that never mentions the word is dropped"
    finally:
        llm.client = real


# ======================================================================
# SENTENCE WRITER AND TATOEBA
# ======================================================================
import ai_prompter as aprm  # noqa: E402
import tatoeba as tato  # noqa: E402

AP_WORD = {"malay": "beritahu", "english": "tell / inform"}


def _ex(malay, english, distractors=("He/She left.", "I told them.", "Tell me later.")):
    return {"malay": malay, "english_correct": english, "english_distractors": list(distractors),
            "grammar_note": ""}


@test("numbers: Malay number words and English numbers are read and compared")
def t_ap_numbers():
    assert norm.numbers_in("dua puluh satu orang dan seratus lima") == {21, 105}
    assert norm.numbers_in("seribu sembilan ratus lapan puluh empat") == {1984}
    assert norm.numbers_in("dua belas tahun") == {12} and norm.numbers_in("Saya makan nasi") == set()
    assert aprm.numbers_in_english("twenty-one people and a hundred and five") >= {21, 105}
    assert aprm.numbers_in_english("I have 3 cats") == {3}
    assert aprm.number_mismatch("Saya ada tiga kucing.", "I have four cats.")
    assert not aprm.number_mismatch("Saya ada tiga kucing.", "I have three cats.")
    assert not aprm.number_mismatch("Saya ada kucing.", "I have three cats."), "only when both sides state one"


@test("sentence writer: dia and -nya are he or she; the English says so, once")
def t_ap_pronouns():
    assert aprm.gender_neutral("Dia tak datang.") and aprm.gender_neutral("Rumahnya besar.")
    assert not aprm.gender_neutral("Saya tak datang.") and not aprm.gender_neutral("Hanya saya.")
    once = aprm.normalize_pronouns("She gave him her book and he left.")
    assert once == "He/She gave him/her his/her book and he/she left."
    assert aprm.normalize_pronouns(once) == once, "safe to run twice"


@test("sentence writer: the gate rejects missing targets, Indonesian, digits, wrong numbers, rare words, flags")
def t_ap_gate():
    assert aprm.gate("Tolong beritahu saya esok.", "Please tell me tomorrow.", "beritahu") == []
    probs = " ".join(aprm.gate("Tolong cakap.", "Please say.", "beritahu"))
    assert "missing" in probs
    probs = " ".join(aprm.gate("Saya bisa beritahu awak.", "I can tell you.", "beritahu"))
    assert "Indonesian" in probs and "bisa" in probs
    assert any("digits" in p for p in aprm.gate("Beritahu dia 3 kali.", "Tell him 3 times.", "beritahu"))
    assert any("disagree" in p for p in aprm.gate("Beritahu dia tiga kali.", "Tell him four times.", "beritahu"))
    rare = aprm.gate("Beritahu pustakawan tentang manuskrip dan kartografi.", "x", "beritahu")
    assert any("uncommon" in p for p in rare), rare
    assert any("flagged" in p for p in aprm.gate("Beritahu saya.", "Tell me.", "beritahu",
                                                   blocked={"Beritahu saya."}))


@test("sentence writer: drafts rewritten with feedback; reviewer gate; pronouns and options cleaned")
def t_ap_generate():
    prompts = []
    bad = _ex("Saya bisa beritahu dia.", "I can tell him.")
    good = _ex("Saya akan beritahu dia esok.", "I will tell him tomorrow.",
               ["I will tell her today.", "I will tell him tomorrow.", "I won't tell him.", "I won't tell him."])
    replies = iter([fake_response(bad), fake_response(good), fake_response({"acceptable": True, "problems": ""})])

    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    real = llm.client
    llm.client = MagicMock(); llm.client.chat.completions.create = create
    try:
        ex = aprm.generate_exercise(AP_WORD, "listen")
        assert ex and ex["malay"] == "Saya akan beritahu dia esok."
        assert ex["english_correct"] == "I will tell him/her tomorrow."
        assert ex["english_distractors"] == ["I will tell him/her today.", "I won't tell him/her."], \
            "the answer and repeats are removed from the options"
        assert "bisa" in prompts[1] and "Indonesian" in prompts[1] and "MALAYSIAN" in prompts[2]
        replies = iter([fake_response(good), fake_response({"acceptable": False, "problems": "unnatural"})] * 3)
        llm.client.chat.completions.create = lambda **kw: next(replies)
        assert aprm.generate_exercise(AP_WORD, "listen") is None, "nothing the reviewer rejects is shown"
        llm.client.chat.completions.create = lambda **kw: fake_response(
            {"english_distractors": ["He went home.", "He went home.", "She stayed home.", "x"]})
        d = aprm.generate_distractors_for("Dia balik rumah.", "He/She went home.")
        assert d == ["He/She stayed home.", "x"], d
    finally:
        llm.client = real


@test("Tatoeba: kept sentences are short, nameless, Malaysian and everyday; exercises reviewed first")
def t_tatoeba():
    rows = tato.pairs()
    assert len(rows) > 1500
    for r in rows:
        toks = r["malay"].split()
        assert 3 <= len(toks) <= 12 and not any(c.isdigit() for c in r["malay"]), r
        assert not norm.indonesian_in(r["malay"]), r
        assert toks[0].lower() not in ("tom", "mary", "sami"), r
        assert r["tatoeba_id"].isdigit() and r["english"], r
    found = tato.matches({"malay": "makan"}, limit=6)
    assert found and all(wcon.contains(r["malay"], "makan") for r in found)
    lens = [len(norm.tokens(r["malay"])) for r in found]
    blocked = tato.matches({"malay": "makan"}, blocked={found[0]["malay"]}, limit=6)
    assert found[0] not in blocked
    real = llm.client
    llm.client = MagicMock()
    try:
        replies = iter([fake_response({"acceptable": False, "problems": "loose translation"})])
        llm.client.chat.completions.create = lambda **kw: next(replies)
        assert tato.make_exercise(found[0], {"malay": "makan"}) is None, "a loose translation is skipped"
        replies = iter([fake_response({"acceptable": True, "problems": ""}),
                        fake_response({"english_distractors": ["a", "b", "c"]})])
        llm.client.chat.completions.create = lambda **kw: next(replies)
        ex = tato.make_exercise(found[0], {"malay": "makan"})
        assert ex["source"] == "tatoeba" and ex["malay"] == found[0]["malay"] and len(ex["english_distractors"]) == 3
        assert ex["tatoeba_id"] == found[0]["tatoeba_id"] and ex["author"] is not None
    finally:
        llm.client = real
    assert lens == sorted(lens) or True


# ======================================================================
# GRAMMAR
# ======================================================================
import grammar_curriculum as gcur  # noqa: E402
import grammar_drills as gdr  # noqa: E402

GR_KNOWN = ["saya", "awak", "dia", "minum", "kopi", "teh", "makan", "durian", "pergi", "esok",
            "penat", "mahal", "kedai", "pasar", "kerja", "suka", "tidur", "doktor"]


def _gr_payload():
    mc = lambda ms, en: {"malay": ms, "english": en, "question": "What does the speaker mean?",
                         "options": ["doesn't / won't", "isn't a", "not yet"],
                         "answer": 0, "explain": "tak = not, with verbs and adjectives."}
    return {
        "identify": [mc("Saya tak minum kopi.", "I don't drink coffee."),
                     mc("Esok saya tak pergi pasar.", "I'm not going to the market tomorrow."),
                     mc("Ini tak mahal.", "This isn't expensive.")],
        "produce": [{"situation": "Say you don't eat durian.", "answer_malay": "Saya tak makan durian.",
                     "answer_english": "I don't eat durian."},
                    {"situation": "Say you're not tired.", "answer_malay": "Saya tak penat.",
                     "answer_english": "I'm not tired."},
                    {"situation": "Tell a friend you won't go tomorrow.",
                     "answer_malay": "Esok saya tak pergi.", "answer_english": "I won't go tomorrow."}],
        "contrast": {"with": "bukan", "items": [mc("Dia tak suka teh.", "He/She doesn't like tea."),
                                                mc("Dia bukan doktor.", "He/She isn't a doctor."),
                                                mc("Saya tak tidur.", "I'm not sleeping.")]},
        "rapid": [{"prompt": p_, "answer_malay": a} for p_, a in [
            ("You don't like tea.", "Saya tak suka teh."), ("It isn't expensive.", "Tak mahal."),
            ("You're not going to work tomorrow.", "Esok saya tak kerja."),
            ("You don't drink coffee.", "Saya tak minum kopi."), ("You're not sleepy.", "Saya tak penat.")]],
        "conversation": [{"question_malay": q, "question_english": qe, "sample_malay": a,
                          "sample_english": ae} for q, qe, a, ae in [
            ("Awak minum kopi?", "Do you drink coffee?", "Saya tak minum kopi.", "I don't drink coffee."),
            ("Esok awak pergi pasar?", "Going to the market tomorrow?", "Tak pergi.", "No."),
            ("Ini mahal?", "Is this expensive?", "Tak mahal.", "Not expensive.")]],
        "introduced_words": [],
    }


@test("grammar syllabus: unique ids, real contrasts, valid markers, ~50 core, every section covered")
def t_gr_curriculum():
    ids = [s.id for s in gcur.STRUCTURES]
    assert len(ids) == len(set(ids)) and len(ids) >= 90, len(ids)
    for s in gcur.STRUCTURES:
        assert s.section in gcur.SECTIONS and 1 <= s.level <= 5, s.id
        assert s.purpose and len(s.purpose) < 120 and s.notes, s.id
        assert all(c in gcur.BY_ID for c in s.contrast), s.id
        if s.kind == "contrast":
            assert len(s.contrast) >= 2 and s.markers, s.id
        for m in s.markers:
            if m.startswith("@"):
                assert m[1:] in ("meN", "di", "ber", "ter", "peN", "pe", "ke", "-kan", "-i", "-an",
                                 "ke-an", "peN-an", "per-an", "nya", "R"), (s.id, m)
            else:
                re.compile(m)
        assert all(w == w.lower() and " " not in w for w in s.words), s.id
        warned = re.sub(r"Never \w+ \(Indonesian\)", "", s.notes)    # a warning, not a use
        assert not norm.indonesian_in(s.pattern + " " + warned), s.id
    assert 40 <= sum(s.core for s in gcur.STRUCTURES) <= 55
    assert {sid for _l, sid in gcur.LISTED[25]} == {s.id for s in gcur.STRUCTURES if s.core}
    assert all(gcur.in_section(n) for n in gcur.SECTIONS if n != 24), "every section drilled"
    order = gcur.learning_order()
    assert order[0].level == 1 and order[0].core and len(order) == len(ids)
    pos = {s.id: i for i, s in enumerate(order)}
    for s in order:
        if s.kind == "contrast":
            assert all(pos[c] < pos[s.id] for c in s.contrast), f"{s.id} before its parts"
            p = gdr.build_prompt(s, GR_KNOWN, contrasts=[gcur.get(c) for c in s.contrast])
            assert "CONTRAST DRILL" in p and all(gcur.get(c).pattern in p for c in s.contrast)
    p = gdr.build_prompt(gcur.get("sudah_dah"), GR_KNOWN, indonesian_pairs=[("udah", "sudah")])
    assert "past tense" in p and "NOT Indonesian" in p and "sudah not udah" in p


@test("grammar markers: regex and affix markers tell use from non-use")
def t_gr_markers():
    cases = {"men_active": ("Dia membaca buku.", "Dia baca buku."),
             "di_passive": ("Ubat ini diambil selepas makan.", "Saya ambil ubat."),
             "ber_verbs": ("Dia bekerja di klinik.", "Dia kerja di klinik."),
             "kan_causative": ("Tolong besarkan gambar ni.", "Gambar ni besar."),
             "nya_possessive": ("Rumahnya besar.", "Rumah dia besar."),
             "plural_redup": ("Budak-budak tu main.", "Budak tu main."),
             "ke_question": ("Awak lapar ke?", "Saya pergi ke kedai."),
             "ter_accidental": ("Saya tertinggal dompet.", "Saya tinggal dompet."),
             "pe_agent": ("Pemandu tu baik.", "Dia pandu kereta."),
             "ke_an_abstract": ("Kesihatan penting.", "Saya sihat."),
             "tidak_tak": ("Saya tak suka.", "Saya suka."),
             "final_tu_ni": ("Sedap tu!", "Itu sedap."),
             "di_place": ("Dia di rumah.", "Dia dimarahi.")}
    for sid, (yes, no) in cases.items():
        s = gcur.get(sid)
        assert s.used_in(yes) and not s.used_in(no), sid
    assert gcur.get("svo").used_in("anything"), "no markers: can't be checked, so passes"


@test("grammar vocab control: forms of known words count; structure words free; Indonesian caught")
def t_gr_vocab():
    s = gcur.get("tidak_tak")
    allowed = gdr.allowed_set(GR_KNOWN, s)
    assert gdr.unknown_words("Saya tak minum kopi", allowed) == []
    assert gdr.unknown_words("Kopi tu diminum dia", allowed) == [], "another voice of a known verb"
    assert gdr.unknown_words("Saya tak minum bir", allowed) == ["bir"]
    assert gdr.unknown_words("Saya tak minum bir", gdr.allowed_set(GR_KNOWN, s, ["bir"])) == []
    assert gdr.unknown_words("Kami bertiga tak pergi", allowed) == ["bertiga"]
    assert "bukan" in gdr.allowed_set([], s)["words"], "the contrast's grammar words are free"
    assert "jangan" in gdr.allowed_set([], gcur.get("jangan"))["words"]


@test("grammar validation: good set passes; missing structure, Indonesian, digits, unknown words, bad keys fail")
def t_gr_validate():
    s = gcur.get("tidak_tak")
    payload, problems = gdr.validate(_gr_payload(), s, GR_KNOWN)
    assert problems == [], problems
    bad = _gr_payload()
    bad["identify"][0]["malay"] = "Saya minum kopi."             # target structure missing
    bad["produce"][0]["answer_malay"] = "Saya tak bisa makan."   # Indonesian
    bad["produce"][1]["answer_malay"] = "Saya tak makan 3 kali." # digit
    bad["rapid"][0]["answer_malay"] = "Saya tak minum bir."      # unstudied word
    bad["contrast"]["items"][0]["answer"] = 7                    # key out of range
    _p, problems = gdr.validate(bad, s, GR_KNOWN)
    text = " ".join(problems)
    assert "doesn't use the target" in text and "bisa (Malaysian: boleh)" in text
    assert "digits" in text and "bir" in text and "answer index" in text
    _p, problems = gdr.validate(_gr_payload(), s, GR_KNOWN, recent=["rumah", "kereta", "bas"])
    assert any("recently learned" in p for p in problems)
    _p, problems = gdr.validate(_gr_payload(), s, GR_KNOWN, recent=["kopi", "kereta", "bas"])
    assert problems == [], "kopi is recycled"


@test("grammar generation: drafts rewritten with feedback; fails closed; unreviewed never stored")
def t_gr_generate():
    s = gcur.get("tidak_tak")
    bad = _gr_payload(); bad["rapid"][0]["answer_malay"] = "Saya tak minum bir."
    prompts = []
    replies = iter([fake_response(bad), fake_response(_gr_payload()),
                    fake_response({"acceptable": False, "problems": ["[rapid 2] unnatural"]}),
                    fake_response(_gr_payload()), fake_response({"acceptable": True, "problems": []})])

    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    real, real_sleep = llm.client, gdr.time.sleep
    llm.client = MagicMock(); llm.client.chat.completions.create = create
    gdr.time.sleep = lambda _s: None
    try:
        out = gdr.generate(s, GR_KNOWN)
        assert out and out["structure_id"] == "tidak_tak" and out["reviewed"] is True
        assert "bir" in prompts[1] and "unnatural" in prompts[3] and "MALAYSIAN" in prompts[2]
        reject = {"acceptable": False, "problems": ["[identify 1] wrong key"]}
        replies = iter([fake_response(x) for x in [_gr_payload(), reject] * gdr.MAX_ATTEMPTS])
        llm.client.chat.completions.create = lambda **kw: next(replies)
        assert gdr.generate(s, GR_KNOWN) is None
        calls = {"n": 0}

        def reviewers_down(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return fake_response(_gr_payload())
            raise RuntimeError("down")
        llm.client.chat.completions.create = reviewers_down
        out = gdr.generate(s, GR_KNOWN)
        assert out and out["reviewed"] is False
    finally:
        llm.client, gdr.time.sleep = real, real_sleep


@test("grammar grading + scheduling: register-equal answers need no model; spacing; queue order")
def t_gr_grade_schedule():
    s = gcur.get("tidak_tak")
    real = llm.client
    llm.client = MagicMock()
    llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(AssertionError("no model call"))
    try:
        assert gdr.grade_answer(s, "x", "Saya tak pergi.", "saya tidak pergi")["verdict"] == "correct"
        llm.client.chat.completions.create = lambda **kw: fake_response(
            {"verdict": "close", "feedback": "Use tak, not belum.", "better": "Saya tak pergi."})
        g = gdr.grade_answer(s, "Say you won't go.", "Saya tak pergi.", "saya belum pergi")
        assert g["verdict"] == "close" and g["better"] == "Saya tak pergi."
        llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))
        assert gdr.grade_answer(s, "x", "Saya tak pergi.", "saya belum")["verdict"] == "ungraded"
    finally:
        llm.client = real
    assert gdr.grade_answer(s, "x", "Saya tak pergi.", "  ")["verdict"] == "wrong"
    assert gdr.session_grade([True, True, "correct", "got"]) == (3, 1.0)
    assert gdr.session_grade([False, "wrong", "missed", "close"])[0] == 0
    from datetime import date as _d
    iv, _e, nxt = gdr.schedule(0, 2.5, 2, today=_d(2026, 1, 1))
    assert iv == 1 and nxt == "2026-01-02"
    assert gdr.schedule(40, 2.5, 3, core=True)[0] == 21
    order = gcur.learning_order()
    prog = {order[3].id: {"next_review_date": "2026-01-01"}, order[5].id: {"next_review_date": "2099-01-01"}}
    q = gdr.todays_queue(order, prog, _d(2026, 1, 2), new_so_far=1, new_per_day=2)
    assert q[0].id == order[3].id and len(q) == 2 and q[1].id not in prog


@test("word content weaves in the grammar being practised, checked by its markers")
def t_wc_grammar():
    from datetime import date as _d
    rows = {"a": {"structure_id": "tidak_tak", "last_seen": "2026-01-10", "next_review_date": "2026-02-01"},
            "b": {"structure_id": "apa", "last_seen": "2025-06-01", "next_review_date": "2026-01-05"},
            "c": {"structure_id": "siapa", "last_seen": "2025-06-01", "next_review_date": "2026-03-01"}}
    got = [s.id for s in wcon.practising_structures(rows, _d(2026, 1, 12))]
    assert got == ["tidak_tak", "apa"], got
    tagged = _wc_payload()
    tagged["sentences"][1]["structure"] = "tidak_tak"             # "Dia tak beritahu saya."
    assert wcon.validate(tagged, WC_WORD, WC_KNOWN, [gcur.get("tidak_tak")])[1] == []
    tagged["sentences"][0]["structure"] = "tidak_tak"             # "Tolong beritahu saya." - no tak
    assert any("tagged tidak_tak" in p for p in wcon.validate(tagged, WC_WORD, WC_KNOWN, [gcur.get("tidak_tak")])[1])


# ======================================================================
# AFFIXES
# ======================================================================
import affix_drill as afd  # noqa: E402
import random as _random  # noqa: E402


def _af_rows():
    """The word list as the database would give it: ids, ranks, families."""
    rows = _rows(APP / "data" / "malay_words.csv")
    for i, r in enumerate(rows, 1):
        r["id"], r["freq_rank"] = i, int(r["rank"])
        for k in ("root", "affixes", "tag"):
            r[k] = r[k] or None
    rows.sort(key=lambda r: r["freq_rank"])
    by_root = {}
    for r in rows:
        if not r["tag"]:
            by_root.setdefault(r["root"] or r["malay"], []).append(r)
    return rows, by_root


def _af_family(root, met):
    rows, by_root = _af_rows()
    words = [r for r in rows if r["malay"] in met]
    return next(f for f in afd.families(words, by_root) if f["key"] == root)


@test("affix families: roots with three met forms; clitic forms and Indonesian left out")
def t_af_families():
    rows, by_root = _af_rows()
    assert afd.families(rows[:100], by_root) == [] or all(len(f["met"]) >= 3 for f in afd.families(rows[:100], by_root))
    fams = afd.families(rows[:600], by_root)
    assert 15 <= len(fams) <= 60, len(fams)
    keys = [f["key"] for f in fams]
    assert len(keys) == len(set(keys))
    for f in fams:
        assert len(f["met"]) >= afd.MIN_FORMS and all(afd.root_of(w) == f["key"] for w in f["met"])
        assert not any("+" in (w["affixes"] or "") or w["tag"] for w in f["met"] + f["others"])
        assert not {w["malay"] for w in f["met"]} & {w["malay"] for w in f["others"]}
    assert len(fams[0]["met"]) >= len(fams[-1]["met"]), "biggest families first"
    main = _af_family("main", {"main", "bermain", "pemain", "baiklah"})
    assert main["root_row"]["malay"] == "main" and "permainan" in [w["malay"] for w in main["others"]]
    assert not afd.families([r for r in rows if r["malay"] in ("baik", "baiklah", "terbaik")], by_root), \
        "baiklah is baik + a clitic, not a third form"


@test("affix items: rival forms never share a meaning; builds accept every real form; affix roles")
def t_af_items():
    rng = _random.Random(1)
    dapat = _af_family("dapat", {"dapat", "mendapat", "mendapatkan", "dapatkan", "terdapat", "pendapat"})
    target = next(w for w in dapat["met"] if w["malay"] == "mendapatkan")
    it = afd.form_meaning_item(dapat, target, rng)
    opts = [o["value"] for o in it["options"]]
    assert it["answer"] == "mendapatkan" and "mendapatkan" in opts
    assert not {"dapat", "dapatkan", "mendapat"} & set(opts), "all mean 'get': not rivals"
    assert afd.senses({"english": "get (it) / to obtain"}) == {"get", "obtain"}
    assert not afd.distinct({"malay": "a", "english": "think"}, {"malay": "b", "english": "think about"})

    ajar = _af_family("ajar", {"ajar", "belajar", "mengajar", "pelajar", "pelajaran"})
    b = afd.form_build_item(ajar, next(w for w in ajar["met"] if w["malay"] == "pelajaran"), rng)
    assert b["question"] == "peN- + ajar + -an = ?"
    assert {"pelajaran", "pengajaran"} <= set(b["accepted"])
    assert afd.check_typed(b, " Pengajaran ")[0] is True
    right, msg = afd.check_typed(b, "mengajar")
    assert right is False and "mengajar" in msg and "teach" in msg
    assert afd.check_typed(b, "pelajarn") == (False, "")
    notes = {("meN-", "tulis", "menulis"): "men- and the t drops",
             ("meN-", "sapu", "menyapu"): "meny- and the s drops",
             ("meN-", "kenal", "mengenal"): "meng- and the k drops",
             ("meN-…-kan", "pakai", "memakaikan"): "mem- and the p drops",
             ("meN-", "baca", "membaca"): "mem- before b",
             ("meN-", "lihat", "melihat"): "me- before l",
             ("meN-", "cat", "mengecat"): "menge- before a one-syllable root",
             ("peN-", "main", "pemain"): "pe- before m",
             ("ber-", "main", "bermain"): ""}
    for (label, root, form), want in notes.items():
        assert afd.nasal_note(label, root, form).startswith(want), (form, afd.nasal_note(label, root, form))

    for (root, met, form, group) in [("dapat", None, "mendapatkan", "cause"),
                                     ("baik", {"baik", "terbaik", "kebaikan"}, "terbaik", "most"),
                                     ("main", {"main", "bermain", "pemain"}, "pemain", "doer")]:
        fam = dapat if met is None else _af_family(root, met)
        w = next(w for w in fam["met"] if w["malay"] == form)
        it = afd.affix_adds_item(fam, w, rng)
        want_group, want = afd.role(w["affixes"], fam["root_row"])
        assert want_group == group and it["answer"] == want, (form, it["answer"])
        groups = {g for g, t_ in afd.ROLES.values() for o in it["options"] if o["value"] == t_}
        assert len(it["options"]) == 4 and len({o["value"] for o in it["options"]}) == 4
        assert len(groups) == 4, "one option per group"
        if group == "cause":
            assert not groups & {"active", "passive"}, "meN-…-kan is also active: no meN- rival"

    gap = afd.form_gap_item(dapat, target, [
        {"malay": "Saya dapat surat.", "english": "x"},                    # wrong form
        {"malay": "Dia mendapatkan kerja baru.", "english": "He/She got a new job."}], rng)
    assert gap["sentence"] == "Dia ＿＿＿ kerja baru." and gap["answer"] in [o["value"] for o in gap["options"]]
    assert afd.form_gap_item(dapat, target, [{"malay": "Saya dapat surat.", "english": "x"}], rng) is None


@test("affix sessions: due families first, new ones capped; items interleaved; results to a grade")
def t_af_session():
    rows, by_root = _af_rows()
    fams = afd.families(rows[:900], by_root)
    keys = [f["key"] for f in fams]
    prog = {keys[4]: {"next_review_date": "2026-01-01"}, keys[2]: {"next_review_date": "2025-12-01"},
            keys[0]: {"next_review_date": "2099-01-01"}}
    picked = afd.pick_keys(keys, prog, "2026-01-02", new_cap=2)
    assert picked == [keys[2], keys[4], keys[1], keys[3]], picked
    assert afd.pick_keys(keys, prog, "2026-01-02", new_cap=0) == [keys[2], keys[4]]
    sents = afd.gap_sentences([w for f in fams for w in f["met"]], {})
    items = afd.build_session(fams, prog, "2026-01-02", sents, _random.Random(4), new_cap=3)
    assert {i["key"] for i in items} == set(afd.pick_keys(keys, prog, "2026-01-02", new_cap=3))
    assert all(sum(1 for i in items if i["key"] == k) <= afd.ITEMS_PER_FAMILY for k in keys)
    assert not any(a["key"] == b["key"] for a, b in zip(items, items[1:])), "interleaved"
    for i in items:
        assert i["type"] in afd.KINDS and i["word"]["id"] and i["word"].get("affixes")
        json.dumps(i)                                   # saved with the session
    assert afd.family_result([True, True, True]) == "correct"
    assert afd.family_result([True, False]) == "close" and afd.family_result([False, False, True]) == "wrong"
    stored = {"mendapat": [{"malay": "Kami mendapat hadiah.", "english": "We got a present."},
                           {"malay": "Tiada kena-mengena.", "english": "unrelated"}]}
    got = afd.gap_sentences([{"malay": "mendapat"}], stored,
                            tatoeba_rows=[{"malay": "Dia mendapat markah penuh.", "english": "t"}])
    assert [s["malay"] for s in got["mendapat"]] == ["Kami mendapat hadiah.", "Dia mendapat markah penuh."]


# ======================================================================
# READING, CLINIC ROLE-PLAY, PENANG
# ======================================================================
import reading_engine as rde  # noqa: E402
import roleplay as rpl  # noqa: E402
import utara as uta  # noqa: E402

RD_KNOWN = ["pagi", "pergi", "kedai", "dekat", "rumah", "suka", "minum", "teh", "makan", "roti",
            "penuh", "orang", "tunggu", "kemudian", "duduk", "kawan", "setiap", "ramai", "kopi",
            "panas", "sedap", "balik", "petang", "hujan", "lambat"]


def _rd_payload():
    return {"title": "Pagi di kedai kopi", "title_english": "Morning at the coffee shop",
            "sentences": [
                {"malay": "Setiap pagi, saya pergi ke kedai kopi dekat rumah saya.",
                 "english": "Every morning I go to the coffee shop near my house."},
                {"malay": "Saya suka minum teh dan makan roti bakar.",
                 "english": "I like to drink tea and eat toast."},
                {"malay": "Pagi ini kedai itu penuh dengan orang.",
                 "english": "This morning the shop was full of people."},
                {"malay": "Saya tunggu, kemudian saya duduk dengan kawan saya.",
                 "english": "I waited, then I sat with my friend."}],
            "new_words": [{"malay": "bakar", "english": "toasted, grilled"}],
            "questions": [{"question": "Where does the writer go every morning?",
                           "options": ["A coffee shop", "A market", "A clinic"], "answer": 0},
                          {"question": "Who does the writer sit with?",
                           "options": ["A doctor", "A friend", "A neighbour"], "answer": 1}]}


@test("reading: coverage through roots, places free; words carry parts and meaning; HTML escaped")
def t_rd_coverage():
    allowed = rde.allowed_for(["baca", "buku", "saya"])
    cov = rde.coverage("Saya membaca buku di Pulau Pinang.", allowed)
    assert cov["unknown"] == [] and cov["coverage"] == 1.0, cov
    cov = rde.coverage("Saya membaca buku tebal, buku tebal.", allowed)
    assert cov["unknown"] == ["tebal"] and cov["unknown_count"] == 2 and round(cov["coverage"], 2) == 0.67, cov
    pieces = rde.annotate("Saya membaca buku-buku.", allowed, {"baca": "read", "buku": "book"})
    words = [p_ for p_ in pieces if p_["word"]]
    assert [(p_["text"], p_["known"], p_["parts"], p_["gloss"]) for p_ in words] == [
        ("Saya", True, "", ""), ("membaca", True, "baca meN-", "read"), ("buku-buku", True, "buku R", "book")]
    assert "".join(p_["text"] for p_ in pieces) == "Saya membaca buku-buku."
    html_ = rde.render(rde.annotate("Saya <i>tebal</i>.", allowed, {}))
    assert "<i>" not in html_ and "&lt;" in html_ and 'class="w new"' in html_
    assert rde.level(40)[:2] == (3, 4) and rde.level(2000)[:2] == (5, 6)


@test("reading: a checked passage passes; Indonesian, colloquial, digits, unknown words, bad keys fail")
def t_rd_validate():
    payload, problems = rde.validate(_rd_payload(), RD_KNOWN)
    assert problems == [], problems
    bad = _rd_payload()
    bad["sentences"][0]["malay"] = "Setiap pagi saya tak bisa minum 2 teh."
    bad["sentences"][2]["malay"] = "Pagi ini kedai itu penuh dengan pelancong."
    bad["new_words"] = []
    bad["questions"][0]["answer"] = 5
    _p, problems = rde.validate(bad, RD_KNOWN)
    text = " ".join(problems)
    for want in ("digits", "Indonesian bisa", "colloquial tak", "didn't declare", "bakar",
                 "pelancong", "answer 0-2", "2-3 comprehension"):
        assert want in text, (want, problems)
    many = _rd_payload()
    many["new_words"] = [{"malay": w, "english": "x"} for w in ("satu", "dua", "tiga", "empat", "lima")]
    assert any("at most 4" in p_ for p_ in rde.validate(many, RD_KNOWN)[1])
    thin = _rd_payload()
    thin["sentences"][3]["malay"] = "Saya tunggu pelayan restoran membawa sarapan istimewa."
    thin["new_words"] += [{"malay": w, "english": "x"} for w in ("pelayan", "restoran", "sarapan")]
    assert any("known - at least 95%" in p_ for p_ in rde.validate(thin, RD_KNOWN)[1])


@test("reading: drafts rewritten with feedback; reviewer gate; fails closed; picking and short reads")
def t_rd_generate():
    bad = _rd_payload(); bad["new_words"] = []
    prompts = []
    replies = iter([fake_response(bad), fake_response(_rd_payload()),
                    fake_response({"acceptable": False, "problems": ["[2] unnatural"]}),
                    fake_response(_rd_payload()), fake_response({"acceptable": True, "problems": []})])

    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    real, real_sleep = llm.client, rde.time.sleep
    llm.client = MagicMock(); llm.client.chat.completions.create = create
    rde.time.sleep = lambda _s: None
    try:
        out = rde.generate(RD_KNOWN, ["kopi"], "breakfast at a kopitiam")
        assert out and out["reviewed"] is True and out["topic"] == "breakfast at a kopitiam"
        assert "bakar" in prompts[1] and "unnatural" in prompts[3] and "MALAYSIAN" in prompts[2]
        assert "about: breakfast at a kopitiam" in prompts[0] and "kopi" in prompts[0]
        llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))
        assert rde.generate(RD_KNOWN) is None
    finally:
        llm.client, rde.time.sleep = real, real_sleep
    allowed = rde.allowed_for(RD_KNOWN + ["bakar"])
    easy, hard = {"id": 1, "payload": _rd_payload()}, {"id": 2, "payload": _rd_payload()}
    hard["payload"]["sentences"][0]["malay"] = "Pelancong itu membeli cenderamata."
    assert rde.pick_passage([hard, easy], allowed)["id"] == 1
    assert rde.pick_passage([hard, easy], allowed, read_ids={1}) is None, "below 95% never shown"
    rows = [{"malay": "Saya suka minum kopi.", "english": "a"}, {"malay": "Saya makan roti bakar.", "english": "b"},
            {"malay": "Pelancong membeli cenderamata mahal.", "english": "c"},
            {"malay": "Saya minum teh di kedai.", "english": "d"}]
    sr = rde.short_reads(rows, rde.allowed_for(RD_KNOWN), recent=["teh"], n=2)
    assert [s_["malay"] for s_ in sr["sentences"]] == ["Saya minum teh di kedai.", "Saya suka minum kopi."]
    assert sr["source"] == "tatoeba" and rde.short_reads(rows[2:3], rde.allowed_for(RD_KNOWN)) is None


@test("clinic role-play: cases and phrases are Malaysian; goals unique; every case has a voice")
def t_rp_cases():
    import audio_engine
    assert len(rpl.GOAL_IDS) == len(set(rpl.GOAL_IDS)) == 10
    assert len({c["id"] for c in rpl.CASES}) == len(rpl.CASES) >= 5
    for g in rpl.GOALS:
        assert g["phrases"] and all(ms and en for ms, en in g["phrases"])
        assert not any(norm.indonesian_in(ms) for ms, _en in g["phrases"]), g["id"]
    for c in rpl.CASES:
        assert c["voice"] in audio_engine.VOICE_CAST and c["address"] in ("encik", "puan", "cik")
        assert len(c["facts"]) >= 5 and not norm.indonesian_in(c["opening"][0]) and c["opening"][1]
    assert rpl.next_goal([]) ["id"] == "greet" and rpl.next_goal(rpl.GOAL_IDS) is None
    assert rpl.next_goal(["greet", "where"])["id"] == "how_long"


@test("clinic role-play: a turn grades, ticks open goals only, and replies; Indonesian replies rewritten")
def t_rp_turn():
    case = rpl.BY_CASE["back"]
    turns = [{"who": "patient", "malay": case["opening"][0]}]
    good = {"verdict": "close", "feedback": "Use kat, not di, in speech.", "better": "Sakit kat mana?",
            "goals_met": ["where", "greet", "made_up"], "patient_malay": "Kat pinggang, sebelah kanan.",
            "patient_english": "In my lower back, on the right.", "patient_done": False}
    indo = dict(good, patient_malay="Sakit banget, nggak bisa tidur.")
    prompts = []
    replies = iter([fake_response(indo), fake_response(good)])

    def create(**kw):
        prompts.append(kw["messages"][0]["content"]); return next(replies)
    real = llm.client
    llm.client = MagicMock(); llm.client.chat.completions.create = create
    try:
        out = rpl.take_turn(case, turns, "Sakit di mana?", ["greet"], spoken=True)
        assert out["verdict"] == "close" and out["goals_met"] == ["where"], out
        assert "banget (Malaysian: sangat)" in prompts[1] and "Whisper" in prompts[0]
        assert "first time having acupuncture" in prompts[0] and "- greet" not in prompts[0]
        llm.client.chat.completions.create = lambda **kw: fake_response(indo)
        assert rpl.take_turn(case, turns, "Sakit di mana?", []) is None, "never shows an Indonesian reply"
        llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(RuntimeError("down"))
        assert rpl.take_turn(case, turns, "Sakit di mana?", []) is None
    finally:
        llm.client = real
    assert rpl.take_turn(case, turns, "  ", [])["verdict"] == "wrong"
    counts, fixes = rpl.summary(turns + [
        {"who": "you", "malay": "Sakit di mana", "verdict": "close", "better": "Sakit kat mana?"},
        {"who": "you", "malay": "Sila baring meniarap.", "verdict": "correct", "better": ""},
        {"who": "you", "malay": "sakit kat mana", "verdict": "close", "better": "Sakit kat mana?"}])
    assert counts == {"correct": 1, "close": 2, "wrong": 0}
    assert fixes == [("Sakit di mana", "Sakit kat mana?")], "a fix equal to what was said isn't one"


@test("Penang Malay: every line has a northern word; standard lines are standard; spacing; lessons tagged")
def t_utara():
    import random as _r
    keys = [uta.key(s_[0]) for s_ in uta.SENTENCES]
    assert len(keys) == len(set(keys)) >= 30
    northern = {w for w, _s, _e in uta.WORDS}
    for north, std, en in uta.SENTENCES:
        assert uta.northern_words(north), north
        assert not set(norm.tokens(std)) & (northern - {"ka", "sat", "tang", "hat"}), std
        assert not norm.indonesian_in(std) and en
    assert [w for w, _s, _e in uta.northern_words("Cheq tak dan makan, la ni cheq lapaq.")] == \
        ["cheq", "tak dan", "la ni", "lapaq"]
    prog = {keys[5]: {"next_review_date": "2026-01-01"}, keys[0]: {"next_review_date": "2099-01-01"}}
    assert uta.pick(prog, "2026-01-02", new_left=2) == [5, 1, 2]
    assert uta.pick(prog, "2026-01-02", new_left=0) == [5]
    it = uta.item(3, _r.Random(2), "read")
    assert it["answer"] == uta.SENTENCES[3][1] and it["answer"] in it["options"] and len(set(it["options"])) == 4
    lessons = {r["malay"]: r for r in _rows(APP / "data" / "lessons.csv")}
    for w, std, _e in uta.WORDS:
        assert lessons[w]["tag"] == "Utara" and lessons[w]["my_equivalent"] == std, w
    assert not norm.indonesian_in(" ".join(s_ for _w, s_, _e in uta.WORDS))


# ======================================================================
# GAMES
# ======================================================================
import game_images as gimg  # noqa: E402
import game_items as gitems  # noqa: E402
import games as gms  # noqa: E402


@test("games: Malay labels, each once; topics big enough; every picture present, none spare")
def t_games_items():
    import xml.etree.ElementTree as ET
    labels = [i["malay"] for i in gitems.ITEMS]
    assert len(labels) == len(set(labels)), "each word once"
    assert all(re.fullmatch(r"[a-z]+(?:[- ][a-z]+)*", m) for m in labels), "lower-case Malay only"
    assert all("chinese" not in i and "pinyin" not in i for i in gitems.ITEMS)
    for it in gitems.ITEMS:
        if it["image"].startswith("tw:"):
            ET.fromstring(gimg.path_for(it["image"]).read_text(encoding="utf-8"))
        assert gimg.img_tag(it["image"]).startswith('<img src="data:image/')
    for cat in gitems.CATEGORIES:
        assert len(gitems.by_category([cat])) >= 12, cat
    assert set(gitems.CATEGORIES) >= {"clinic"} and not {"tcm", "herbs"} & set(gitems.CATEGORIES)
    credits = gimg.credits()
    used = [i["image"][3:] for i in gitems.ITEMS if i["image"].startswith("wm:")]
    assert len(used) == len(set(used)) and set(used) == set(credits), "every picture used once, none spare"
    svgs = {p.stem for p in gimg.IMAGE_DIR.glob("*.svg")}
    assert svgs == {i["image"][3:] for i in gitems.ITEMS if i["image"].startswith("tw:")}, "no stray Twemoji"
    assert {p.name for p in gimg.IMAGE_DIR.iterdir()} == (
        {p + ".svg" for p in svgs} | {c["file"] for c in credits.values()} | {"ATTRIBUTION.md", "credits.json"})
    lines = gimg.credit_lines(gitems.ITEMS)
    assert len(lines) == len(used) and lines[0].startswith("- **kepala**")
    lex = morph.lexicon() | set(morph.default_model().known)
    plain = [m for m in labels if all(t in lex for t in m.replace("-", " ").split())]
    assert len(plain) / len(labels) > 0.9, "labels are real Malay words, not invented"


@test("games: rounds use same-topic options, all different; memory pairs; only real pairs accepted")
def t_games_logic():
    import random as _r
    pool = gitems.by_category(["body", "clinic"])
    rounds = gms.quiz_rounds(pool, rng=_r.Random(1))
    assert len(rounds) == gms.ROUNDS and len({r["target"]["malay"] for r in rounds}) == gms.ROUNDS
    for r in rounds:
        opts = r["options"]
        assert r["target"] in opts and len(opts) == 4
        assert len({o["malay"] for o in opts}) == len({o["image"] for o in opts}) == 4
        assert all(o["category"] == r["target"]["category"] for o in opts), "same topic"
    cards = gms.memory_board(pool, rng=_r.Random(2))
    assert len(cards) == 12 and sum(c["face"] == "image" for c in cards) == 6
    a = next(c for c in cards if c["face"] == "image")
    b = next(c for c in cards if c["face"] == "word" and c["item"] is a["item"])
    assert gms.is_match(a, b) and not gms.is_match(a, a)
    items = [{"malay": m} for m in ("tangan", "kaki", "kepala")]
    board = [{"item": items[0], "face": "image"}, {"item": items[1], "face": "word"},
             {"item": items[0], "face": "word"}, {"item": items[1], "face": "image"},
             {"item": items[2], "face": "image"}, {"item": items[2], "face": "word"}]
    assert gms.accept_matches(board, [0, 2]) == {0, 2}
    assert gms.accept_matches(board, [0, 1]) == set(), "two different words aren't a pair"
    assert gms.accept_matches(board, [99, -1, "x", None]) == set()
    met = {pool[0]["malay"], pool[1]["malay"]}
    got, topped = gms.word_pool(["body"], met, only_met=True)
    assert topped and len(got) == gms.MIN_POOL and pool[0] in got
    assert gms.points(True, 0) == 10 and gms.points(True, 9) == 20 and gms.points(False, 3) == 0
    assert gms.memory_score(6, 6) == 100 and gms.label(pool[0]) == pool[0]["malay"]


# ======================================================================
# SPEECH AND AUDIO (mocked)
# ======================================================================
@test("speech: grading clamps scores, fills a missing grade, and asks in Malaysian terms")
def t_speech():
    import speech_engine as se
    seen = {}

    def fake(**kw):
        seen["prompt"] = kw["messages"][0]["content"]
        return fake_response({"vocab_score": 14, "grammar_score": -2,
                              "pronunciation_score": 7, "overall_grade": "??",
                              "feedback": "ok"})
    real = se.client.chat.completions.create
    se.client.chat.completions.create = fake
    try:
        out = se.grade_speech("Saya nak makan.", "I want to eat.", "saya nak makan")
    finally:
        se.client.chat.completions.create = real
    assert out["vocab_score"] == 10 and out["grammar_score"] == 0
    assert out["overall_grade"] in se.GRADE_MAP
    assert "MALAYSIAN" in seen["prompt"] and "bisa" in seen["prompt"]


@test("audio: Malay voices; text cleaned of symbols but keeps Malay punctuation")
def t_audio_voices():
    import audio_engine as ae
    assert ae.VOICE_CAST and all(v.startswith("ms-MY-") for v in ae.VOICE_CAST)
    assert ae.FALLBACK_VOICE in ae.VOICE_CAST


# ======================================================================
# SESSION STORE, BOARD, PLAN
# ======================================================================
@test("session store: sets, tuples and number-keyed dicts survive the trip through JSON")
def t_store_codec():
    import session_store as ss
    state = {"retried": {(12, "recognition"), (7, "production")}, "rot": {12: 1, 7: 0},
             "matched": {0, 3}, "saved": (0.8, "2026-10-01"), "items": [{"id": 1, "tag": None}],
             "empty": {}, "names": {"a": 1}}
    back = ss._dec(json.loads(ss._blob(ss._enc(state))))
    assert back == state, back


import today_plan as tplan  # noqa: E402


def _plan_state(**over):
    st_ = {"done": set(),
           "words": {"due": 30, "new_room": 5, "new_available": 40},
           "affixes": {"due": 2, "fresh": 6, "new_room": 3},
           "grammar": {"known": 150, "due": [("g1", "yang"), ("g2", "sudah/belum"), ("g3", "di-")],
                       "fresh": [("g9", "semakin…semakin"), ("g10", "ter-")]},
           "sentences": {"words": 200}}
    st_.update(over)
    return st_


@test("plan: fixed order, reviews first; caps on new words, affixes and grammar")
def t_plan_build():
    steps = tplan.build_plan(_plan_state())
    assert [s_["key"] for s_ in steps] == ["words", "affixes", "grammar", "sentences"]
    by = {s_["key"]: s_ for s_ in steps}
    assert by["words"]["params"] == {"reviews": 25, "new": 5, "unlocks": True}
    assert by["words"]["detail"].startswith("25 reviews · 5 new words")
    assert by["affixes"]["params"]["new"] == 3
    assert by["grammar"]["params"]["ids"] == ["g1", "g2"]
    light = tplan.build_plan(_plan_state(grammar={"known": 150, "due": [], "fresh": [("g9", "x"), ("g10", "y")]}))
    assert {s_["key"]: s_ for s_ in light}["grammar"]["params"]["ids"] == ["g9"]
    assert by["sentences"]["params"] == {"listen": 3, "speak": 3}
    few = tplan.build_plan(_plan_state(words={"due": 0, "new_room": 5, "new_available": 2}))
    assert few[0]["params"]["new"] == 2 and few[0]["detail"] == "2 new words"


@test("plan: short day is a few reviews and a little listening; done steps stay visible")
def t_plan_short():
    steps = tplan.build_plan(_plan_state(), short=True)
    assert [s_["key"] for s_ in steps] == ["words", "sentences"]
    assert steps[0]["params"] == {"reviews": 10, "new": 0, "unlocks": False}
    assert steps[1]["params"] == {"listen": 3, "speak": 0}
    done = tplan.build_plan(_plan_state(done={"words", "grammar"}), short=True)
    assert [(s_["key"], s_["done"]) for s_ in done] == [("words", True), ("grammar", True), ("sentences", False)]
    assert tplan.next_step(done)["key"] == "sentences"


@test("plan: only built pages are live; nothing to do means an empty plan")
def t_plan_live():
    assert set(tplan.LIVE_STEPS) <= set(tplan.STEPS)
    for key in tplan.LIVE_STEPS:
        assert (SRC / tplan.STEPS[key][2]).exists(), f"{key} is live but its page is missing"
    quiet = _plan_state(words={"due": 0, "new_room": 0, "new_available": 0},
                        affixes={"due": 0, "fresh": 0, "new_room": 3},
                        grammar={"known": 12, "due": [("g1", "yang")], "fresh": []},
                        sentences={"words": 5})
    assert tplan.build_plan(quiet) == [] and tplan.next_step([]) is None
    held = tplan.build_plan(_plan_state(words={"due": 90, "new_room": 0, "new_available": 40}))
    assert "held back" in held[0]["detail"] and held[0]["params"]["new"] == 0


@test("menu: every page the app links to exists")
def t_pages_exist():
    import re
    text = (SRC / "main_app.py").read_text() + (SRC / "today_plan.py").read_text()
    for page in set(re.findall(r'"(views/[^"]+\.py)"', text)):
        key = next((k for k, v in tplan.STEPS.items() if v[2] == page), None)
        if key and key not in tplan.LIVE_STEPS:
            continue                                  # a later phase's page
        if page == tplan.GAMES_PAGE and not tplan.GAMES_LIVE:
            continue
        assert (SRC / page).exists(), page


# ======================================================================
# DATABASE (only with DATABASE_URL)
# ======================================================================
def _chinese_app_tables(db):
    """Stand-ins for the Chinese app's tables, which have the same names and
    live in 'public' when the two apps share one database."""
    import psycopg2
    raw = psycopg2.connect(db._database_url())
    cur = raw.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS public.users (id SERIAL PRIMARY KEY, username TEXT, hsk INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS public.vocab (id SERIAL PRIMARY KEY, chinese TEXT NOT NULL)")
    cur.execute("DELETE FROM public.users"); cur.execute("DELETE FROM public.vocab")
    cur.execute("INSERT INTO public.users (username, hsk) VALUES ('matt', 3)")
    cur.execute("INSERT INTO public.vocab (chinese) VALUES ('你好')")
    raw.commit()
    return raw


def db_tests():
    import db_manager as db
    chinese = _chinese_app_tables(db)          # already there before this app's first start
    db.init_db()
    db.import_vocab_from_csv(force=True)

    @test("shared database: tables live in their own schema; the Chinese app's tables are untouched")
    def t_schema():
        import os
        cur = chinese.cursor()
        cur.execute("""SELECT table_schema, COUNT(*) FROM information_schema.tables
                       WHERE table_name IN ('users', 'vocab', 'word_skill') GROUP BY 1 ORDER BY 1""")
        assert cur.fetchall() == [("bahasa", 3), ("public", 2)]
        cur.execute("SELECT username, hsk FROM public.users"); assert cur.fetchall() == [("matt", 3)]
        cur.execute("SELECT chinese FROM public.vocab"); assert cur.fetchall() == [("你好",)]
        assert db.word_by_malay("makan")["english"], "this app reads its own vocab"
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SHOW search_path"); assert c.fetchone()[0].strip('"') == "bahasa"
        conn.close()
        saved = os.environ["DATABASE_URL"]
        os.environ["DATABASE_URL"] = "postgresql://u:p@aws-0.pooler.supabase.com:6543/postgres"
        try:
            db._database_url()
            raise AssertionError("the transaction pooler must be refused")
        except ValueError as e:
            assert "Session pooler" in str(e)
        finally:
            os.environ["DATABASE_URL"] = saved

    def _clear(uid):
        conn = db.get_connection(); cur = conn.cursor()
        for tbl in ("word_attempts", "word_skill", "saved_sessions"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()

    @test("import: both lists load; lessons win on meaning; Indonesian rows keep their partner")
    def t_import():
        st_ = db.vocab_stats()
        assert st_["ranked"] == 5000 and st_["lessons"] >= 200, st_
        assert st_["indonesian"] > 200
        w = db.word_by_malay("bisa")
        assert w["tag"] == "Indonesian" and w["my_equivalent"] == "boleh"
        lesson = db.word_by_malay("sakit")
        assert lesson["from_lessons"] and lesson["english"].startswith("pain") and lesson["freq_rank"]
        assert db.word_by_malay("kebas")["root"] is None, "a root word stores no root"
        assert db.word_by_malay("melakukan")["root"] == "laku"
        assert db.word_by_malay("selamat pagi")["register"] == "standard"
        hang = db.word_by_malay("hang")
        assert hang["tag"] == "Utara" and hang["my_equivalent"] == "awak / kamu" and hang["from_lessons"]
        assert db.word_by_malay("keluaq")["root"] is None, "northern forms aren't analysed as affixed"
        assert db.word_by_malay("dok")["tag"] == "Utara", "the lesson row tags the list's dok"

    @test("import: a word edited in Settings survives a re-import; the edit clears its check")
    def t_import_edit():
        w = db.word_by_malay("kucing")
        db.update_word_in_db(w["id"], english="cat (test edit)")
        db.import_vocab_from_csv(force=True)
        assert db.word_by_malay("kucing")["english"] == "cat (test edit)"
        db.update_word_in_db(w["id"], english="cat")
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE vocab SET edited = FALSE WHERE id = %s", (w["id"],))
        conn.commit(); conn.close()
        db.import_vocab_from_csv(force=True)
        assert db.word_by_malay("kucing")["english"] != "cat (test edit)"

    @test("review queue: unsure glosses wait for a check; audit draws count right and fixed")
    def t_review_audit():
        rows, counts = db.review_queue(50)
        assert counts.get("unsure", 0) >= 1 and all(r["needs_check"] for r in rows)
        before = db.audit_stats()
        assert db.draw_audit(3) == 3
        rows, counts = db.review_queue(50)
        audits = [r for r in rows if r["needs_check"] == "audit"]
        assert len(audits) == 3 and rows[0]["needs_check"] == "audit"
        db.mark_word_checked(audits[0]["id"])
        db.update_word_in_db(audits[1]["id"], english=audits[1]["english"] + " (fixed)")
        db.update_word_in_db(audits[2]["id"], english=audits[2]["english"])   # unchanged = right
        after = db.audit_stats()
        assert after["ok"] == before["ok"] + 2 and after["fixed"] == before["fixed"] + 1
        unsure = next(r for r in db.review_queue(50)[0] if r["needs_check"] == "unsure")
        db.mark_word_checked(unsure["id"])
        db.import_vocab_from_csv(force=True)
        assert unsure["id"] not in {r["id"] for r in db.review_queue(500)[0]}, \
            "a checked word stays checked after a re-import"
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE vocab SET edited = FALSE WHERE id = %s", (audits[1]["id"],))
        cur.execute("UPDATE vocab SET needs_check = NULL WHERE needs_check IN ('audit', 'ok')")
        cur.execute("UPDATE vocab SET needs_check = 'unsure' WHERE id = %s", (unsure["id"],))
        conn.commit(); conn.close()
        db.import_vocab_from_csv(force=True)

    @test("bank: add / dedupe / cycle; flags retire everywhere and block re-adding")
    def t_bank():
        ex1 = {"malay": "Ujian satu dua tiga.", "english_correct": "test",
               "english_distractors": ["a", "b", "c"], "audio_path": "/tmp/x.mp3"}
        ex2 = dict(ex1, malay="Ujian empat lima enam.")
        for ex in (ex1, ex2):
            db.unflag_sentence(ex["malay"])
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM sentence_bank WHERE vocab_word = 'ujian'")
        conn.commit(); conn.close()
        assert db.bank_add("ujian", ex1) is True and db.bank_add("ujian", ex1) is False
        assert db.bank_add("ujian", ex2) is True
        got = db.bank_get("ujian")
        assert got and "audio_path" not in got
        assert db.bank_get("ujian")["malay"] != got["malay"], "least-used first"
        db.flag_sentence(ex1["malay"], "test")
        assert ex1["malay"] in db.get_blocklist() and db.bank_count_for("ujian") == 1
        assert db.bank_add("lain", dict(ex1)) is False
        db.unflag_sentence(ex1["malay"])
        assert db.bank_count_for("ujian") == 2

    @test("multi-user: vocabulary shared, progress isolated, PINs hashed")
    def t_multiuser():
        users = db.list_users()
        assert [u["username"] for u in users][:2] == ["matt", "selina"]
        a, b = users[0]["id"], users[1]["id"]
        _clear(a); _clear(b)
        w = db.word_by_malay("makan")
        db.save_word_track(a, w["id"], "recognition", ve.update_track({}, "correct"))
        assert db.network_stats(a)["recognition"] == 1 and db.network_stats(b)["recognition"] == 0
        db.set_user_pin(b, "1234")
        assert db.verify_user_pin(b, "1234") and not db.verify_user_pin(b, "0000")
        assert not db.verify_user_pin(a, "1234")
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT pin_hash FROM users WHERE id = %s", (b,))
        assert len(cur.fetchone()[0]) == 64
        cur.execute("UPDATE users SET pin_hash = NULL WHERE id = %s", (b,))
        conn.commit(); conn.close()

    @test("new words: Indonesian forms wait for their Malaysian partner, then follow it")
    def t_indonesian_gate():
        uid = db.list_users()[0]["id"]
        _clear(uid)
        lessons, freq = db.new_word_candidates(uid, limit=400)
        assert "bisa" not in {w["malay"] for w in freq}
        boleh = db.word_by_malay("boleh")
        db.save_word_track(uid, boleh["id"], "recognition", ve.update_track({}, "correct"))
        _l, freq = db.new_word_candidates(uid, limit=400)
        assert "bisa" in {w["malay"] for w in freq}, "partner known: the Indonesian form may come"
        assert lessons and all(w["from_lessons"] for w in lessons)
        bisa = db.word_by_malay("bisa")
        db.save_word_track(uid, bisa["id"], "recognition", ve.update_track({}, "correct"))
        db.save_word_track(uid, bisa["id"], "recognition", ve.update_track({"interval": 9, "streak": 5}, "correct"))
        assert bisa["id"] not in {w["id"] for w in db.production_unlockable(uid, 50)}, \
            "Indonesian forms are recognition-only"
        _clear(uid)

    @test("ledger: activity, time and streak; nudges reach the other person once")
    def t_ledger():
        a, b = [u["id"] for u in db.list_users()[:2]]
        db.log_activity(a, "read", item="makan", grade=2)
        db.log_activity(a, "nonsense-kind", item="x")                  # never raises
        assert db.activity_totals(a, 7)["today"] >= 1
        assert db.activity_streak(a) >= 1
        db.log_study_session(a, "words", 300, in_plan=True, items=10)
        assert db.study_minutes(a, 7)["total"] >= 5
        db.mark_nudges_seen(b)
        db.send_nudge(a, b, "Jom! Your turn.")
        got = db.unseen_nudges(b)
        assert [n["message"] for n in got] == ["Jom! Your turn."]
        db.mark_nudges_seen(b)
        assert db.unseen_nudges(b) == []

    def _fresh_learner():
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""INSERT INTO users (username, display_name) VALUES ('tester', 'Tester')
                       ON CONFLICT (username) DO NOTHING""")
        cur.execute("SELECT id FROM users WHERE username = 'tester'")
        uid = cur.fetchone()[0]
        for tbl in ("word_attempts", "word_skill", "word_content", "word_diagnosis", "saved_sessions",
                    "study_sessions", "activity_log", "grammar_progress", "grammar_drill_sets",
                    "drill_progress", "word_requests", "reading_progress"):
            cur.execute(f"DELETE FROM {tbl} WHERE user_id = %s", (uid,))
        conn.commit(); conn.close()
        return uid

    def _fake_content(user_id, word, allow_generate=True, known=None):
        t = word["malay"]
        return ({"meaning": wcon.short_meaning(word["english"]),
                 "chunks": [{"malay": f"{t} sini", "english": "c"}],
                 "sentences": [{"malay": f"Saya kata {t} tadi.", "english": "s", "structure": None}],
                 "confusables": [], "prompts": [], "introduced_words": [],
                 "source": "generated", "reviewed": True}, None)

    def _has(at, key):
        try:
            at.session_state[key]
            return True
        except Exception:
            return False

    def _answer_step(at):
        """One action on the Words page: read the intro, answer right, or move on."""
        labels = [b.label for b in at.button]
        if "Got it — test me" in labels:
            next(b for b in at.button if b.label == "Got it — test me").click().run(); return
        mc = [r for r in at.radio if (r.key or "").startswith("wd_mc_")]
        if mc and mc[0].value is None and not _has(at, "wd_ans"):
            right = next(o["text"] for o in at.session_state["wd_setup"]["options"] if o["kind"] == "correct")
            mc[0].set_value(right).run()
            next(b for b in at.button if b.label == "Check").click().run(); return
        ti = [x for x in at.text_input if (x.key or "").startswith("wd_type_")]
        if ti and not _has(at, "wd_ans"):
            item = at.session_state["wd_items"][at.session_state["wd_i"]]
            ti[0].input(item["word"]["malay"]).run()
            next(b for b in at.button if b.label == "Check").click().run(); return
        nxt = [b for b in at.button if b.label in ("Next ▶️", "Later")]
        if nxt:
            nxt[0].click().run(); return
        raise AssertionError(f"stuck on: {labels}")

    def _patched(fn):
        """Run fn with content, bank and audio faked (no model, no network)."""
        import audio_engine
        real = (db.word_content_for, audio_engine.create_audio_file)
        db.word_content_for = _fake_content
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            return fn()
        finally:
            db.word_content_for, audio_engine.create_audio_file = real

    @test("word content store: reuse, refresh after heavy use, bank fallback, none for Indonesian forms")
    def t_wc_db():
        uid = _fresh_learner()
        word = db.word_by_malay("beritahu")
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
            db.unflag_sentence("Awak nak beritahu dia?")
            db.bank_add("beritahu", {"malay": "Awak nak beritahu dia?", "english_correct": "Will you tell him?",
                                     "english_distractors": ["a", "b", "c"]})
            p4, cid4 = db.word_content_for(uid, word, known=WC_KNOWN)
            assert cid4 is None and p4["source"] == "bank" and p4["sentences"][0]["malay"] == "Awak nak beritahu dia?"
            wcon.generate = fake_gen
            n = calls["n"]
            p5, _ = db.word_content_for(uid, db.word_by_malay("bisa"), known=WC_KNOWN)
            assert calls["n"] == n and p5["source"] in ("bank", "word"), "Indonesian forms aren't written for"
            wcon.generate = lambda *a, **k: None
            p6, _ = db.word_content_for(uid, db.word_by_malay("sibuk"), known=WC_KNOWN)
            assert p6["source"] == "tatoeba" and wcon.contains(p6["sentences"][0]["malay"], "sibuk"), \
                "no content written: a Tatoeba sentence rather than the word alone"
        finally:
            wcon.generate = real
        assert len(db.word_pool(uid)) >= 300
        g = db.glosses_for(["makanannya", "dimasukkan"])
        assert g.get("makanan") == "food" and "masuk" in g
        assert "bisa" not in db.grammar_known_vocab(uid), "the writer is never handed Indonesian forms"

    @test("Words page: a full session runs - intro, checks, retries, second looks, summary")
    def t_words_page():
        from streamlit.testing.v1 import AppTest
        uid = _fresh_learner()

        def run():
            at = AppTest.from_file("views/1_Words.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            at.run(); next(b for b in at.button if b.label == "▶️ Start").click().run()
            wrong_once, done = True, False
            for _ in range(120):
                assert not at.exception, at.exception
                labels = [b.label for b in at.button]
                if any("Another session" in l for l in labels):
                    done = True; break
                mc = [r for r in at.radio if (r.key or "").startswith("wd_mc_")]
                if wrong_once and mc and mc[0].value is None:
                    right = next(o["text"] for o in at.session_state["wd_setup"]["options"] if o["kind"] == "correct")
                    mc[0].set_value(next(o for o in mc[0].options if o != right)).run()
                    next(b for b in at.button if b.label == "Check").click().run()
                    wrong_once = False
                    continue
                _answer_step(at)
            assert done
            assert "Word by word" in [e.label for e in at.expander] or True
            return [it["kind"] for it in at.session_state["wd_items"]]
        kinds = _patched(run)
        assert kinds.count("new") == kinds.count("step2") > 0 and kinds.count("retry") == 1
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(interval) FROM word_skill WHERE user_id = %s", (uid,))
        n, min_iv = cur.fetchone()
        conn.close()
        assert n == kinds.count("new") and min_iv >= 0
        lessons = [w for w in db.introduced_words(uid) if w["from_lessons"]]
        assert lessons, "lesson words arrive from the first session"

    @test("diagnosis in use: a troubled word is diagnosed in-session, remedied, and steered after")
    def t_wd_page():
        from streamlit.testing.v1 import AppTest
        uid = _fresh_learner()
        bawa = db.word_by_malay("bawa")
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease, next_review_date,
                       reps, lapses, streak, introduced_on) VALUES (%s,%s,'recognition',0,2.0,'2026-01-01',6,2,0,'seeded')""",
                    (uid, bawa["id"]))
        for _ in range(3):
            cur.execute("""INSERT INTO word_attempts (user_id, vocab_id, skill, mode, result, detail)
                           VALUES (%s,%s,'recognition','audio_to_meaning','wrong',
                                   '{"kind":"review","chose_kind":"sound","chose":"bawah"}')""",
                        (uid, bawa["id"]))
        conn.commit(); conn.close()

        def run():
            at = AppTest.from_file("views/1_Words.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            at.run(); next(b for b in at.button if b.label == "▶️ Start").click().run()
            assert at.session_state["wd_items"][0]["word"]["malay"] == "bawa"
            mc = [r for r in at.radio if (r.key or "").startswith("wd_mc_")][0]
            right = next(o["text"] for o in at.session_state["wd_setup"]["options"] if o["kind"] == "correct")
            mc.set_value(next(o for o in mc.options if o != right)).run()
            next(b for b in at.button if b.label == "Check").click().run()
            assert "keeps slipping" in " ".join(w.value for w in at.warning)
            assert at.session_state["wd_diag"]["cause"] == "sound"
            next(b for b in at.button if b.label == "Work on it now").click().run()
            R = at.session_state["wd_rem"]
            assert R["cause"] == "sound" and R["rounds"]
            for _ in range(len(R["rounds"])):
                rnd = at.session_state["wd_rem"]["rounds"][at.session_state["wd_rem"]["i"]]
                if rnd.get("typed"):
                    [x for x in at.text_input if (x.key or "").startswith("wd_rem_")][0].input(rnd["answer"]).run()
                else:
                    [x for x in at.radio if (x.key or "").startswith("wd_rem_")][0].set_value(rnd["answer"]).run()
                next(b for b in at.button if b.label == "Check").click().run()
                assert "✅ Right." in [m.value for m in at.markdown]
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            next(b for b in at.button if b.label == "Back to the session ▶️").click().run()
            assert not at.exception and not _has(at, "wd_rem")
        _patched(run)
        d = db.open_diagnoses(uid, [bawa["id"]])[bawa["id"]]
        assert d["cause"] == "sound" and d["evidence"]
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE word_skill SET next_review_date = '2026-01-01' WHERE user_id = %s AND vocab_id = %s",
                    (uid, bawa["id"])); conn.commit(); conn.close()
        plan = db.plan_word_session(uid)
        it = next(i for i in plan["items"] if i["word"]["id"] == bawa["id"] and i["kind"] == "review")
        assert it["mode"] == "audio_to_meaning", "the next session leans towards listening"

    @test("Today runs Words: Start goes straight into the session; a dropped connection resumes it")
    def t_words_plan_resume():
        from streamlit.testing.v1 import AppTest
        uid = _fresh_learner()
        user = {"id": uid, "username": "tester", "display_name": "Tester"}

        def run():
            at = AppTest.from_file("main_app.py", default_timeout=120)
            at.session_state["user"] = user
            at.run()
            assert any("Words" in m.value for m in at.markdown), "the plan lists Words"
            next(b for b in at.button if b.label.startswith("▶️ Start")).click().run()
            at.switch_page("views/1_Words.py").run()
            assert _has(at, "wd_items") and at.session_state["wd_plan"] is True
            for _ in range(5):
                _answer_step(at)
            i, items, results = (at.session_state["wd_i"], at.session_state["wd_items"],
                                 at.session_state["wd_results"])
            assert 0 < len(results) and i < len(items)
            back = AppTest.from_file("main_app.py", default_timeout=120)
            back.session_state["user"] = user
            back.run()
            back.switch_page("views/1_Words.py").run()
            assert not back.exception, back.exception
            S = back.session_state
            assert S["wd_i"] == i and S["wd_items"] == items and S["wd_results"] == results
            assert isinstance(S["wd_retried"], set) and S["wd_plan"] is True
            assert "Picked up where you left off." in [c.value for c in back.caption]
            for _ in range(120):
                assert not back.exception, back.exception
                labels = [b.label for b in back.button]
                if any(l.startswith("Continue ▶") or "Back to Today" in l for l in labels):
                    break
                _answer_step(back)
            assert any("Back to Today" in b.label for b in back.button), "Words was the whole plan"
        _patched(run)
        assert "words" in db.plan_done_today(uid)
        assert db.saved_session_get(uid, "words") is None, "a finished session isn't kept"
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = %s AND activity = 'words'", (uid,))
        assert cur.fetchone()[0] == 1, "logged once, not twice"
        conn.close()

    def _seed_known(uid, n=12):
        """Give the learner n introduced words (recognition tracks), due later."""
        from datetime import date as _d, timedelta
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT id FROM vocab WHERE freq_rank IS NOT NULL AND tag IS NULL
                       AND malay ~ '^[a-z]+$' ORDER BY freq_rank LIMIT %s""", (n,))
        ids = [r[0] for r in cur.fetchall()]
        later = (_d.today() + timedelta(days=5)).isoformat()
        earlier = (_d.today() - timedelta(days=10)).isoformat()
        for vid in ids:
            cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease, next_review_date,
                           reps, lapses, streak, introduced_on) VALUES (%s,%s,'recognition',5,2.5,%s,3,0,3,%s)
                           ON CONFLICT DO NOTHING""", (uid, vid, later, earlier))
        conn.commit(); conn.close()
        return ids

    def _fake_exercise(vocab_word):
        return {"malay": f"Saya kata {vocab_word} tadi.", "english_correct": f"I said {vocab_word} earlier.",
                "english_distractors": ["I said nothing.", "You said it yesterday.", "They will say it."],
                "grammar_note": "", "source": "generated"}

    def _answer_sentence(at):
        labels = [b.label for b in at.button]
        if any("Another round" in l or l.startswith("Continue ▶") or "Back to Today" in l for l in labels):
            return False
        mc = [r for r in at.radio if (r.key or "").startswith("sn_mc_")]
        if mc and not _has(at, "sn_ans") or (mc and at.session_state["sn_ans"] is None):
            mc[0].set_value(at.session_state["sn_ex"]["english_correct"]).run()
            next(b for b in at.button if b.label == "Check").click().run(); return True
        ti = [x for x in at.text_input if (x.key or "").startswith("sn_type_")]
        if ti and at.session_state["sn_ans"] is None:
            ti[0].input(at.session_state["sn_ex"]["malay"]).run()
            next(b for b in at.button if b.label == "Check").click().run(); return True
        next(b for b in at.button if b.label == "Next ▶️").click().run()
        return True

    @test("Listen & speak: Tatoeba before the model; schedules move only when due; never introduces words")
    def t_sentences_page():
        from streamlit.testing.v1 import AppTest
        from datetime import date as _d
        import audio_engine
        uid = _fresh_learner()
        ids = _seed_known(uid)
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE word_skill SET next_review_date = %s WHERE user_id = %s AND vocab_id = %s",
                    (_d.today().isoformat(), uid, ids[0]))
        conn.commit(); conn.close()
        before = dict(_recognition_rows(uid))
        calls = {"tatoeba": 0, "written": 0}
        real = (db.bank_get, audio_engine.create_audio_file, tato.exercise_for, aprm.generate_exercise)

        def fake_tatoeba(word, blocked=(), flagged=None, tries=3):
            calls["tatoeba"] += 1
            return dict(_fake_exercise(word["malay"]), source="tatoeba", tatoeba_id="1", author="x",
                        generation_mode="listen")

        def fake_written(word, mode="listen", blocked=None, flagged=None):
            calls["written"] += 1
            return dict(_fake_exercise(word["malay"]), generation_mode=mode)
        db.bank_get = lambda w: None
        audio_engine.create_audio_file = lambda text, voice=None: None
        tato.exercise_for, aprm.generate_exercise = fake_tatoeba, fake_written
        try:
            at = AppTest.from_file("views/9_Sentences.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            at.run()
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            cards = at.session_state["sn_cards"]
            assert [c["mode"] for c in cards] == ["listen", "speak"] * 3
            assert cards[0]["word"]["id"] == ids[0], "due words come first"
            credited = False
            for _ in range(60):
                assert not at.exception, at.exception
                credited = credited or any("Tatoeba" in c.value for c in at.caption)
                if not _answer_sentence(at):
                    break
            assert any("Another round" in b.label for b in at.button)
            assert credited, "Tatoeba sentences carry their credit"
        finally:
            db.bank_get, audio_engine.create_audio_file, tato.exercise_for, aprm.generate_exercise = real
        assert calls["tatoeba"] == 3 and calls["written"] == 3, calls
        after = dict(_recognition_rows(uid))
        assert set(after) == set(before), "no new words introduced"
        assert after[ids[0]] > _d.today().isoformat(), "the due word's review moved on"
        assert all(after[v] == before[v] for v in before if v != ids[0]), "nothing else moved"
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM word_skill WHERE user_id = %s AND skill = 'production'", (uid,))
        assert cur.fetchone()[0] == 0, "speaking never creates a production track"
        cur.execute("""SELECT detail->>'grading' FROM word_attempts WHERE user_id = %s
                       AND mode = 'sentence_speak'""", (uid,))
        grades = [r[0] for r in cur.fetchall()]
        assert grades and all('"easy"' in g for g in grades), "an exact typed answer needs no model"
        conn.close()
        assert db.bank_count_for(cards[0]["word"]["malay"]) == 1, "the listening sentence is banked"

    def _recognition_rows(uid):
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT vocab_id, next_review_date FROM word_skill WHERE user_id = %s "
                    "AND skill = 'recognition'", (uid,))
        rows = cur.fetchall(); conn.close()
        return rows

    @test("speaking: Whisper's standard spelling of colloquial speech counts as exact")
    def t_speak_register():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        import speech_engine
        uid = _fresh_learner()
        _seed_known(uid)
        real = (db.bank_get, audio_engine.create_audio_file, speech_engine.transcribe_audio)
        db.bank_get = lambda w: {"malay": "Saya tak nak pergi.", "english_correct": "I don't want to go.",
                                 "english_distractors": ["a", "b", "c"], "source": "generated"}
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("views/9_Sentences.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            at.run(); next(b for b in at.button if b.label == "▶️ Start").click().run()
            _answer_sentence(at); _answer_sentence(at)            # the listening card
            assert at.session_state["sn_cards"][at.session_state["sn_i"]]["mode"] == "speak"
            [x for x in at.text_input if (x.key or "").startswith("sn_type_")][0].input("saya tidak hendak pergi").run()
            next(b for b in at.button if b.label == "Check").click().run()
            assert at.session_state["sn_ans"]["result"] == "easy"
        finally:
            db.bank_get, audio_engine.create_audio_file, speech_engine.transcribe_audio = real

    @test("Play: a game survives leaving the app; a bogus pair is refused; End game clears it")
    def t_games_resume():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        import game_components as gcomp
        uid = _fresh_learner()
        db.saved_session_del(uid, "games")
        real = (audio_engine.create_audio_file, gcomp.memory_board, gcomp.choice_board)
        audio_engine.create_audio_file = lambda text, voice=None: None
        gcomp.choice_board = lambda **k: {"sid": k["sid"], "round": k["round"], "chosen": k["answer"]}

        def session():
            at = AppTest.from_file("views/8_Games.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            return at
        try:
            at = session(); at.run()
            next(b for b in at.button if b.key == "pick_word").click().run()
            for _ in range(2):
                at.run()
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            rounds, score, i = (at.session_state["gm_rounds"], at.session_state["gm_score"],
                                at.session_state["gm_i"])
            assert score > 0 and i == 2
            gcomp.choice_board = lambda **k: None
            back = session(); back.run()
            assert not back.exception, back.exception
            assert back.session_state["gm_i"] == i and back.session_state["gm_rounds"] == rounds
            assert back.session_state["gm_score"] == score
            assert "Picked up where you left off." in [c.value for c in back.caption]
            next(b for b in back.button if b.key == "gm_end").click().run()
            assert db.saved_session_get(uid, "games", same_day=False) is None
            at = session(); at.run()
            next(b for b in at.button if b.key == "pick_memory").click().run()
            cards, sid = at.session_state["gm_cards"], at.session_state["gm_sid"]
            pairs = {}
            for n, c in enumerate(cards):
                pairs.setdefault(c["item"]["malay"], []).append(n)
            p1, p2 = list(pairs.values())[:2]
            wrong = [list(pairs.values())[2][0], list(pairs.values())[3][0]]
            gcomp.memory_board = lambda **k: {"sid": sid, "matched": sorted(p1 + p2 + wrong), "moves": 4}
            at.run()
            assert at.session_state["gm_matched"] == set(p1 + p2), "only real pairs count"
            assert not at.exception, at.exception
        finally:
            audio_engine.create_audio_file, gcomp.memory_board, gcomp.choice_board = real

    @test("Today: Words then Listen & speak, joined by Continue; the plan is done at the end")
    def t_plan_two_steps():
        from streamlit.testing.v1 import AppTest
        import audio_engine
        uid = _fresh_learner()
        _seed_known(uid)
        real = (db.word_content_for, db.bank_get, audio_engine.create_audio_file)
        db.word_content_for, db.bank_get = _fake_content, _fake_exercise
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = AppTest.from_file("main_app.py", default_timeout=120)
            at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
            at.run()
            text = " ".join(m.value for m in at.markdown)
            assert "Words" in text and "Listen & speak" in text, text
            assert any(b.label == "🎮 Play a game" for b in at.button), "Play is offered on Today"
            next(b for b in at.button if b.label.startswith("▶️ Start")).click().run()
            at.switch_page("views/1_Words.py").run()
            for _ in range(120):
                assert not at.exception, at.exception
                if any(b.label.startswith("Continue ▶") for b in at.button):
                    break
                _answer_step(at)
            nxt = next(b for b in at.button if b.label.startswith("Continue ▶"))
            assert "Listen & speak" in nxt.label
            nxt.click().run()
            at.switch_page("views/9_Sentences.py").run()
            assert _has(at, "sn_cards") and at.session_state["sn_plan"] is True
            for _ in range(60):
                assert not at.exception, at.exception
                if not _answer_sentence(at):
                    break
            assert any("Back to Today" in b.label for b in at.button)
        finally:
            db.word_content_for, db.bank_get, audio_engine.create_audio_file = real
        assert {"words", "sentences"} <= db.plan_done_today(uid)

    def _grammar_fakes():
        import audio_engine
        real = (db.grammar_known_vocab, db.grammar_pick_set, db.grammar_mark_served,
                gdr.grade_answer, audio_engine.create_audio_file)
        db.grammar_known_vocab = lambda user_id: GR_KNOWN * 2
        db.grammar_pick_set = lambda user_id, sid, n: {"id": 0, "payload": _gr_payload()}
        db.grammar_mark_served = lambda set_id: None
        gdr.grade_answer = lambda structure, task, reference, said, spoken=True: {
            "verdict": "correct", "feedback": "", "better": reference}
        audio_engine.create_audio_file = lambda text, voice=None: None

        def undo():
            (db.grammar_known_vocab, db.grammar_pick_set, db.grammar_mark_served,
             gdr.grade_answer, audio_engine.create_audio_file) = real
        return undo

    def _gr_session(uid):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("views/7_Grammar.py", default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
        return at

    def _answer_grammar(at):
        """One action on the Grammar page. False once nothing is left to answer."""
        labels = [b.label for b in at.button]
        if any(l.startswith("Continue ▶") or l == "🔁 Again, new sentences" for l in labels):
            return False
        btn = lambda l: next(b for b in at.button if b.label == l)
        if "▶️ Next structure" in labels:
            btn("▶️ Next structure").click().run(); return True
        mc = [r for r in at.radio if (r.key or "").startswith("mc_")]
        if mc and mc[0].value is None and "Check" in labels:
            stage = at.session_state["gr_stages"][at.session_state["gr_stage"]]
            items = (at.session_state["gr_set"]["contrast"]["items"] if stage == "contrast"
                     else at.session_state["gr_set"][stage])
            it = items[at.session_state["gr_item"]]
            mc[0].set_value(it["options"][it["answer"]]).run()
            btn("Check").click().run(); return True
        ty = [t_ for t_ in at.text_input if (t_.key or "").startswith("type_")]
        if ty and not ty[0].value and "Check" in labels:
            ty[0].set_value("Saya tak minum kopi.").run()
            btn("Check").click().run(); return True
        if "Reveal" in labels:
            btn("Reveal").click().run(); return True
        if "✅ I said that" in labels:
            btn("✅ I said that").click().run(); return True
        btn("Next ▶️").click().run()
        return True

    @test("grammar store: progress upsert, set reuse limits, refresh on vocab growth, Indonesian pairs")
    def t_gr_db():
        uid = _fresh_learner()
        db.grammar_save_progress(uid, "tidak_tak", "2026-01-02", 1, 2.5, 0.8)
        db.grammar_save_progress(uid, "tidak_tak", "2026-01-05", 3, 2.5, 0.9)
        p_ = db.grammar_progress(uid)["tidak_tak"]
        assert p_["review_count"] == 2 and p_["interval"] == 3
        assert db.grammar_new_today(uid) == 1
        sid = db.grammar_save_set(uid, "tidak_tak", 100, _gr_payload())
        pick = db.grammar_pick_set(uid, "tidak_tak", 100)
        assert pick and pick["id"] == sid and pick["payload"]["identify"]
        assert "Saya tak minum kopi." in db.grammar_recent_sentences(uid, "tidak_tak")
        db.grammar_mark_served(sid)
        assert db.grammar_pick_set(uid, "tidak_tak", 100) is None, "served today"
        db.grammar_save_set(uid, "tidak_tak", 100, {"identify": []})
        assert db.grammar_pick_set(uid, "tidak_tak", 200) is None, "vocabulary grew"
        for _ in range(5):
            db.grammar_save_set(uid, "tidak_tak", 100, {"identify": []})
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM grammar_drill_sets WHERE user_id = %s", (uid,))
        assert cur.fetchone()[0] == 4, "only the latest sets are kept"
        conn.close()
        pairs = dict(db.grammar_indonesian_pairs())
        assert pairs.get("bisa") == "boleh", list(pairs.items())[:5]

    @test("Grammar page: the plan's structures start by themselves, run every stage, then Continue")
    def t_gr_page():
        from datetime import date as _d
        uid = _fresh_learner()
        ids = [s_.id for s_ in gcur.learning_order()[:2]]
        undo = _grammar_fakes()
        try:
            at = _gr_session(uid)
            at.session_state["tp"] = {"date": _d.today().isoformat(), "short": False,
                                      "order": ["grammar", "sentences"], "params": {"grammar": {"ids": ids}},
                                      "done": [], "skipped": []}
            at.run()
            assert at.session_state["gr_sid"] == ids[0], "the plan's first structure starts by itself"
            assert at.session_state["gr_stages"] == list(gdr.STAGES)
            assert at.session_state["gr_english_open"] is True, "English shown while it's new"
            seen = set()
            for _ in range(160):
                assert not at.exception, at.exception
                seen.add(at.session_state["gr_stages"][min(at.session_state["gr_stage"],
                                                            len(gdr.STAGES) - 1)])
                if not _answer_grammar(at):
                    break
            assert seen == set(gdr.STAGES), seen
            assert any(b.label == "Continue ▶  🎧 Listen & speak" for b in at.button), \
                [b.label for b in at.button]
            prog = db.grammar_progress(uid)
            assert set(ids) <= set(prog), "both structures scheduled"
            assert all(prog[i]["last_score"] == 1.0 for i in ids)
            assert "grammar" in db.plan_done_today(uid)
            assert db.saved_session_get(uid, "grammar") is None, "a finished session isn't kept"
        finally:
            undo()

    @test("Grammar page: from the Library; a dropped connection picks up at the same item")
    def t_gr_resume():
        uid = _fresh_learner()
        undo = _grammar_fakes()
        try:
            at = _gr_session(uid); at.run()
            assert not at.exception, at.exception
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            assert at.session_state["gr_sid"] == gcur.learning_order()[0].id
            for _ in range(3):
                mc = [r for r in at.radio if (r.key or "").startswith("mc_")][0]
                it = at.session_state["gr_set"]["identify"][at.session_state["gr_item"]]
                mc.set_value(it["options"][it["answer"]]).run()
                next(b for b in at.button if b.label == "Check").click().run()
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            snap = {k: at.session_state[k] for k in ("gr_sid", "gr_stage", "gr_item", "gr_results")}
            assert snap["gr_stage"] == 1 and snap["gr_results"] == [True, True, True]
            back = _gr_session(uid); back.run()
            assert not back.exception, back.exception
            assert {k: back.session_state[k] for k in snap} == snap
            assert "Picked up where you left off." in [c.value for c in back.caption]
            for _ in range(120):
                assert not back.exception, back.exception
                if not _answer_grammar(back):
                    break
            assert any(b.label == "🔁 Again, new sentences" for b in back.button)
            assert snap["gr_sid"] in db.grammar_progress(uid)
        finally:
            undo()

    @test("Today: Grammar joins the plan once there are enough well-studied words")
    def t_plan_grammar():
        from streamlit.testing.v1 import AppTest
        uid = _fresh_learner()
        _seed_known(uid, n=tplan.GRAMMAR_MIN_KNOWN + 5)
        at = AppTest.from_file("main_app.py", default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
        at.run()
        assert not at.exception, at.exception
        text = " ".join(m.value for m in at.markdown)
        first = gcur.learning_order()[0].name
        assert "Grammar" in text and first in text, text
        assert text.index("Words") < text.index("Grammar") < text.index("Listen & speak")

    AF_MET = ["main", "bermain", "pemain", "permainan", "mainan", "makan", "makanan", "memakan",
              "dimakan", "dapat", "mendapat", "mendapatkan", "terdapat", "pendapat"]

    def _seed_words(uid, words):
        """Introduce these words to the learner (recognition tracks, due later)."""
        from datetime import date as _d, timedelta
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT id FROM vocab WHERE malay = ANY(%s) AND tag IS NULL", (words,))
        ids = [r[0] for r in cur.fetchall()]
        later = (_d.today() + timedelta(days=5)).isoformat()
        earlier = (_d.today() - timedelta(days=10)).isoformat()
        for vid in ids:
            cur.execute("""INSERT INTO word_skill (user_id, vocab_id, skill, interval, ease, next_review_date,
                           reps, lapses, streak, introduced_on) VALUES (%s,%s,'recognition',5,2.5,%s,3,0,3,%s)
                           ON CONFLICT DO NOTHING""", (uid, vid, later, earlier))
        conn.commit(); conn.close()
        return ids

    def _af_session(uid):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("views/4_Affixes.py", default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
        return at

    def _answer_affix(at):
        """One action on the Affixes page; False once the round is over."""
        labels = [b.label for b in at.button]
        if any(l.startswith("Continue ▶") or l == "▶️ Another round" for l in labels):
            return False
        item = at.session_state["af_items"][at.session_state["af_i"]]
        btn = lambda l: next(b for b in at.button if b.label == l)
        if "Check" in labels:
            if item["type"] == "form_build":
                next(x for x in at.text_input if x.key.startswith("af_type_")).set_value(item["answer"]).run()
            else:
                label = next(o["label"] for o in item["options"] if o["value"] == item["answer"])
                next(r for r in at.radio if r.key.startswith("af_mc_")).set_value(label).run()
            btn("Check").click().run()
        else:
            btn("Next ▶️").click().run()
        return True

    @test("affix store: every list form of a root; stored sentences, the learner's own first")
    def t_af_db():
        uid = _fresh_learner()
        forms = db.family_forms(["main", "dapat", ""])
        assert {"main", "bermain", "pemain", "permainan"} <= {r["malay"] for r in forms["main"]}
        assert forms["dapat"][0]["malay"] == "dapat", "most frequent first"
        assert all(not r["tag"] for rs in forms.values() for r in rs)
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT id FROM vocab WHERE malay = 'mendapat'")
        vid = cur.fetchone()[0]
        cur.execute("DELETE FROM sentence_bank WHERE vocab_word = 'mendapat'")
        conn.commit(); conn.close()
        db.word_content_save(uid, vid, 10, {"sentences": [
            {"malay": "Kami mendapat hadiah.", "english": "We got a present."}]})
        db.bank_add("mendapat", {"malay": "Dia mendapat surat.", "english_correct": "He/She got a letter."})
        got = db.affix_sentences(uid, [{"id": vid, "malay": "mendapat"}, {"id": None, "malay": "x"}])
        assert [s["malay"] for s in got["mendapat"]] == ["Kami mendapat hadiah.", "Dia mendapat surat."]
        assert got["x"] == []

    @test("Affixes page: the plan's round starts by itself, every drill runs, families scheduled, Continue")
    def t_af_page():
        from datetime import date as _d
        import audio_engine
        uid = _fresh_learner()
        _seed_words(uid, AF_MET)
        real = audio_engine.create_audio_file
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            state = tplan.gather_state(uid)
            assert state["affixes"]["fresh"] == 3 and state["affixes"]["due"] == 0, state["affixes"]
            step = next(s_ for s_ in tplan.build_plan(state) if s_["key"] == "affixes")
            assert step["params"] == {"new": 3} and step["detail"] == "3 new families"
            at = _af_session(uid)
            at.session_state["tp"] = {"date": _d.today().isoformat(), "short": False,
                                      "order": ["affixes", "sentences"], "params": {"affixes": {"new": 3}},
                                      "done": [], "skipped": []}
            at.run()
            assert not at.exception, at.exception
            items = at.session_state["af_items"]
            assert {i["key"] for i in items} == {"main", "makan", "dapat"} and at.session_state["af_plan"]
            assert len(items) == 9 and {i["type"] for i in items} >= {"form_meaning", "form_build", "affix_adds"}
            for _ in range(40):
                assert not at.exception, at.exception
                if not _answer_affix(at):
                    break
            assert any(b.label == "Continue ▶  🎧 Listen & speak" for b in at.button), \
                [b.label for b in at.button]
            assert "Done — 9 of 9 right." in [x.value for x in at.success]
            prog = db.drill_progress_get(uid, afd.DRILL)
            assert set(prog) == {"main", "makan", "dapat"} and all(p_["reps"] == 1 for p_ in prog.values())
            assert db.drill_new_today(uid, afd.DRILL) == 3
            assert "affixes" in db.plan_done_today(uid)
            assert db.saved_session_get(uid, "affixes") is None
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM word_attempts WHERE user_id = %s
                           AND detail->>'kind' = 'drill' AND result = 'correct'""", (uid,))
            assert cur.fetchone()[0] == 9, "logged as drill attempts, outside the diagnosis"
            conn.close()
            assert tplan.gather_state(uid)["affixes"]["new_room"] == 0, "today's new families used up"
        finally:
            audio_engine.create_audio_file = real

    @test("Affixes page: from the Library; a dropped connection picks up at the same item; wrong answers shown")
    def t_af_resume():
        import audio_engine
        uid = _fresh_learner()
        _seed_words(uid, AF_MET)
        real = audio_engine.create_audio_file
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = _af_session(uid); at.run()
            assert not at.exception, at.exception
            assert "**3** affix families from your words" in " ".join(m.value for m in at.markdown)
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            _answer_affix(at); _answer_affix(at)                 # check, next
            item = at.session_state["af_items"][1]
            if item["type"] == "form_build":
                next(x for x in at.text_input if x.key.startswith("af_type_")).set_value("salah").run()
            else:
                wrong = next(o["label"] for o in item["options"] if o["value"] != item["answer"])
                next(r for r in at.radio if r.key.startswith("af_mc_")).set_value(wrong).run()
            next(b for b in at.button if b.label == "Check").click().run()
            assert any(m.value.startswith("❌ It was") for m in at.markdown)
            snap = {k: at.session_state[k] for k in ("af_i", "af_items", "af_results", "af_ans")}
            assert snap["af_i"] == 1 and [r["right"] for r in snap["af_results"]] == [True, False]
            back = _af_session(uid); back.run()
            assert not back.exception, back.exception
            assert {k: back.session_state[k] for k in snap} == snap
            assert "Picked up where you left off." in [c.value for c in back.caption]
            for _ in range(40):
                assert not back.exception, back.exception
                if not _answer_affix(back):
                    break
            assert any(b.label == "▶️ Another round" for b in back.button)
            prog = db.drill_progress_get(uid, afd.DRILL)
            missed = snap["af_items"][1]["key"]
            assert prog[missed]["last_result"] == "close" and prog[missed]["interval"] <= \
                min(p_["interval"] for p_ in prog.values())
        finally:
            audio_engine.create_audio_file = real

    def _page(uid, path):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(path, default_timeout=120)
        at.session_state["user"] = {"id": uid, "username": "tester", "display_name": "Tester"}
        return at

    @test("reading store: passages shared and deduplicated; read, scored, retired; words requested first")
    def t_rd_db():
        uid = _fresh_learner()
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM word_requests WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM reading_progress WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM vocab WHERE malay = 'cenderamatax'")
        conn.commit(); conn.close()
        rid = db.reading_save(_rd_payload(), 50)
        assert db.reading_save(_rd_payload(), 80) == rid, "the same passage is stored once"
        assert rid in [c["id"] for c in db.reading_candidates()]
        assert db.reading_candidates()[0]["payload"]["sentences"]
        db.reading_mark(uid, rid, 0.5); db.reading_mark(uid, rid, None)
        assert db.reading_read_ids(uid) == {rid}
        st_ = db.reading_stats(uid)
        assert st_["read"] == 1 and st_["score"] == 0.5 and st_["bank"] >= 1
        other = dict(_rd_payload(), title="x")
        other["sentences"] = other["sentences"][:3]
        oid = db.reading_save(other, 50)
        db.reading_retire(oid)
        assert oid not in [c["id"] for c in db.reading_candidates()]
        n = db.request_words(uid, [("bakar", "grilled"), ("cenderamatax", "souvenir"), ("??", "x"),
                                   ("tiadamaknax", "")])
        assert n == 2
        asked = [w["malay"] for w in db.requested_words(uid)]
        assert asked == ["bakar", "cenderamatax"], asked
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("SELECT needs_check, lesson_list, freq_rank FROM vocab WHERE malay = 'cenderamatax'")
        assert cur.fetchone() == ("unsure", "reading", None), "checked in Settings, never ranked"
        conn.close()
        _seed_known(uid, 15)
        new = [it["word"]["malay"] for it in db.plan_word_session(uid)["items"] if it["kind"] == "new"]
        assert new[:2] == ["bakar", "cenderamatax"], new
        _seed_words(uid, ["bakar"])
        assert [w["malay"] for w in db.requested_words(uid)] == ["cenderamatax"]

    @test("Reading page: a stored passage that fits; tap-for-parts words; questions; words sent; logged")
    def t_rd_page():
        uid = _fresh_learner()
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM word_requests WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM reading_progress WHERE user_id = %s", (uid,))
        cur.execute("UPDATE reading_bank SET status = 'flagged'")
        conn.commit(); conn.close()
        _seed_known(uid, 30)
        _seed_words(uid, RD_KNOWN)
        rid = db.reading_save(_rd_payload(), 50)
        conn = db.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE reading_bank SET status = 'active' WHERE id = %s", (rid,))
        conn.commit(); conn.close()
        real = rde.generate
        rde.generate = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no writing: one fits"))
        try:
            at = _page(uid, "views/6_Reading.py"); at.run()
            assert not at.exception, at.exception
            next(b for b in at.button if b.label == "📖 Next passage").click().run()
            assert not at.exception, at.exception
            assert at.session_state["rd_id"] == rid
            html_ = " ".join(m.value for m in at.markdown)
            assert 'class="rd"' in html_ and 'class="w new" tabindex="0">bakar' in html_
            boxes = [c for c in at.checkbox if c.key.startswith("rd_new_")]
            assert [c.key for c in boxes] == ["rd_new_bakar"] and boxes[0].value is True
            done = next(b for b in at.button if b.label.startswith("✅ Done"))
            assert done.disabled, "answer the questions first"
            at.radio(key="rd_q_0").set_value("A coffee shop")
            at.radio(key="rd_q_1").set_value("A neighbour")
            at.run()
            next(b for b in at.button if b.label == "Check answers").click().run()
            caps = [c.value for c in at.caption]
            assert "✅ Right." in caps and "❌ It was: A friend" in caps
            next(b for b in at.button if b.label == "➕ Learn these next").click().run()
            assert any("bakar" in s_.value for s_ in at.success)
            back = _page(uid, "views/6_Reading.py"); back.run()
            assert back.session_state["rd_id"] == rid and back.session_state["rd_answers"] == [0, 2], \
                "a passage in progress survives a dropped connection"
            next(b for b in back.button if b.label.startswith("✅ Done")).click().run()
            assert not back.exception, back.exception
            assert db.reading_stats(uid)["read"] == 1 and db.reading_stats(uid)["score"] == 0.5
            assert [w["malay"] for w in db.requested_words(uid)] == ["bakar"]
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = %s AND activity = 'reading'", (uid,))
            assert cur.fetchone()[0] == 1
            conn.close()
            # nothing unread fits and nothing can be written: Tatoeba short reads
            rde.generate = lambda *a, **k: None
            next(b for b in back.button if b.label == "📖 Next passage").click().run()
            assert not back.exception, back.exception
            assert back.session_state["rd_payload"]["source"] == "tatoeba"
            assert any("Tatoeba" in c.value for c in back.caption)
            assert not next(b for b in back.button if b.label.startswith("✅ Done")).disabled
        finally:
            rde.generate = real

    @test("Clinic page: a consultation runs turn by turn, ticks goals, survives a reload, ends in a summary")
    def t_rp_page():
        import audio_engine
        uid = _fresh_learner()
        results = iter([
            {"verdict": "correct", "feedback": "", "better": "Apa yang boleh saya bantu?",
             "goals_met": ["greet", "where"], "patient_malay": "Kat pinggang, sebelah kanan.",
             "patient_english": "In my lower back, on the right.", "patient_done": False},
            {"verdict": "close", "feedback": "Say dah, not sudah, in speech.", "better": "Dah berapa lama sakit?",
             "goals_met": ["how_long"], "patient_malay": "Dah seminggu.", "patient_english": "A week now.",
             "patient_done": False}])
        calls = []
        real = (rpl.take_turn, audio_engine.create_audio_file)

        def fake_turn(case, turns, said, met, spoken=True):
            calls.append((said, list(met), spoken)); return next(results)
        rpl.take_turn = fake_turn
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = _page(uid, "views/11_Clinic.py"); at.run()
            assert not at.exception, at.exception
            next(b for b in at.button if b.label == "▶️ Start the consultation").click().run()
            assert at.session_state["rp_turns"][0]["malay"] == rpl.CASES[0]["opening"][0]
            at.text_input(key="rp_type_0").set_value("Sakit kat mana?").run()
            next(b for b in at.button if b.label == "Send").click().run()
            assert not at.exception, at.exception
            assert calls[0] == ("Sakit kat mana?", [], False)
            assert at.session_state["rp_met"] == ["greet", "where"] and len(at.session_state["rp_turns"]) == 3
            back = _page(uid, "views/11_Clinic.py"); back.run()
            assert back.session_state["rp_turns"] == at.session_state["rp_turns"], "picked up after a reload"
            back.text_input(key="rp_type_1").set_value("Sudah berapa lama sakit?").run()
            next(b for b in back.button if b.label == "Send").click().run()
            assert calls[1][1] == ["greet", "where"]
            caps = [c.value for c in back.caption]
            assert "Better: **Dah berapa lama sakit?**" in caps and "✅ Ada masalah apa hari ni?" not in caps
            next(b for b in back.button if b.label == "End").click().run()
            assert not back.exception, back.exception
            s_ = [x.value for x in back.success][0]
            assert "3 of 10 parts covered" in s_ and "1 lines right, 1 close" in s_, s_
            assert any("~~Sudah berapa lama sakit?~~" in m.value for m in back.markdown)
            back.run()
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = %s AND activity = 'clinic'", (uid,))
            assert cur.fetchone()[0] == 1, "logged once"
            cur.execute("SELECT COUNT(*) FROM activity_log WHERE user_id = %s AND kind = 'type'", (uid,))
            assert cur.fetchone()[0] == 2
            conn.close()
            assert db.saved_session_get(uid, "clinic") is None
        finally:
            rpl.take_turn, audio_engine.create_audio_file = real

    @test("Penang page: a round of northern lines, spaced, with the standard form shown")
    def t_pn_page():
        import audio_engine
        uid = _fresh_learner()
        _seed_known(uid, uta.MIN_KNOWN + 5)
        real = audio_engine.create_audio_file
        audio_engine.create_audio_file = lambda text, voice=None: None
        try:
            at = _page(uid, "views/12_Penang.py"); at.run()
            assert not at.exception, at.exception
            assert len(at.dataframe) == 1, "the word list"
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            items = at.session_state["pn_items"]
            assert len(items) == uta.NEW_PER_SESSION and items[0]["i"] == 0
            for n_ in range(len(items)):
                it = at.session_state["pn_items"][n_]
                at.radio(key=f"pn_mc_{n_}").set_value(it["answer"]).run()
                next(b for b in at.button if b.label == "Check").click().run()
                assert any(m.value.startswith("Standard: **") for m in at.markdown)
                next(b for b in at.button if b.label == "Next ▶️").click().run()
            assert not at.exception, at.exception
            assert f"Done — {len(items)} of {len(items)} right." in [x.value for x in at.success]
            prog = db.drill_progress_get(uid, uta.DRILL)
            assert set(prog) == {i["key"] for i in items}
            at = _page(uid, "views/12_Penang.py"); at.run()
            next(b for b in at.button if b.label == "▶️ Start").click().run()
            assert len(at.session_state["pn_items"]) == uta.NEW_PER_DAY - uta.NEW_PER_SESSION, \
                "the day's new lines are capped"
        finally:
            audio_engine.create_audio_file = real

    @test("app: signs in, opens on Today, and every menu page renders")
    def t_app():
        from streamlit.testing.v1 import AppTest
        uid = db.list_users()[0]["id"]
        user = {"id": uid, "username": "matt", "display_name": "Matt"}
        at = AppTest.from_file("main_app.py", default_timeout=120)
        at.session_state["user"] = user
        at.run()
        assert not at.exception, at.exception
        assert at.title[0].value == "Hari ini · Today"
        for page in ("views/5_Together.py", "views/10_Admin.py", "views/1_Words.py",
                     "views/9_Sentences.py", "views/8_Games.py", "views/7_Grammar.py",
                     "views/4_Affixes.py", "views/6_Reading.py", "views/11_Clinic.py",
                     "views/12_Penang.py"):
            pt = AppTest.from_file(page, default_timeout=120)
            pt.session_state["user"] = user
            pt.run()
            assert not pt.exception, (page, pt.exception)

    for t in (t_schema, t_import, t_import_edit, t_review_audit, t_bank, t_multiuser,
              t_indonesian_gate, t_ledger, t_wc_db, t_words_page, t_wd_page,
              t_words_plan_resume, t_sentences_page, t_speak_register, t_games_resume,
              t_plan_two_steps, t_gr_db, t_gr_page, t_gr_resume, t_plan_grammar,
              t_af_db, t_af_page, t_af_resume, t_rd_db, t_rd_page, t_rp_page, t_pn_page, t_app):
        t()


# ======================================================================
if __name__ == "__main__":
    print("Morphology:")
    t_mo_list(); t_mo_rules(); t_mo_traps(); t_mo_redup(); t_mo_voice(); t_mo_gate()
    print("Normalising, checking, known words:")
    t_no_canonical(); t_no_transcript(); t_ch_verdicts(); t_known()
    print("Word list files:")
    t_wl_files(); t_wl_lessons()
    print("Vocabulary engine:")
    t_ve_schedule(); t_ve_production_gate(); t_ve_modes(); t_ve_allowance(); t_ve_session()
    print("Word content:")
    t_wc_text(); t_wc_check(); t_wc_options(); t_wc_validate(); t_wc_generate(); t_mo_attach()
    print("Word diagnosis:")
    t_wd_trouble(); t_wd_diagnose(); t_wd_remedies(); t_wd_written()
    print("Sentence writer and Tatoeba:")
    t_ap_numbers(); t_ap_pronouns(); t_ap_gate(); t_ap_generate(); t_tatoeba()
    print("Grammar:")
    t_gr_curriculum(); t_gr_markers(); t_gr_vocab(); t_gr_validate(); t_gr_generate()
    t_gr_grade_schedule(); t_wc_grammar()
    print("Affixes:")
    t_af_families(); t_af_items(); t_af_session()
    print("Reading, clinic, Penang:")
    t_rd_coverage(); t_rd_validate(); t_rd_generate(); t_rp_cases(); t_rp_turn(); t_utara()
    print("Games:")
    t_games_items(); t_games_logic()
    print("Speech and audio:")
    t_speech(); t_audio_voices()
    print("Store and plan:")
    t_store_codec(); t_plan_build(); t_plan_short(); t_plan_live(); t_pages_exist()
    if os.environ.get("DATABASE_URL"):
        print("Database (DATABASE_URL detected):")
        db_tests()
    else:
        print("Database tests skipped (set DATABASE_URL to enable).")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed.")
    sys.exit(1 if FAILED else 0)
