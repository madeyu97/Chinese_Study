# src/utara.py
"""
Northern Malay (loghat utara: Penang, Kedah, Perlis) for recognition. You
learn to understand it, never to produce it: the Words page and every
checker still treat standard and colloquial Malaysian Malay as the target.

WORDS are the everyday northern forms with their standard partner. They are
also on the lesson list (tag Utara), so they arrive on the Words page after
your first 300 words, recognition only.

SOUND_RULES are the regular sound changes that turn standard words into
northern ones (besar -> besaq, kenal -> kenai, panas -> panaih); once you
know them, most northern words are words you already know.

SENTENCES are hand-written Penang lines, each with the standard Malay and
the English. The Penang page plays one and asks what it means, or shows it
and asks for the standard form. Each sentence is spaced in drill_progress
(drill "utara").

The app's voices are standard Malaysian, so the audio is northern words in a
standard accent: good for the words, not for the tune.
"""

import random
import re

DRILL = "utara"
ITEMS_PER_SESSION = 8
NEW_PER_SESSION = 4
NEW_PER_DAY = 6
MIN_KNOWN = 60

# (northern, standard, English)
WORDS = [
    ("hang", "awak / kamu", "you"),
    ("hampa", "korang / kamu semua", "you (plural)"),
    ("depa", "mereka", "they"),
    ("cheq", "saya", "I, me"),
    ("pi", "pergi", "go"),
    ("mai", "mari / datang", "come"),
    ("awat", "kenapa", "why"),
    ("pasai", "sebab / pasal", "because; about"),
    ("habaq", "beritahu", "tell"),
    ("toksah", "tak payah", "no need to; don't bother"),
    ("satgi", "sekejap lagi / nanti", "in a while, later"),
    ("sat", "sekejap", "a moment"),
    ("la ni", "sekarang", "now"),
    ("dok", "sedang / tinggal", "be doing (dok makan); live, stay (dok mana)"),
    ("lagu mana", "macam mana", "how"),
    ("lagu tu", "macam tu", "like that"),
    ("tang", "kat / di", "at (a spot): tang mana = where exactly"),
    ("hat", "yang", "the one that, which"),
    ("ka", "ke", "question particle (Hang nak ka?)"),
    ("dak", "tak", "not (in betoi ka dak? = true or not?)"),
    ("noh", "kan", "isn't it? right? (end of a sentence)"),
    ("tak dan", "tak sempat", "no time to; didn't manage to"),
    ("takpa", "tak apa", "never mind, it's fine"),
    ("teruih", "terus", "straight on; straight away"),
    ("habih", "habis", "finished, all gone"),
    ("betoi", "betul", "right, true"),
    ("besaq", "besar", "big"),
    ("lapaq", "lapar", "hungry"),
    ("pasaq", "pasar", "market"),
    ("keluaq", "keluar", "go out"),
    ("tinggai", "tinggal", "live, stay; leave behind"),
    ("kenai", "kenal", "know (a person)"),
    ("panaih", "panas", "hot"),
    ("manih", "manis", "sweet"),
]
BY_WORD = {w: (s, e) for w, s, e in WORDS}

SOUND_RULES = [
    ("-ar → -aq", [("besar", "besaq"), ("lapar", "lapaq"), ("pasar", "pasaq"), ("keluar", "keluaq")]),
    ("-al, -ul → -ai, -oi", [("tinggal", "tinggai"), ("kenal", "kenai"), ("betul", "betoi")]),
    ("-as, -us → -aih, -uih", [("panas", "panaih"), ("terus", "teruih")]),
    ("-is → -ih", [("manis", "manih"), ("habis", "habih")]),
    ("final -a stays a full 'a'", [("apa", "apa (not 'ape')"), ("mana", "mana (not 'mane')")]),
]

