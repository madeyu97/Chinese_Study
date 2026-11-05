# src/grammar_data_2.py
"""Grammar curriculum, sections 7-12: numbers and classifiers, noun phrases
and yang, prepositions and place, verb affixes, the passive."""

from grammar_schema import Structure

SECTIONS = {
    7: "Numbers and classifiers",
    8: "Noun phrases and yang",
    9: "Prepositions and place",
    10: "Verb affixes I: meN- and ber-",
    11: "Verb affixes II: -kan and -i",
    12: "Passive and object focus",
}

_S = Structure
STRUCTURES = [
    # ------------------------------------------------------------------
    # 7. Numbers and classifiers
    # ------------------------------------------------------------------
    _S("se_one", 7, "se- for 'one'", "se- + classifier / time  (seorang, sekali, sehari)",
       "Say 'one' or 'a' the Malay way, joined to the word that follows.",
       notes="seorang (one person), sebuah (one thing), seekor (one animal), sekali (once), "
             "sehari (a day / per day), seminggu, sebulan. satu is used for counting; se- "
             "joins a classifier or a time word. Clinic: dua kali sehari.",
       markers=(r"\bse(orang|buah|ekor|biji|keping|helai|batang|kali|hari|minggu|bulan|"
                r"tahun|jam|minit|cawan|gelas|pinggan)\b",),
       words=("seorang", "sebuah", "seekor", "sebiji", "sekeping", "sehelai", "sekali",
              "sehari", "seminggu", "sebulan", "setahun"), level=1),
    _S("classifiers", 7, "Counting words: orang, ekor, buah, biji, keping, helai",
       "number + classifier + noun  (dua orang budak)",
       "Count people, animals and things with the right counting word.",
       notes="orang for people (tiga orang pesakit), ekor for animals (dua ekor kucing), "
             "buah for big things, houses and cars (sebuah kereta), biji for small round "
             "things and pills (dua biji pil), keping for flat things (sekeping roti), "
             "helai for cloth and paper (dua helai baju). Speech often drops the "
             "classifier (dua kucing) - accept both, model the classifier.",
       markers=(r"\b(orang|ekor|buah|biji|keping|helai|batang)\b",),
       words=("orang", "ekor", "buah", "biji", "keping", "helai", "batang"),
       level=2),
    _S("quantifiers", 7, "banyak, sikit, semua, setiap, beberapa", "banyak + noun · semua + noun",
       "Say how much or how many without a number.",
       notes="banyak orang, sikit garam, semua pesakit, setiap hari, beberapa minit, ramai "
             "orang (for people). banyak and sikit can also follow: makan banyak / makan "
             "sikit. Clinic: minum air banyak.",
       markers=(r"\b(banyak|sikit|sedikit|semua|setiap|beberapa|ramai|banyakkan)\b",),
       words=("banyak", "sikit", "sedikit", "semua", "setiap", "beberapa", "ramai"),
       level=1),
    _S("money_price", 7, "Prices and money", "… ringgit … sen  ·  Berapa harganya?",
       "Ask and say prices.",
       notes="Lima puluh ringgit. / Dua ringgit lima puluh sen. / Berapa harga satu? / "
             "Mahal sangat! / Boleh kurang sikit? Numbers in words. Contexts: market, "
             "clinic payment, taxi.",
       markers=(r"\b(ringgit|sen|harga\w*)\b",), words=("ringgit", "sen", "harga"),
       level=1, core=True),
    _S("clock_time", 7, "Telling the time", "pukul + number  (pukul tiga petang)",
       "Ask and say the time of day.",
       notes="Pukul berapa sekarang? / Pukul lapan pagi. / Pukul tiga setengah. / Temu janji "
             "pukul dua petang. Add pagi, tengah hari, petang, malam for the part of the "
             "day.",
       markers=(r"\bpukul\b", r"\bjam berapa\b"), words=("pukul", "setengah", "suku"),
       level=1, core=True),
    _S("ordinals", 7, "First, second, third", "pertama · ke- + number  (kedua, ketiga)",
       "Put things in order.",
       notes="hari pertama, kali kedua, tingkat tiga (floor three) vs tingkat ketiga. "
             "pertama is irregular; the rest are ke- + number. kali pertama datang? is a "
             "receptionist question.",
       markers=(r"\b(pertama|kedua|ketiga|keempat|kelima|keenam|ketujuh|kelapan|"
                r"kesembilan|kesepuluh)\b",), words=("pertama",), level=2),

    # ------------------------------------------------------------------
    # 8. Noun phrases and yang
    # ------------------------------------------------------------------
    _S("yang_clause", 8, "yang — who, which, that", "noun + yang + description",
       "Pick out which person or thing you mean with a description.",
       notes="Orang yang sakit tu. / Ubat yang doktor bagi. / Kedai yang jual kopi. The "
             "description follows yang. With a single adjective yang is optional (baju "
             "merah / baju yang merah); with longer descriptions it is needed.",
       markers=(r"\byang\b",), words=("yang",), level=1, core=True),
    _S("yang_one", 8, "yang + adjective — 'the … one'", "yang merah · yang mana?",
       "Say 'the red one', 'the big one', or ask 'which one?'.",
       notes="Saya nak yang besar. / Yang mana satu? / Yang ni lagi murah. Very common at "
             "shops and stalls. The noun is dropped because it is known.",
       contrast=("yang_clause",), markers=(r"\byang\b",), words=("yang", "mana"),
       level=2),
    _S("nya_the", 8, "-nya for a thing already known — 'the'", "noun + -nya  (Makanannya sedap.)",
       "Point back to something both people know about.",
       notes="Kita pergi restoran tu. Makanannya sedap, harganya murah. -nya refers to the "
             "thing already in the conversation, like 'the'. Also with adjectives: "
             "Mahalnya! (How expensive!). Keep separate from -nya as 'his/her'.",
       contrast=("nya_possessive",), markers=("@nya",), level=2),

    # ------------------------------------------------------------------
    # 9. Prepositions and place
    # ------------------------------------------------------------------
    _S("di_place", 9, "di — at, in", "di + place  (di rumah)",
       "Say where something is or happens.",
       notes="Saya tinggal di Ipoh. / Ubat ada di atas meja. di is written as a separate "
             "word before a place (di rumah), never joined; joined di- is the passive "
             "prefix (dimakan). Speech often uses kat.",
       contrast=("ke_place", "kat_dekat"), markers=(r"\bdi\b",), words=("di",),
       level=1, core=True),
    _S("ke_place", 9, "ke — to (a place)", "pergi / datang / balik + ke + place",
       "Say where someone is going.",
       notes="Saya nak pergi ke klinik. / Dia balik ke kampung. Speech often drops ke after "
             "pergi (pergi klinik). Separate word, never joined (ke rumah, not kerumah).",
       contrast=("di_place",), markers=(r"\bke\b",), words=("ke",), level=1, core=True),
    _S("dari_from", 9, "dari — from (a place or a time)", "dari + place / time",
       "Say where or when something starts.",
       notes="Saya dari England. / Dia datang dari Pulau Pinang. / Klinik buka dari pukul "
             "sembilan sampai pukul lima. Not for people or comparison (that is daripada).",
       contrast=("di_place",), markers=(r"\bdari\b",), words=("dari",), level=1),
    _S("di_ke_dari", 9, "di, ke or dari?", "di (at) · ke (to) · dari (from)",
       "Choose between 'at', 'to' and 'from'.",
       notes="Contrast drill: Dia di klinik / Dia pergi ke klinik / Dia baru balik dari "
             "klinik. Items hinge on position vs movement towards vs away.",
       contrast=("di_place", "ke_place", "dari_from"), markers=(r"\b(di|ke|dari)\b",),
       words=("di", "ke", "dari"), kind="contrast", level=1, also_in=(23,)),
    _S("kat_dekat", 9, "kat / dekat — at, near (speech)", "kat + place",
       "Say where, the way people actually talk.",
       notes="Saya kat rumah. / Sakit kat mana? / Kedai tu dekat dengan stesen (near). kat "
             "replaces di in speech; dekat means 'near' and also 'at'. Clinic: Sakit kat "
             "sini?",
       contrast=("di_place",), markers=(r"\b(kat|dekat)\b",), words=("kat", "dekat"),
       level=1, core=True),
    _S("pada_kepada", 9, "pada and kepada", "kepada + person · pada + time",
       "Say 'to' a person in formal Malay, and 'at/on' a time.",
       notes="Beri kepada doktor. / Saya cakap kepada dia. / Pada hari Isnin. / Pada pukul "
             "lapan. Speech often says bagi kat dia, cakap dengan dia. Mostly identify, "
             "some produce in formal contexts.",
       markers=(r"\b(pada|kepada)\b",), words=("pada", "kepada"), level=2),
    _S("dari_vs_daripada", 9, "dari or daripada?", "dari + place/time · daripada + person / comparison",
       "Choose the right 'from'.",
       notes="Contrast drill: Saya dari Ipoh (place) vs Saya dapat surat daripada doktor "
             "(person) / lebih besar daripada (comparison). Items hinge on place/time vs "
             "person or comparison.",
       contrast=("dari_from", "lebih_daripada"), markers=(r"\b(dari|daripada)\b",),
       words=("dari", "daripada"), kind="contrast", level=2, also_in=(23,)),
    _S("dengan", 9, "dengan — with, by", "dengan + person / thing",
       "Say who you are with, or what you use.",
       notes="Saya datang dengan isteri. / Pergi dengan teksi. / Makan dengan tangan. Also "
             "cakap dengan (talk to). Not for 'and' between nouns (that is dan).",
       markers=(r"\bdengan\b",), words=("dengan",), level=1, core=True),
    _S("untuk", 9, "untuk — for", "untuk + person / purpose",
       "Say who something is for, or what it is for.",
       notes="Ubat ni untuk sakit kepala. / Hadiah untuk awak. / Saya datang untuk rawatan. "
             "Also before verbs: untuk tidur (in order to sleep).",
       markers=(r"\buntuk\b",), words=("untuk",), level=1),
    _S("position_words", 9, "atas, bawah, dalam, luar, depan, belakang, sebelah",
       "di / kat + atas / bawah … + noun  (di atas meja)",
       "Say exactly where: on, under, in, outside, in front, behind, next to.",
       notes="Kunci ada di atas meja. / Kucing tidur bawah kerusi. / Tunggu kat luar. / "
             "Klinik sebelah kedai kopi. The position word comes before the noun. Clinic: "
             "baring, kepala ke atas.",
       markers=(r"\b(atas|bawah|dalam|luar|depan|hadapan|belakang|sebelah|tepi|tengah|"
                r"antara)\b",),
       words=("atas", "bawah", "dalam", "luar", "depan", "belakang", "sebelah", "tepi",
              "tengah", "antara"), level=1, core=True),

    # ------------------------------------------------------------------
    # 10. Verb affixes I
    # ------------------------------------------------------------------
    _S("bare_verbs", 10, "Bare verbs in everyday speech", "Saya beli roti. (= membeli)",
       "Use and understand the short verb forms people actually say.",
       notes="Speech drops meN-: Saya beli roti, Dia tengok TV, Awak baca buku ni? Written "
             "Malay would use membeli, menonton, membaca. Drill hearing bare verbs and "
             "matching them to the full form; produce in casual contexts only.",
       contrast=("men_active",), level=1),
    _S("men_active", 10, "meN- — the active verb", "meN- + root  (membaca, menulis, memukul)",
       "Use the standard active verb that does something to something.",
       notes="meN- changes with the root's first sound: baca → membaca, tulis → menulis, "
             "pukul → memukul, sapu → menyapu, ambil → mengambil, cat → mengecat. Usually "
             "with an object. In speech often bare (baca). Drill recognising the root inside "
             "the verb, and the full form in writing and formal speech.",
       contrast=("bare_verbs", "ber_verbs", "di_passive"), markers=("@meN",),
       level=1, core=True),
    _S("ber_verbs", 10, "ber- — doing, being, having", "ber- + root  (berjalan, bekerja, berumur)",
       "Use verbs for activities without an object, states and 'having'.",
       notes="berjalan (walk), bekerja (work), berehat (rest), bermain (play), berumur "
             "(aged), berbaju merah (wearing a red top), bercakap (speak). No object "
             "follows. ber- becomes be- before r and some roots (berehat, bekerja), bel- in "
             "belajar.",
       contrast=("men_active",), markers=("@ber",), level=1, core=True),
    _S("men_vs_ber", 10, "meN- or ber-?", "meN- (to something) · ber- (no object)",
       "Choose between the 'does something to it' verb and the 'just doing / being' verb.",
       notes="Contrast drill with real pairs from one root: mengajar (teach someone) / "
             "belajar (study); menjalankan (run something) / berjalan (walk); mengubati "
             "(treat a patient) / berubat (get treatment). Items hinge on whether something "
             "is acted on.",
       contrast=("men_active", "ber_verbs"), markers=("@meN", "@ber"),
       kind="contrast", level=2, also_in=(23,)),

    # ------------------------------------------------------------------
    # 11. Verb affixes II
    # ------------------------------------------------------------------
    _S("kan_causative", 11, "-kan — make it so, do it for someone", "root + -kan  (besarkan, belikan)",
       "Make something happen to something, or do something for someone.",
       notes="besarkan (make bigger), naikkan (raise), kurangkan (reduce), panaskan "
             "(heat up), bengkokkan (bend it); belikan (buy for), ambilkan (fetch for). "
             "Instructions: Tolong luruskan kaki. / Kurangkan gula. Often with meN- in "
             "writing (membesarkan), bare in commands.",
       contrast=("i_suffix",), markers=("@-kan",), level=2),
    _S("i_suffix", 11, "-i — to, at, on (the place or person)", "root + -i  (masuki, datangi, sukai)",
       "Point the action at a place or person.",
       notes="mendekati (approach), menaiki (get on), menyukai (like), memasuki (enter), "
             "rasai (feel it). Less common in speech than -kan. Mostly identify and "
             "recognise; produce a few common ones (sukai, naiki).",
       contrast=("kan_causative",), markers=("@-i",), level=2),
    _S("kan_vs_i", 11, "-kan or -i?", "-kan (cause / for) · -i (to / at)",
       "Tell the two suffixes apart.",
       notes="Contrast drill with real pairs: masukkan (put it in) vs masuki (enter it); "
             "naikkan (raise it) vs naiki (get on it); dekatkan (bring closer) vs dekati "
             "(approach). Items hinge on moving the object vs going to it.",
       contrast=("kan_causative", "i_suffix"), markers=("@-kan", "@-i"),
       kind="contrast", level=2, also_in=(23,)),

    # ------------------------------------------------------------------
    # 12. Passive and object focus
    # ------------------------------------------------------------------
    _S("di_passive", 12, "di- — the passive", "thing + di- + verb (+ oleh + person)",
       "Put the thing acted on first: 'it was done (by someone)'.",
       notes="Ubat ni diambil selepas makan. / Kereta saya dicuri. / Surat tu ditulis oleh "
             "doktor. Very common in Malay, far more than in English, for instructions and "
             "news. Only with a third person or unknown doer - with saya/awak use the "
             "pronoun form (a separate structure).",
       contrast=("men_active", "object_focus"), markers=("@di",), level=2, core=True),
    _S("object_focus", 12, "Thing + pronoun + verb", "Buku tu saya dah baca.",
       "Put the thing first when the doer is I, you or we.",
       notes="Ubat tu saya dah makan. / Ini awak kena isi. / Kerja tu kami buat esok. The "
             "pronoun goes straight before a bare verb; aspect words (dah, nak) come "
             "before the pronoun or between. This is the passive for saya/awak/kami - "
             "never di- with them (NOT dibaca oleh saya in speech).",
       contrast=("di_passive",), level=2),
    _S("men_vs_di", 12, "meN- or di-?", "doer first: meN- · thing first: di-",
       "Choose active or passive.",
       notes="Contrast drill: Doktor memeriksa pesakit vs Pesakit diperiksa oleh doktor. "
             "Items hinge on which comes first and who does it.",
       contrast=("men_active", "di_passive"), markers=("@meN", "@di"),
       kind="contrast", level=2, also_in=(23,)),
    _S("ter_accidental", 12, "ter- — by accident, can't help it", "ter- + root  (tertinggal, terjatuh)",
       "Say something happened by accident or without meaning to.",
       notes="Saya tertinggal dompet. / Dia terjatuh. / Terlupa! / Tak terangkat (can't "
             "lift it). Also ter- = most (terbaik) - keep that for comparison.",
       markers=("@ter",), level=2),
    _S("kena_adversative", 12, "kena + verb — something happens to you", "kena + verb  (kena marah)",
       "Say something unwelcome happened to someone.",
       notes="Saya kena marah. / Dia kena tipu. / Kaki dia kena gigit nyamuk. kena also "
             "means 'have to' (kena pergi) - a separate structure. Drill hearing the "
             "difference from context.",
       contrast=("di_passive",), markers=(r"\bkena\b",), words=("kena",), level=2),
]
