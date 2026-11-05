# src/grammar_data_1.py
"""Grammar curriculum, sections 1-6: sentence basics, pronouns and address,
negation, questions, aspect and time, existence and possession."""

from grammar_schema import Structure

SECTIONS = {
    1: "Sentence basics",
    2: "Pronouns and address",
    3: "Negation",
    4: "Questions",
    5: "Aspect and time",
    6: "Existence and possession",
}

_S = Structure
STRUCTURES = [
    # ------------------------------------------------------------------
    # 1. Sentence basics
    # ------------------------------------------------------------------
    _S("svo", 1, "Basic word order", "subject + verb + object  (Saya makan nasi.)",
       "Say who does what: the subject, then the action, then what it acts on.",
       notes="Meaning comes from order, not word endings: Ali panggil Ahmad vs Ahmad "
             "panggil Ali. Swap subject and object to change who does what. Very short "
             "sentences, everyday verbs (makan, minum, beli, tengok, ambil). No tense words "
             "needed: Malay verbs never change for time.",
       level=1, core=True),
    _S("adj_predicate", 1, "Adjective as the predicate", "noun + adjective  (Rumah tu besar.)",
       "Describe something: the adjective follows directly, with no word for 'is'.",
       notes="Kopi ni panas. / Dia penat. / Bilik tu sejuk. Never put adalah or ialah before "
             "an adjective (NOT Dia adalah penat). Sangat may come before the adjective "
             "(sangat panas) - keep that for a later structure, mostly bare adjectives here.",
       contrast=("noun_adj", "adalah_ialah"), level=1, core=True),
    _S("noun_adj", 1, "Noun before adjective", "noun + adjective  (kereta baru)",
       "Describe a thing inside a phrase: the describing word comes after the noun.",
       notes="kereta merah, air sejuk, rumah besar, kawan baik - the reverse of English. "
             "Contrast the phrase (kereta merah = a red car) with the sentence (Kereta tu "
             "merah = The car is red): ini/itu at the end makes it a sentence. Drill hearing "
             "which is which.",
       contrast=("adj_predicate",), level=1, core=True),
    _S("ini_itu", 1, "ini / itu after the noun", "noun + ini / itu  (buku ini, kereta tu)",
       "Point to 'this' or 'that' thing: ini and itu follow the noun.",
       notes="buku ini, rumah itu; in speech ni and tu: kedai ni, orang tu. On their own "
             "they mean 'this (one)' / 'that (one)': Ini kopi saya. Never before the noun "
             "(NOT ini buku for 'this book' - Ini buku means 'This is a book'). Drill the "
             "difference between 'buku ini' (this book) and 'Ini buku' (This is a book).",
       markers=(r"\b(ini|itu|ni|tu)\b",), words=("ini", "itu", "ni", "tu"),
       level=1, core=True),
    _S("possessor_after", 1, "Owner after the thing", "thing + owner  (rumah saya, kereta kawan saya)",
       "Say whose something is: the owner comes after the thing.",
       notes="beg saya, nama awak, kereta kawan saya, bilik doktor. No 'of' word needed. "
             "Chains go thing + owner + owner's owner (kereta abang saya = my brother's car). "
             "Keep -nya ('his/her') for its own structure.",
       level=1, core=True),
    _S("zero_copula", 1, "No word for 'is' with nouns in speech", "A + B  (Dia doktor.)",
       "Say what or who someone is, in everyday speech, with nothing between the two nouns.",
       notes="Dia doktor. / Ini rumah saya. / Ayah saya cikgu. Spoken Malay puts the two "
             "nouns side by side. The formal adalah/ialah is a separate structure. Negative "
             "with bukan (Dia bukan doktor) belongs to negation - use positives here.",
       contrast=("adalah_ialah",), level=1, core=True),
    _S("adalah_ialah", 1, "adalah / ialah before nouns (formal)", "A + ialah / adalah + B",
       "Link two nouns in formal or written Malay.",
       notes="Ibu negeri Pulau Pinang ialah George Town. / Masalahnya adalah masa. Used in "
             "writing, news and formal speech; in conversation it is usually dropped. Never "
             "before an adjective (NOT Dia adalah sakit). Contexts: notices, news, "
             "definitions, presentations.",
       contrast=("zero_copula", "adj_predicate"), markers=(r"\b(adalah|ialah)\b",),
       words=("adalah", "ialah"), level=2),
    _S("subject_drop", 1, "Leaving out the subject", "(Saya) dah makan.",
       "Drop the subject when it is obvious who you mean.",
       notes="Replies and follow-ups lose the subject: A: Dah makan? B: Dah. / Nak pergi "
             "mana? - Balik rumah. Drill understanding who is meant from context and "
             "answering without repeating the subject. Short natural exchanges.",
       level=2, also_in=(21,)),
    _S("object_drop", 1, "Leaving out the object", "Dah beli? - Dah beli.",
       "Drop the object when both people know what it is.",
       notes="Malay drops a known object where English needs 'it': A: Awak dah baca buku "
             "tu? B: Dah baca. (not Dah baca ia). Drill replies that omit the object; "
             "never add ia or itu for things in these replies.",
       level=2),

    # ------------------------------------------------------------------
    # 2. Pronouns and address
    # ------------------------------------------------------------------
    _S("saya_awak", 2, "saya and awak — the polite default", "saya … awak",
       "Talk about yourself and the person you're speaking to, politely.",
       notes="saya (I/me) and awak (you) are safe with almost anyone of similar age. "
             "Possessives follow the noun: kereta saya, nama awak. Kamu is fine too but "
             "can sound like talking to a child or a junior. Contexts: shop, clinic, "
             "neighbours, colleagues.",
       markers=(r"\b(saya|awak)\b",), words=("saya", "awak"), level=1, core=True),
    _S("aku_kau", 2, "aku and kau — between close friends", "aku … kau",
       "Talk to close friends and family the casual way.",
       notes="aku (I) and kau/engkau (you) are for close friends, siblings, people your own "
             "age you know well - rude with strangers or elders. Possessive -ku/-mu are "
             "mostly written; speech says rumah aku, kereta kau. Identify tasks: which "
             "relationship does the pronoun show?",
       contrast=("saya_awak",), markers=(r"\b(aku|kau|engkau)\b",),
       words=("aku", "kau", "engkau"), level=2),
    _S("kami_kita", 2, "kami vs kita — 'we' without you, 'we' with you",
       "kami (not you) · kita (including you)",
       "Choose the right 'we': kami leaves the listener out, kita includes them.",
       notes="Kami nak balik (we - not you - are going home) vs Jom kita makan (let's eat, "
             "you too). The error to train out is kita for a group the listener isn't in. "
             "Drill situations: telling a shopkeeper about your family (kami), inviting a "
             "friend (kita).",
       markers=(r"\b(kami|kita)\b",), words=("kami", "kita"), level=1, core=True),
    _S("dia_mereka", 2, "dia, beliau, mereka", "dia (he/she) · beliau (respectful) · mereka (they)",
       "Talk about other people: one person, someone you respect, a group.",
       notes="dia covers he and she - Malay doesn't mark gender. beliau is the respectful "
             "form for elders, officials, a doctor or teacher spoken of formally. mereka is "
             "they. Drill that 'dia' answers can be he OR she.",
       markers=(r"\b(dia|beliau|mereka)\b",), words=("dia", "beliau", "mereka"),
       level=1, core=True),
    _S("kin_address", 2, "Kin terms as 'you'", "abang / kakak / adik / pak cik / mak cik + …",
       "Address people the Malaysian way, with family words instead of 'you'.",
       notes="Malaysians say 'you' with kin terms: Abang nak apa? (to a man a bit older), "
             "Kakak tinggal mana? (a woman a bit older), Adik (someone younger), Pak cik / "
             "Mak cik (much older), Encik / Puan (formal). Short forms in speech: bang, kak, "
             "dik. Contexts: a stall, a taxi, a clinic - asking a patient where it hurts "
             "(Mak cik sakit kat mana?).",
       contrast=("saya_awak",),
       markers=(r"\b(abang|bang|kakak|kak|adik|dik|pak cik|mak cik|encik|puan|cik)\b",),
       words=("abang", "bang", "kakak", "kak", "adik", "dik", "pak", "mak", "cik", "encik", "puan"),
       level=2, core=True),
    _S("anda", 2, "anda — 'you' in writing and adverts", "anda",
       "Recognise the polite 'you' used in signs, forms and adverts.",
       notes="anda appears on signs, forms, adverts and announcements (Sila tunggu giliran "
             "anda). In conversation it sounds stiff. Mostly identify tasks: notices, forms, "
             "instructions.",
       markers=(r"\banda\b",), words=("anda",), level=2),
    _S("korang_diorang", 2, "korang and diorang — casual 'you all' and 'they'",
       "korang (= kamu semua) · diorang (= mereka)",
       "Understand and use the everyday plural pronouns.",
       notes="korang (from kau orang) = you all; diorang/dorang (from dia orang) = they. "
             "Very common in speech, not in writing. Drill recognising them by ear and "
             "mapping to mereka / kamu semua.",
       contrast=("dia_mereka",), markers=(r"\b(korang|diorang|dorang)\b",),
       words=("korang", "diorang", "dorang"), level=2),

    # ------------------------------------------------------------------
    # 3. Negation
    # ------------------------------------------------------------------
    _S("tidak_tak", 3, "tidak / tak — not", "tak + verb / adjective",
       "Say something doesn't happen or isn't so.",
       notes="tidak negates verbs and adjectives: Saya tak suka. / Kopi ni tak manis. "
             "Speech says tak almost always. Never before a noun (that is bukan). Short "
             "everyday sentences; mix tak and tidak across items.",
       contrast=("bukan",), markers=(r"\b(tidak|tak|x)\b",), words=("tidak", "tak"),
       level=1, core=True),
    _S("bukan", 3, "bukan — not (with nouns)", "bukan + noun",
       "Say something isn't a particular thing or person.",
       notes="Dia bukan doktor. / Ini bukan kereta saya. Also for contrast: bukan hari ini, "
             "esok. Not before verbs or adjectives in plain negation (that is tak).",
       contrast=("tidak_tak",), markers=(r"\bbukan\b",), words=("bukan",), level=1, core=True),
    _S("tak_vs_bukan", 3, "tak or bukan?", "tak + verb/adjective · bukan + noun",
       "Choose the right 'not'.",
       notes="Contrast drill: Dia tak sakit (he isn't ill) vs Dia bukan doktor (he isn't a "
             "doctor). Items must hinge on what follows the negative.",
       contrast=("tidak_tak", "bukan"), markers=(r"\b(tidak|tak|bukan)\b",),
       words=("tidak", "tak", "bukan"), kind="contrast", level=1, also_in=(23,)),
    _S("belum", 3, "belum — not yet", "belum + verb",
       "Say something hasn't happened yet but is expected to.",
       notes="Saya belum makan. / Dia belum sampai. The reply to Dah …? questions: Dah "
             "makan? - Belum. Not the same as tak (never / not at all).",
       contrast=("tidak_tak", "sudah_dah"), markers=(r"\bbelum\b",), words=("belum",),
       level=1, core=True),
    _S("jangan", 3, "jangan — don't", "jangan + verb",
       "Tell someone not to do something.",
       notes="Jangan bergerak. / Jangan risau. / Jangan makan makanan pedas. Softer: "
             "Janganlah. Clinic instructions are good contexts (Jangan angkat barang berat).",
       markers=(r"\bjangan\w*\b",), words=("jangan",), level=1, core=True),
    _S("tiada_takde", 3, "tiada / takde — there isn't, don't have",
       "tiada / tak ada / takde + noun",
       "Say something isn't there or someone doesn't have it.",
       notes="Takde duit. / Hari ni tiada doktor. tiada is standard and written; tak ada "
             "and takde are speech. Never tak + noun for absence (NOT tak duit).",
       contrast=("ada_exist",), markers=(r"\b(tiada|takde|takda|tak ada|tidak ada)\b",),
       words=("tiada", "takde", "ada"), level=1, core=True),
    _S("belum_vs_tak", 3, "belum or tak?", "belum (not yet) · tak (not)",
       "Tell 'not yet' apart from 'not'.",
       notes="Contrast drill: Saya belum makan (not yet - I will) vs Saya tak makan daging "
             "(I don't eat meat). Items hinge on whether it is expected to happen.",
       contrast=("belum", "tidak_tak"), markers=(r"\b(belum|tidak|tak)\b",),
       words=("belum", "tidak", "tak"), kind="contrast", level=2, also_in=(23,)),

    # ------------------------------------------------------------------
    # 4. Questions
    # ------------------------------------------------------------------
    _S("apa", 4, "apa — what", "… apa?  /  Apa …?",
       "Ask what something is or what someone does.",
       notes="Awak nak apa? / Apa ni? / Nama awak apa? Question words can stay where the "
             "answer would go (Awak makan apa?). Also apa-apa (anything) - keep to plain apa.",
       markers=(r"\bapa\b",), words=("apa",), level=1, core=True),
    _S("siapa", 4, "siapa — who", "Siapa …?",
       "Ask who.",
       notes="Siapa nama awak? / Ini siapa punya? / Awak cari siapa? Natural receptionist "
             "and clinic questions.",
       markers=(r"\bsiapa\b",), words=("siapa",), level=1, core=True),
    _S("mana", 4, "mana — where (di / ke / dari mana)", "di mana · ke mana · dari mana",
       "Ask where something is, where someone is going, or where they're from.",
       notes="Tandas kat mana? / Nak pergi mana? / Awak dari mana? Speech often drops the "
             "preposition (Pergi mana?). Also 'which': yang mana? Clinic: Sakit kat mana?",
       markers=(r"\bmana\b",), words=("mana",), level=1, core=True),
    _S("bila", 4, "bila — when", "Bila …?",
       "Ask when.",
       notes="Bila awak sampai? / Bila mula sakit? / Klinik buka bila? (Bila as a question "
             "only here; bila as 'when' in a statement is a later structure.)",
       markers=(r"\bbila\b",), words=("bila",), level=1, core=True),
    _S("kenapa", 4, "kenapa — why", "Kenapa …?",
       "Ask why.",
       notes="Kenapa awak lambat? / Kenapa tak datang semalam? mengapa is the formal "
             "equivalent; apa pasal is casual (a later structure). Answers usually use "
             "sebab.",
       markers=(r"\b(kenapa|mengapa)\b",), words=("kenapa", "mengapa"), level=1, core=True),
    _S("macam_mana", 4, "macam mana — how", "Macam mana …?  /  bagaimana",
       "Ask how something is done or how something is.",
       notes="Macam mana nak pergi ke stesen? / Macam mana rasanya? bagaimana is formal; "
             "camne is casual. Clinic: Macam mana sakitnya?",
       markers=(r"\b(macam mana|bagaimana|camne|macamana)\b",),
       words=("macam", "mana", "bagaimana"), level=1, core=True),
    _S("berapa", 4, "berapa — how many, how much", "Berapa …?",
       "Ask about numbers, prices, age and time.",
       notes="Berapa harga ni? / Berapa orang? / Umur berapa? / Pukul berapa? Answers give "
             "a number in words.",
       markers=(r"\bberapa\w*\b",), words=("berapa",), level=1, core=True),
    _S("ke_question", 4, "… ke? — the spoken yes/no question", "Awak lapar ke?",
       "Ask a yes/no question the everyday way.",
       notes="In speech, ke after the word being asked about makes a yes/no question: Awak "
             "penat ke? / Dia doktor ke? / Nak ke tak nak? Also ke tak at the end. Don't "
             "confuse with ke meaning 'to'. Formal speech uses -kah or adakah instead.",
       contrast=("kah_question",), markers=(r"\bke\b(?=\s*(\?|$|tak\b|tidak\b|,))",),
       words=("ke",), level=1, core=True),
    _S("kah_question", 4, "Adakah … / -kah — formal questions", "Adakah …? · Bolehkah …?",
       "Recognise and ask yes/no questions in formal Malay.",
       notes="Adakah awak sudah makan? / Bolehkah saya masuk? / Betulkah? Common in writing, "
             "announcements and polite speech; in conversation ke or intonation does the "
             "same job.",
       contrast=("ke_question",), markers=(r"\badakah\b", r"\b\w+kah\b"),
       words=("adakah",), level=2),
    _S("tag_question", 4, "… kan? / … ya tak? — checking agreement", "Sedap, kan?",
       "Check the listener agrees, like '…, isn't it?'",
       notes="Dia dah balik, kan? / Panas hari ni, kan? / Betul tak? kan at the end "
             "expects 'yes'. Also kan at the start for 'see, I told you': Kan saya dah "
             "cakap!",
       markers=(r"\bkan\b", r"\bya tak\b", r"\bbetul tak\b"), words=("kan", "ya", "betul"),
       level=2),

    # ------------------------------------------------------------------
    # 5. Aspect and time
    # ------------------------------------------------------------------
    _S("sudah_dah", 5, "sudah / dah — already, done", "dah + verb",
       "Say something has happened or is finished.",
       notes="Saya dah makan. / Doktor dah sampai. / Dah siap. telah is the written form. "
             "Malay verbs don't change for past: dah marks completion, not tense - never "
             "explain it as 'past tense'. Common question: Dah …? answered Dah / Belum.",
       contrast=("belum", "pernah"), markers=(r"\b(sudah|dah|telah)\b",),
       words=("sudah", "dah", "telah"), level=1, core=True),
    _S("sedang_tengah", 5, "sedang / tengah — in the middle of", "tengah + verb",
       "Say something is happening right now.",
       notes="Dia tengah makan. / Saya sedang tunggu. tengah is speech, sedang more formal. "
             "Only for ongoing actions, not states (NOT Saya tengah sakit for 'I'm ill').",
       markers=(r"\b(sedang|tengah)\b",), words=("sedang", "tengah"), level=1, core=True),
    _S("akan_nak", 5, "akan / nak — going to, will", "nak / akan + verb",
       "Talk about plans and what will happen.",
       notes="Saya nak balik esok. (plan) / Hujan akan turun. (prediction) / Klinik akan "
             "tutup pukul enam. nak is everyday speech for plans; akan is more formal and "
             "used for predictions and announcements.",
       contrast=("nak_want",), markers=(r"\b(akan|nak|hendak)\b",),
       words=("akan", "nak", "hendak"), level=1, core=True),
    _S("pernah", 5, "pernah — have ever", "pernah + verb",
       "Say you have (or have never) done something at some time.",
       notes="Saya pernah pergi ke Ipoh. / Awak pernah makan durian? / Saya tak pernah "
             "naik kapal terbang. Experience, not a single recent event (that is dah).",
       contrast=("sudah_dah",), markers=(r"\bpernah\b",), words=("pernah",), level=1, core=True),
    _S("sudah_vs_pernah", 5, "dah or pernah?", "dah (done) · pernah (ever)",
       "Tell 'already done' apart from 'have ever done'.",
       notes="Contrast drill: Saya dah makan (I've eaten - just now) vs Saya pernah makan "
             "durian (I have eaten it at some time in my life). Items hinge on single event "
             "vs experience.",
       contrast=("sudah_dah", "pernah"), markers=(r"\b(sudah|dah|pernah)\b",),
       words=("sudah", "dah", "pernah"), kind="contrast", level=2, also_in=(23,)),
    _S("masih", 5, "masih — still", "masih + verb / adjective",
       "Say something is still going on.",
       notes="Dia masih tidur. / Kaki saya masih sakit. / Kedai tu masih buka. Speech also "
             "says lagi after the verb (Dia tidur lagi) - recognise it.",
       markers=(r"\bmasih\b",), words=("masih",), level=2),
    _S("baru", 5, "baru — just (a moment ago)", "baru + verb",
       "Say something has only just happened.",
       notes="Saya baru sampai. / Dia baru keluar. Also baru = new (kereta baru) - keep to "
             "'just' here, contexts make it clear.",
       markers=(r"\bbaru\b",), words=("baru",), level=2),
    _S("time_position", 5, "Where time words go", "Esok saya kerja. / Saya kerja esok.",
       "Say when: time words go at the start or the end of the sentence.",
       notes="semalam, hari ini, esok, tadi, nanti, minggu depan, pagi tadi. Either at the "
             "start or the end; never between verb and object (NOT Saya makan semalam nasi). "
             "No verb changes for time.",
       markers=(r"\b(esok|semalam|hari ini|hari ni|tadi|nanti|sekarang|minggu depan|"
                r"minggu lepas|bulan depan|tahun lepas|lusa|pagi|petang|malam)\b",),
       words=("esok", "semalam", "hari", "tadi", "nanti", "sekarang"), level=1),
    _S("lagi", 5, "lagi — more, again, still", "… lagi",
       "Ask for more, say 'again', or say something is still the case.",
       notes="Nak lagi? (more?) / Datang lagi (come again) / Dia tidur lagi (still asleep) "
             "/ Lagi lima minit (five more minutes). Drill hearing which sense from context.",
       markers=(r"\blagi\b",), words=("lagi",), level=2),

    # ------------------------------------------------------------------
    # 6. Existence and possession
    # ------------------------------------------------------------------
    _S("ada_exist", 6, "ada — there is, have", "ada + noun",
       "Say something exists somewhere, or someone has it.",
       notes="Ada kedai kat sana. / Saya ada dua anak. / Awak ada masa? Questions: Ada … "
             "tak? Negative is tiada / tak ada / takde.",
       contrast=("tiada_takde",), markers=(r"\bada\b",), words=("ada",), level=1, core=True),
    _S("nya_possessive", 6, "-nya — his, her, its", "noun + -nya  (rumahnya)",
       "Say 'his', 'her' or 'its' by adding -nya.",
       notes="Keretanya baru. / Nama dia Ali, umurnya lima tahun. -nya can be his or her; "
             "speech often prefers noun + dia (kereta dia). Also -nya with a known thing "
             "(the) is a later structure.",
       contrast=("possessor_after",), markers=("@nya",), level=1, core=True),
    _S("punya", 6, "punya — owning (speech)", "Siapa punya? · saya punya",
       "Ask or say whose something is, the casual way.",
       notes="Ini siapa punya? / Ni saya punya. / Kawan saya punya kereta (my friend's car). "
             "Very common in speech; writing uses kepunyaan or plain noun + owner.",
       contrast=("possessor_after",), markers=(r"\bpunya\b",), words=("punya",), level=2),
]