# (northern, standard, English)
SENTENCES = [
    ("Hang nak pi mana?", "Awak nak pergi mana?", "Where are you going?"),
    ("Cheq nak pi pasaq.", "Saya nak pergi pasar.", "I'm going to the market."),
    ("Awat hang mai lambat?", "Kenapa awak datang lambat?", "Why did you come late?"),
    ("Pasai hujan lebat tadi.", "Sebab hujan lebat tadi.", "Because it rained heavily earlier."),
    ("Depa dok makan kat kedai tu.", "Mereka sedang makan di kedai itu.", "They're eating at that shop."),
    ("Hang dok buat apa tu?", "Awak sedang buat apa tu?", "What are you doing?"),
    ("Mai sini sat.", "Mari sini sekejap.", "Come here a moment."),
    ("Tunggu sat, cheq mai satgi.", "Tunggu sekejap, saya datang nanti.",
     "Wait a moment, I'll come in a bit."),
    ("La ni cheq tak dan.", "Sekarang saya tak sempat.", "I don't have time right now."),
    ("Toksah risau.", "Tak payah risau.", "Don't worry."),
    ("Habaq kat dia cheq dah sampai.", "Beritahu dia saya dah sampai.",
     "Tell him/her I've arrived."),
    ("Lagu mana nak pi Balik Pulau?", "Macam mana nak pergi Balik Pulau?",
     "How do I get to Balik Pulau?"),
    ("Pi teruih, pastu belok kiri.", "Pergi terus, lepas tu belok kiri.",
     "Go straight on, then turn left."),
    ("Panaih sungguh hari ni.", "Panas sungguh hari ni.", "It's really hot today."),
    ("Cheq dah lapaq ni.", "Saya dah lapar ni.", "I'm hungry now."),
    ("Nasi kandaq ni sedap noh?", "Nasi kandar ni sedap, kan?", "This nasi kandar is good, isn't it?"),
    ("Rumah dia besaq.", "Rumah dia besar.", "His/her house is big."),
    ("Hang kenai dia ka?", "Awak kenal dia ke?", "Do you know him/her?"),
    ("Betoi ka dak?", "Betul ke tak?", "Is that true or not?"),
    ("Hat merah tu cheq punya.", "Yang merah tu saya punya.", "The red one is mine."),
    ("Hampa dok mana?", "Korang tinggal mana?", "Where do you all live?"),
    ("Depa tinggai kat Jelutong.", "Mereka tinggal di Jelutong.", "They live in Jelutong."),
    ("Takpa, lain kali.", "Tak apa, lain kali.", "Never mind, next time."),
    ("Teh ni manih sangat.", "Teh ni manis sangat.", "This tea is very sweet."),
    ("Duit cheq dah habih.", "Duit saya dah habis.", "My money's all gone."),
    ("Sakit tang mana?", "Sakit kat mana?", "Where does it hurt?"),
    ("Sakit tang ni, doktor.", "Sakit kat sini, doktor.", "It hurts here, doctor."),
    ("Awat lutut hang bengkak?", "Kenapa lutut awak bengkak?", "Why is your knee swollen?"),
    ("Cheq tak dan makan ubat pagi tadi.", "Saya tak sempat makan ubat pagi tadi.",
     "I didn't manage to take my medicine this morning."),
    ("Pinggang cheq sakit pasai angkat kotak.", "Pinggang saya sakit sebab angkat kotak.",
     "My lower back hurts because I lifted a box."),
    ("Hang baring sat, toksah bangun lagi.", "Awak baring sekejap, tak payah bangun lagi.",
     "Lie down a moment, don't get up yet."),
    ("Satgi cheq mai balik.", "Nanti saya datang balik.", "I'll come back in a bit."),
]


def key(sentence):
    """A stable key for drill_progress: the northern sentence, lowercased."""
    return re.sub(r"[^a-z ]", "", sentence.lower()).strip()


def northern_words(sentence):
    """[(northern, standard, English)] for the northern words in a sentence,
    two-word forms (la ni, tak dan) included."""
    text = " " + re.sub(r"[^a-z ]", " ", sentence.lower()) + " "
    found = []
    for w, s, e in sorted(WORDS, key=lambda x: -len(x[0])):
        if f" {w} " in text:
            found.append((w, s, e))
            text = text.replace(f" {w} ", " " + "_" * len(w) + " ")
    order = sentence.lower()
    return sorted(found, key=lambda x: order.find(x[0]))


def pick(progress, today, new_left, n=ITEMS_PER_SESSION):
    """Sentence indexes for a session: due ones (oldest first), then new
    ones in list order, at most new_left."""
    today = today.isoformat() if hasattr(today, "isoformat") else str(today)
    keyed = [(i, key(s[0])) for i, s in enumerate(SENTENCES)]
    due = [i for i, k in keyed if k in progress and (progress[k].get("next_review_date") or "") <= today]
    due.sort(key=lambda i: progress[key(SENTENCES[i][0])].get("next_review_date") or "")
    fresh = [i for i, k in keyed if k not in progress][:max(0, min(new_left, NEW_PER_SESSION))]
    return (due + fresh)[:n]


def item(i, rng, kind=None):
    """One question about sentence i: hear it and pick the meaning, or read
    it and pick the standard Malay."""
    north, std, en = SENTENCES[i]
    kind = kind or rng.choice(("hear", "read"))
    others = [s for j, s in enumerate(SENTENCES) if j != i]
    rng.shuffle(others)
    if kind == "hear":
        opts = [en] + [o[2] for o in others[:3]]
        question = "What did you hear?"
    else:
        opts = [std] + [o[1] for o in others[:3]]
        question = "Which standard Malay says the same?"
    answer = opts[0]
    rng.shuffle(opts)
    return {"i": i, "key": key(north), "kind": kind, "north": north, "standard": std,
            "english": en, "question": question, "options": opts, "answer": answer,
            "words": northern_words(north)}


def build_session(progress, today, new_left, rng=None):
    rng = rng or random.Random()
    return [item(i, rng) for i in pick(progress, today, new_left)]
