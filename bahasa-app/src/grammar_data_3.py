# src/grammar_data_3.py
"""Grammar curriculum, sections 13-25: noun formation, comparison,
reduplication, requests, modals, adverbs, linking clauses, spoken particles
and set phrases, register pairs, contrast pairs and the core set.

Section 24 (northern Malay) arrives with Phase 6; section 23 and 25 gather
structures written in other sections (see also_in and core)."""

from grammar_schema import Structure

SECTIONS = {
    13: "Noun formation",
    14: "Comparison",
    15: "Reduplication",
    16: "Requests and commands",
    17: "Modals",
    18: "Adverbs and focus",
    19: "Linking clauses",
    20: "Spoken particles",
    21: "Spoken set phrases",
    22: "Register pairs",
    23: "Contrast pairs",
    24: "Northern Malay (recognition)",
    25: "Core automation set",
}

_S = Structure
STRUCTURES = [
    # ------------------------------------------------------------------
    # 13. Noun formation
    # ------------------------------------------------------------------
    _S("an_noun", 13, "-an — the thing made or done", "root + -an  (makanan, minuman, tulisan)",
       "Recognise and use nouns made with -an.",
       notes="makan → makanan (food), minum → minuman (drink), tulis → tulisan (writing), "
             "rawat → rawatan (treatment), urut → urutan (a massage). Drill moving between "
             "the verb and the noun in natural sentences.",
       markers=("@-an",), level=2),
    _S("pe_agent", 13, "peN- / pe- — the person who does it", "peN- + root  (pemandu, penjual, pelajar)",
       "Name the person who does an activity.",
       notes="pandu → pemandu (driver), jual → penjual (seller), ajar → pelajar (student), "
             "kerja → pekerja (worker), sakit → pesakit (patient), urut → pengurut "
             "(masseur). The prefix changes with the first sound like meN-.",
       markers=("@peN", "@pe"), level=2),
    _S("ke_an_abstract", 13, "ke-…-an — the state or quality", "ke- + root + -an  (kesihatan, kebersihan)",
       "Name an idea or condition from an adjective or verb.",
       notes="sihat → kesihatan (health), bersih → kebersihan (cleanliness), sakit → "
             "kesakitan (pain), selamat → keselamatan (safety). Common in notices and "
             "health talk. Also ke-…-an for something unwelcome (kehujanan) - recognise only.",
       markers=("@ke-an",), level=2),

    # ------------------------------------------------------------------
    # 14. Comparison
    # ------------------------------------------------------------------
    _S("lebih_daripada", 14, "lebih … daripada — more … than", "A + lebih + adjective + daripada + B",
       "Compare two things.",
       notes="Kereta ni lebih mahal daripada kereta tu. / Hari ni lebih panas. Speech often "
             "says dari instead of daripada. Also lebih baik (better): Lebih baik awak "
             "berehat.",
       contrast=("paling",), markers=(r"\blebih\b",), words=("lebih", "daripada", "dari"),
       level=1, core=True),
    _S("paling", 14, "paling — the most", "paling + adjective",
       "Say something is the most … of all.",
       notes="Ini yang paling murah. / Dia paling tinggi dalam kelas. ter- does the same in "
             "writing (terbaik, termahal) - recognise it.",
       contrast=("lebih_daripada",), markers=(r"\bpaling\b", r"\bter(baik|besar|mahal|murah|"
                                              r"tinggi|cantik|penting)\b"),
       words=("paling",), level=1),
    _S("sama_dengan", 14, "sama … dengan / se- — as … as", "sama + adjective + dengan · se- + adjective",
       "Say two things are equal in some way.",
       notes="Dia sama tinggi dengan abang dia. / Rumah ni sebesar rumah saya. / Harga dia "
             "sama. se- + adjective is common in writing (secepat mungkin = as fast as "
             "possible).",
       markers=(r"\bsama\b", r"\bse(besar|tinggi|cepat|mahal|murah|banyak|lama|jauh)\b"),
       words=("sama", "dengan"), level=2),
    _S("makin_makin", 14, "makin … makin — the more … the more", "makin + adjective  ·  makin … makin …",
       "Say something keeps increasing, or that one change brings another.",
       notes="Sakitnya makin teruk. / Makin lama makin baik. semakin is the formal form. "
             "Clinic: makin baik, makin teruk.",
       markers=(r"\b(makin|semakin)\b",), words=("makin", "semakin"), level=2),
    _S("kurang", 14, "kurang — less, not very", "kurang + adjective",
       "Say 'less' or soften a negative.",
       notes="Saya kurang sihat hari ni (not very well - polite). / Kurangkan gula (reduce "
             "sugar - -kan form). / Kurang pedas (less spicy). Polite way to say something "
             "isn't good.",
       markers=(r"\bkurang\w*\b",), words=("kurang",), level=2),

    # ------------------------------------------------------------------
    # 15. Reduplication
    # ------------------------------------------------------------------
    _S("plural_redup", 15, "Doubling for plurals", "noun-noun  (budak-budak, buku-buku)",
       "Say there are many of something, or various kinds.",
       notes="budak-budak (children), buah-buahan (fruits of all kinds), kawan-kawan saya. "
             "Not needed after a number or banyak (NOT dua budak-budak, NOT banyak "
             "buku-buku). Some words are always doubled (kanak-kanak, rama-rama).",
       markers=("@R", r"\b(\w+)-\1\b"), level=1),
    _S("manner_redup", 15, "Doubling for manner", "perlahan-lahan · cepat-cepat · baik-baik",
       "Say how something is done.",
       notes="Jalan perlahan-lahan. / Cepat-cepat sikit! / Jaga diri baik-baik. Also "
             "doubling for 'all sorts of' and 'kind of' - keep to manner here. Clinic: tarik "
             "nafas perlahan-lahan.",
       markers=(r"\b\w+-\w+\b",), level=2),

    # ------------------------------------------------------------------
    # 16. Requests and commands
    # ------------------------------------------------------------------
    _S("tolong_sila", 16, "tolong and sila — please", "Tolong + verb · Sila + verb",
       "Ask someone to do something, politely.",
       notes="Tolong tutup pintu. (asking a favour) / Sila duduk. (inviting, formal - "
             "reception, notices) / Tolong baring meniarap. Contexts: clinic instructions, "
             "asking for help.",
       markers=(r"\b(tolong|sila)\b",), words=("tolong", "sila"), level=1, core=True),
    _S("lah_command", 16, "-lah to soften a command", "verb + -lah  (Duduklah.)",
       "Make an instruction friendlier.",
       notes="Duduklah. / Makanlah dulu. / Rehatlah. -lah after the verb softens it; tone "
             "carries a lot. Also on negatives: Janganlah risau.",
       contrast=("tolong_sila",), markers=(r"\b\w+lah\b",), level=1),
    _S("jom_mari", 16, "jom / mari — let's", "Jom + verb",
       "Suggest doing something together.",
       notes="Jom makan! / Jom pergi. / Mari kita mulakan. jom is speech, mari more formal "
             "or older. Uses kita (including you).",
       markers=(r"\b(jom|mari)\b",), words=("jom", "mari"), level=1),
    _S("cuba", 16, "cuba — try (and a soft command)", "Cuba + verb",
       "Ask someone to try, or give a gentle instruction.",
       notes="Cuba angkat tangan. / Cuba tarik nafas dalam-dalam. / Cuba tengok ni. Very "
             "useful in treatment: it invites rather than orders.",
       markers=(r"\bcuba\b",), words=("cuba",), level=2),

    # ------------------------------------------------------------------
    # 17. Modals
    # ------------------------------------------------------------------
    _S("boleh", 17, "boleh — can, may", "boleh + verb",
       "Say someone can or may do something; ask permission.",
       notes="Saya boleh cakap Melayu sikit. / Boleh saya masuk? / Boleh tak? Negative: tak "
             "boleh. Never bisa (Indonesian).",
       markers=(r"\bboleh\w*\b",), words=("boleh",), level=1, core=True),
    _S("must_need", 17, "mesti, kena, perlu — must, have to, need", "mesti / kena / perlu + verb",
       "Say something is necessary.",
       notes="Awak mesti rehat. / Saya kena balik sekarang. / Tak perlu bayar. kena is the "
             "everyday 'have to'; perlu = need; mesti = must. Clinic advice: Awak perlu "
             "minum banyak air.",
       contrast=("kena_adversative",), markers=(r"\b(mesti|kena|perlu|harus|wajib)\b",),
       words=("mesti", "kena", "perlu", "harus"), level=1, core=True),
    _S("patut", 17, "patut — should", "patut + verb",
       "Give advice or say what's right.",
       notes="Awak patut jumpa doktor. / Sepatutnya dia datang semalam (he was supposed "
             "to). Softer than mesti.",
       contrast=("must_need",), markers=(r"\b(patut|sepatutnya)\b",), words=("patut",),
       level=2),
    _S("nak_want", 17, "nak / mahu — want", "nak + noun / verb",
       "Say what someone wants.",
       notes="Saya nak air suam. / Nak rehat sekejap. / Awak nak apa? mahu and hendak are "
             "the standard forms; nak is speech. Same word as the future 'nak' - context "
             "decides.",
       contrast=("akan_nak",), markers=(r"\b(nak|mahu|hendak|taknak)\b",),
       words=("nak", "mahu", "hendak"), level=1, core=True),
    _S("mungkin", 17, "mungkin / kot — maybe", "mungkin + … · … kot",
       "Say something might be so.",
       notes="Mungkin dia lambat. / Dia dah balik kot. (sentence-final kot = I think / "
             "maybe, casual). barangkali is formal.",
       markers=(r"\b(mungkin|kot|barangkali)\b",), words=("mungkin", "kot"), level=2),
    _S("sempat_dapat", 17, "sempat and dapat — have time to, manage to", "sempat + verb · dapat + verb",
       "Say whether there was time, or whether someone managed.",
       notes="Saya tak sempat makan. / Dia dapat tiket. / Tak dapat tidur. dapat + noun = "
             "get; dapat + verb = manage to.",
       markers=(r"\b(sempat|dapat)\b",), words=("sempat", "dapat"), level=2),

    # ------------------------------------------------------------------
    # 18. Adverbs and focus
    # ------------------------------------------------------------------
    _S("juga_pun", 18, "juga / pun — also, too", "… juga · … pun",
       "Say 'also' or 'too'.",
       notes="Saya pun nak. / Dia juga datang. / Saya pun sama. Speech: jugak. pun after the "
             "subject is very common.",
       markers=(r"\b(juga|jugak|pun)\b",), words=("juga", "jugak", "pun"), level=1),
    _S("only_je", 18, "je / sahaja / hanya — only, just", "… je · hanya …",
       "Say 'only' or 'just'.",
       notes="Sikit je. / Lima minit je. / Saya tanya je. sahaja and hanya are standard "
             "(hanya before, sahaja after); je and aje are speech.",
       markers=(r"\b(je|jer|aje|sahaja|saja|hanya|cuma)\b",),
       words=("je", "sahaja", "saja", "hanya", "cuma"), level=1),
    _S("very", 18, "sangat, sekali, betul — very", "sangat + adjective · adjective + sekali",
       "Make an adjective stronger.",
       notes="sangat sakit, sakit sangat (speech puts it after), cantik sekali, sedap "
             "betul, amat penting (formal). Vary the position as Malaysians do.",
       markers=(r"\b(sangat|sekali|betul|amat|sungguh)\b",),
       words=("sangat", "sekali", "betul", "amat", "sungguh"), level=1),
    _S("terlalu", 18, "terlalu — too (much)", "terlalu + adjective",
       "Say something is more than it should be.",
       notes="Terlalu panas. / Jangan tekan terlalu kuat. / Mahal sangat (speech for "
             "'too expensive'). Clinic: Terlalu kuat?",
       contrast=("very",), markers=(r"\bterlalu\b",), words=("terlalu",), level=2),
    _S("agak", 18, "agak — quite, rather", "agak + adjective",
       "Say 'quite' or 'fairly'.",
       notes="Agak jauh. / Sakitnya agak teruk. / Agak-agak (roughly) is speech. Softens "
             "a description.",
       markers=(r"\bagak\b",), words=("agak",), level=2),

    # ------------------------------------------------------------------
    # 19. Linking clauses
    # ------------------------------------------------------------------
    _S("dan_tapi_atau", 19, "dan, tapi, atau — and, but, or", "… dan … · … tapi … · … atau …",
       "Join ideas: and, but, or.",
       notes="Saya penat tapi gembira. / Teh atau kopi? / Dia makan dan tidur. tetapi is "
             "the written form of tapi.",
       markers=(r"\b(dan|tetapi|tapi|atau)\b",), words=("dan", "tetapi", "tapi", "atau"),
       level=1, core=True),
    _S("sebab", 19, "sebab / kerana — because", "… sebab …",
       "Give a reason.",
       notes="Saya tak datang sebab sakit. / Kerana hujan, dia lambat. sebab is speech, "
             "kerana writing. Never karena (Indonesian).",
       markers=(r"\b(sebab|kerana|pasal)\b",), words=("sebab", "kerana"), level=1, core=True),
    _S("jadi", 19, "jadi — so", "… , jadi …",
       "Say what follows from something.",
       notes="Dah lewat, jadi saya balik dulu. / Jadi, macam mana? Also jadi = become "
             "(jadi doktor) - keep to 'so'.",
       markers=(r"\b(jadi|maka)\b",), words=("jadi",), level=2),
    _S("kalau", 19, "kalau / jika — if", "Kalau …, …",
       "Say what happens if.",
       notes="Kalau sakit, beritahu saya. / Kalau hujan, kita tak pergi. jika is formal. "
             "Very useful in treatment instructions.",
       markers=(r"\b(kalau|jika|sekiranya)\b",), words=("kalau", "jika"), level=1, core=True),
    _S("walaupun", 19, "walaupun — although", "Walaupun …, …",
       "Say something is true despite something else.",
       notes="Walaupun penat, dia tetap kerja. / Saya pergi walaupun hujan. Don't add tapi "
             "as well (NOT Walaupun penat, tapi …).",
       markers=(r"\b(walaupun|walau|meskipun)\b",), words=("walaupun",), level=2),
    _S("supaya", 19, "supaya — so that", "… supaya …",
       "Give the purpose of an action.",
       notes="Minum air supaya tak dehidrasi. / Cakap perlahan supaya dia faham. agar is "
             "formal. untuk + verb does a similar job.",
       markers=(r"\b(supaya|agar)\b",), words=("supaya",), level=2),
    _S("before_after", 19, "sebelum / lepas — before, after", "sebelum … · lepas / selepas …",
       "Put events in order.",
       notes="Makan ubat lepas makan. / Sebelum tidur, minum air suam. / Selepas rawatan, "
             "rehat sekejap. lepas is speech, selepas standard.",
       markers=(r"\b(sebelum|lepas|selepas|sesudah)\b",), words=("sebelum", "lepas", "selepas"),
       level=1, core=True),
    _S("masa_when", 19, "masa / bila — when (in a statement)", "Masa …, … · Bila …, …",
       "Say when something happened or happens.",
       notes="Masa saya kecil, saya tinggal di Ipoh. / Bila sampai, telefon saya. Not a "
             "question here (that is bila?). semasa and ketika are formal.",
       contrast=("bila",), markers=(r"\b(masa|semasa|ketika|bila)\b",),
       words=("masa", "semasa", "ketika", "bila"), level=2),
    _S("sampai", 19, "sampai — until; arrive", "… sampai …",
       "Say how long something goes on, or that someone arrived.",
       notes="Tunggu sampai doktor panggil. / Kerja sampai malam. / Dia dah sampai (arrived). "
             "hingga / sehingga are formal.",
       markers=(r"\b(sampai|hingga|sehingga)\b",), words=("sampai", "hingga"), level=2),

    # ------------------------------------------------------------------
    # 20. Spoken particles
    # ------------------------------------------------------------------
    _S("lah_particle", 20, "lah — the all-purpose softener", "… lah",
       "Hear and use lah the way Malaysians do.",
       notes="Okeylah. / Bukanlah. / Sikit-sikit lah. / Takpelah. It softens, agrees, "
             "insists - tone decides. Don't overuse it on every sentence.",
       contrast=("lah_command",), markers=(r"\b\w*lah\b", r"\bla\b"), words=("lah", "la"),
       level=2),
    _S("final_tu_ni", 20, "tu and ni at the end — pointing with feeling", "Sedap tu! · Mahal ni.",
       "Add emphasis by ending with tu or ni.",
       notes="Pedas ni! / Betul tu. / Siapa tu? Sentence-final tu/ni points at the "
             "situation and adds feeling. Recognise and use in replies.",
       contrast=("ini_itu",), markers=(r"\b(tu|ni)\s*[.!?]*\s*$",), words=("tu", "ni"),
       level=2),

    # ------------------------------------------------------------------
    # 21. Spoken set phrases
    # ------------------------------------------------------------------
    _S("tak_payah", 21, "tak payah — no need", "Tak payah + verb",
       "Say there's no need to do something.",
       notes="Tak payah bayar. / Tak payah risau. / Tak payahlah. tidak perlu is the "
             "standard form.",
       markers=(r"\btak payah\w*\b", r"\btidak perlu\b", r"\btak perlu\b"),
       words=("payah",), level=1),
    _S("takpe", 21, "takpe — never mind, it's OK", "Takpe.",
       "Reassure someone or wave something off.",
       notes="Takpe, saya tunggu. / Tak apa, lain kali. / Takpelah. Also after an apology: "
             "Minta maaf! - Takpe.",
       markers=(r"\b(takpe|takpa|tak apa|tidak apa)\w*\b",), words=("takpe", "apa"),
       level=1),
    _S("boleh_tak", 21, "Boleh tak …? — could you…? / can I…?", "Boleh tak + verb?",
       "Make a friendly request or ask permission.",
       notes="Boleh tak tunggu sekejap? / Boleh tak saya tengok? / Boleh tak cakap "
             "perlahan sikit? Answer: Boleh. / Tak boleh.",
       contrast=("boleh",), markers=(r"\bboleh\s+tak\b",), words=("boleh", "tak"),
       level=1),
    _S("ada_tak", 21, "Ada … tak? — is there? do you have?", "Ada + noun + tak?",
       "Ask whether something is there or someone has it.",
       notes="Ada alahan tak? / Ada ubat tak? / Ada sakit kat sini tak? Answer: Ada / Takde.",
       contrast=("ada_exist",), markers=(r"\bada\b.*\btak\b",), words=("ada", "tak"),
       level=1),
    _S("jangan_risau", 21, "Jangan risau — don't worry", "Jangan risau.",
       "Reassure someone.",
       notes="Jangan risau, sikit je. / Jangan risau, tak sakit. / Janganlah risau. Useful "
             "with nervous patients.",
       markers=(r"\bjangan\w*\s+risau\b",), words=("jangan", "risau"), level=1),
    _S("mana_ada", 21, "Mana ada! — that's not true!", "Mana ada …!",
       "Deny something strongly, the casual way.",
       notes="A: Awak marah ke? B: Mana ada! / Mana ada mahal! Not a question about place "
             "here.",
       contrast=("mana",), markers=(r"\bmana ada\b",), words=("mana", "ada"), level=2),
    _S("apa_pasal", 21, "Apa pasal? — why? (casual)", "Apa pasal …?",
       "Ask why, the casual way.",
       notes="Apa pasal lambat? / Apa pasal tak datang? Casual, between friends; kenapa is "
             "neutral. Recognise apsal too.",
       contrast=("kenapa",), markers=(r"\bapa pasal\b", r"\bapsal\b"), words=("pasal",),
       level=2),

    # ------------------------------------------------------------------
    # 22. Register pairs
    # ------------------------------------------------------------------
    _S("register_pairs", 22, "Spoken and standard pairs",
       "tak · tidak   nak · hendak   dah · sudah   je · sahaja   sikit · sedikit   kat · di",
       "Recognise both forms and use the one the situation calls for.",
       notes="The same sentence in two registers: Saya tak nak / Saya tidak mahu; Dah siap / "
             "Sudah siap; Sikit je / Sedikit sahaja; Kat rumah / Di rumah. Identify tasks: "
             "which is a chat, which a notice? Produce tasks say which register to use.",
       markers=(r"\b(tak|nak|dah|je|sikit|kat|tidak|hendak|sudah|sahaja|sedikit|di)\b",),
       words=("tak", "nak", "dah", "je", "sikit", "kat", "tidak", "hendak", "sudah",
              "sahaja", "sedikit", "di"), level=1, core=True),
]

# Section 24 is written in Phase 6 (northern Malay, recognition only).
