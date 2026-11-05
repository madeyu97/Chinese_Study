# src/roleplay.py
"""
Clinic role-play: the model plays a patient, you take the history and give
the treatment instructions, in Malay, by voice or typing.

Each case is written here by hand: who the patient is, what's wrong, and
the facts the patient knows (where, how long, how bad, what makes it worse,
medicine so far). The patient's opening line is hand-written too, so a
consultation starts without a model call.

A consultation has goals, the things a practitioner has to cover: greet and
ask what's wrong, where, how long, how bad, what makes it worse, treatment
so far, explain the treatment, position the patient, check comfort, and
advice to take home. Each goal has hand-written example phrases, shown as
hints when you're stuck.

Each of your turns is one model call that does three things: grades your
Malay (correct / close / wrong, with a better version), ticks off the goals
your line covered, and writes the patient's reply from the case facts. The
reply and the better version are checked in code for Indonesian forms; a
reply that fails is rewritten once with the problem fed back.
"""

import logging

import llm
from config import GRADING_MODEL
from malay import normalise

MAX_TURNS = 14
VERDICTS = ("correct", "close", "wrong")

GOALS = [
    {"id": "greet", "task": "Greet the patient and ask what the problem is",
     "phrases": [("Apa yang boleh saya bantu?", "How can I help?"),
                 ("Ada masalah apa hari ni?", "What's the problem today?")]},
    {"id": "where", "task": "Find out exactly where it hurts",
     "phrases": [("Sakit kat mana?", "Where does it hurt?"),
                 ("Boleh tunjuk tempat yang sakit?", "Can you show me where it hurts?")]},
    {"id": "how_long", "task": "Ask how long it has been like this",
     "phrases": [("Dah berapa lama sakit?", "How long has it hurt?"),
                 ("Sejak bila?", "Since when?")]},
    {"id": "how_bad", "task": "Ask how bad it is",
     "phrases": [("Dari satu sampai sepuluh, berapa sakit?", "From one to ten, how much does it hurt?"),
                 ("Sakit sangat ke?", "Does it hurt a lot?")]},
    {"id": "worse", "task": "Ask what started it or what makes it worse",
     "phrases": [("Bila jadi lebih sakit?", "When does it get worse?"),
                 ("Macam mana boleh jadi macam ni?", "How did this happen?")]},
    {"id": "history", "task": "Ask about medicine or treatment so far",
     "phrases": [("Ada makan ubat?", "Are you taking any medicine?"),
                 ("Pernah buat rawatan sebelum ni?", "Have you had treatment before?")]},
    {"id": "explain", "task": "Explain the treatment you'll give",
     "phrases": [("Hari ni saya buat urut dan akupunktur.", "Today I'll do massage and acupuncture."),
                 ("Saya nak tekan sikit kat bahagian ni.", "I'm going to press a little here.")]},
    {"id": "position", "task": "Tell the patient how to lie, turn or breathe",
     "phrases": [("Sila baring meniarap.", "Please lie face down."),
                 ("Pusing ke kiri sikit.", "Turn a little to the left."),
                 ("Tarik nafas dalam-dalam.", "Take a deep breath.")]},
    {"id": "comfort", "task": "Check the patient is comfortable during treatment",
     "phrases": [("Sakit tak?", "Does it hurt?"),
                 ("Kalau sakit, beritahu saya ya.", "If it hurts, tell me.")]},
    {"id": "advice", "task": "Give advice for after the treatment",
     "phrases": [("Minum air banyak-banyak.", "Drink plenty of water."),
                 ("Jangan angkat barang berat dulu.", "Don't lift heavy things for now."),
                 ("Datang lagi minggu depan.", "Come again next week.")]},
]
GOAL_IDS = [g["id"] for g in GOALS]
BY_GOAL = {g["id"]: g for g in GOALS}

CASES = [
    {"id": "back", "title": "Lower back pain", "address": "encik", "voice": "ms-MY-OsmanNeural",
     "who": "a man in his forties who works in an office",
     "facts": ["pain in the lower back, more on the right side",
               "started last week after lifting a heavy box at home",
               "about seven out of ten",
               "worse in the morning and when bending down; sitting long makes it stiff",
               "no numbness in the legs",
               "took painkillers from the pharmacy, which helped a little",
               "first time having acupuncture"],
     "opening": ("Selamat pagi, doktor. Pinggang saya sakit sejak minggu lepas.",
                 "Good morning, doctor. My lower back has hurt since last week.")},
    {"id": "neck", "title": "Stiff neck and shoulders", "address": "puan", "voice": "ms-MY-YasminNeural",
     "who": "a woman in her fifties, a teacher who marks books at a desk every evening",
     "facts": ["neck and both shoulders feel stiff and achy (lenguh), the left side worse",
               "about two weeks",
               "about five out of ten",
               "hard to turn her head to the left; worse after a long day at the desk",
               "sometimes a headache at the back of the head in the evening",
               "sleeps badly because of it",
               "had a massage once last year, nothing since"],
     "opening": ("Doktor, tengkuk dengan bahu saya ni lenguh. Susah nak pusing kepala.",
                 "Doctor, my neck and shoulders ache. It's hard to turn my head.")},
    {"id": "headache", "title": "Headaches", "address": "cik", "voice": "ms-MY-YasminNeural",
     "who": "a young woman in her twenties who works long hours",
     "facts": ["pain on both sides of the head, at the temples",
               "every afternoon for the past three days, on and off for a month",
               "about six out of ten",
               "worse when stressed at work and when she skips lunch; she drinks little water",
               "sleeps only five or six hours",
               "takes paracetamol sometimes",
               "no problems with her eyes"],
     "opening": ("Saya selalu sakit kepala, doktor. Dah tiga hari macam ni.",
                 "I keep getting headaches, doctor. It's been like this for three days.")},
    {"id": "knee", "title": "Knee pain", "address": "encik", "voice": "ms-MY-OsmanNeural",
     "who": "a man in his thirties who jogs most mornings",
     "facts": ["pain on the inside of the right knee",
               "about a month",
               "about five out of ten, sharper on stairs",
               "worse going up stairs and after jogging; a little swollen (bengkak) in the evening",
               "hurt the same knee playing football years ago",
               "uses a pain-relief cream; has stopped jogging this week"],
     "opening": ("Lutut kanan saya sakit bila naik tangga.",
                 "My right knee hurts when I go up stairs.")},
    {"id": "wrist", "title": "Numb hand", "address": "puan", "voice": "ms-MY-YasminNeural",
     "who": "a woman in her forties who types all day at work",
     "facts": ["the right hand and fingers go numb (kebas) and tingle",
               "about three weeks",
               "the numbness is mild, about four out of ten, but it wakes her at night",
               "worse at night and after long typing",
               "no injury",
               "has not taken any medicine"],
     "opening": ("Tangan saya selalu kebas, terutamanya waktu malam.",
                 "My hand keeps going numb, especially at night.")},
    {"id": "sleep", "title": "Can't sleep", "address": "encik", "voice": "ms-MY-OsmanNeural",
     "who": "a man in his fifties who runs a small shop",
     "facts": ["can't stay asleep: wakes up around three in the morning and can't sleep again",
               "about a month",
               "very tired in the day",
               "worried about his business; drinks coffee in the afternoon",
               "his neck and shoulders feel tight",
               "has not taken sleeping pills and doesn't want to"],
     "opening": ("Saya susah nak tidur, doktor. Dah sebulan macam ni.",
                 "I can't sleep, doctor. It's been like this for a month.")},
]
BY_CASE = {c["id"]: c for c in CASES}


# ======================================================================
# A turn
# ======================================================================
def history_lines(turns):
    out = []
    for t in turns:
        who = "PRACTITIONER" if t["who"] == "you" else "PATIENT"
        out.append(f"{who}: {t['malay']}")
    return "\n".join(out[-12:])


def build_prompt(case, turns, said, open_goals, spoken=True, feedback=""):
    goals = "\n".join(f"- {g}: {BY_GOAL[g]['task']}" for g in open_goals) or "- (all covered)"
    return f"""
You are helping a Tui Na and acupuncture practitioner practise MALAYSIAN Malay
with patients. You play the PATIENT and you also grade the practitioner's Malay.

THE PATIENT: {case['who']}. Addressed as "{case['address']}".
What the patient knows (reveal only what is asked, one or two facts at a time):
{chr(10).join("- " + f for f in case['facts'])}

CONVERSATION SO FAR:
{history_lines(turns)}

THE PRACTITIONER JUST SAID: {said}
{"(Speech transcription: ignore spelling and punctuation; Whisper may write colloquial speech in standard spelling.)" if spoken else ""}

GOALS STILL OPEN (ids):
{goals}

Do four things.
1. verdict for the practitioner's Malay: "correct" = natural Malaysian Malay
   a patient would understand at once; "close" = understandable with small
   slips (wrong affix, odd word order, missing word); "wrong" = not
   understandable, not Malay, or Indonesian. Colloquial and standard forms
   are equally correct (tak = tidak, nak = hendak, kat = di).
2. feedback: at most two short plain-English sentences on the Malay (empty if
   perfect). better: how a Malaysian practitioner would say what they meant -
   short, natural, polite clinic Malay.
3. goals_met: ids from the open goals that this line achieved.
4. The patient's reply: natural, simple, colloquial Malaysian Malay, one or
   two short sentences, consistent with the facts, answering only what was
   asked. If the practitioner could not be understood, the patient politely
   asks them to say it again. NEVER Indonesian (boleh not bisa, tak/tidak not
   nggak, sangat not banget, ubat not obat, faham not paham, sikit not dikit).
   patient_done = true only when the practitioner has given after-care advice
   and the patient is thanking them and leaving.
{("PREVIOUS ANSWER WAS REJECTED: " + feedback) if feedback else ""}

Return ONLY JSON:
{{"verdict": "...", "feedback": "...", "better": "...", "goals_met": ["..."],
  "patient_malay": "...", "patient_english": "...", "patient_done": false}}
""".strip()


def validate(result, open_goals):
    problems = []
    if not isinstance(result, dict):
        return None, ["not a JSON object"]
    verdict = str(result.get("verdict") or "").lower()
    if verdict not in VERDICTS:
        problems.append(f"verdict must be one of {', '.join(VERDICTS)}")
    reply = str(result.get("patient_malay") or "").strip()
    if not reply:
        problems.append("patient_malay is empty")
    for field in ("patient_malay", "better"):
        indo = normalise.indonesian_in(str(result.get(field) or ""))
        if indo:
            problems.append(f"{field} uses Indonesian: " + ", ".join(
                f"{f} (Malaysian: {m})" for f, m in indo))
    met = [g for g in (result.get("goals_met") or []) if g in open_goals]
    out = {"verdict": verdict, "feedback": str(result.get("feedback") or "").strip(),
           "better": str(result.get("better") or "").strip(), "goals_met": met,
           "patient_malay": reply, "patient_english": str(result.get("patient_english") or "").strip(),
           "patient_done": bool(result.get("patient_done"))}
    return out, problems


def take_turn(case, turns, said, met_goals, spoken=True):
    """Grade one practitioner line and get the patient's reply. Returns the
    checked result, or None if the model can't be reached or keeps failing
    the checks."""
    said = (said or "").strip()
    if not said:
        return {"verdict": "wrong", "feedback": "Nothing was heard - try again.", "better": "",
                "goals_met": [], "patient_malay": "", "patient_english": "",
                "patient_done": False, "empty": True}
    open_goals = [g for g in GOAL_IDS if g not in set(met_goals)]
    feedback = ""
    for attempt in (1, 2):
        try:
            raw = llm.chat_json(GRADING_MODEL, build_prompt(case, turns, said, open_goals, spoken,
                                                            feedback), 0.4)
        except Exception as e:
            logging.warning(f"[ROLEPLAY] attempt {attempt}: {e}")
            continue
        result, problems = validate(raw, open_goals)
        if not problems:
            return result
        feedback = "; ".join(problems)
        logging.warning(f"[ROLEPLAY] attempt {attempt} rejected: {feedback}")
    return None


def next_goal(met_goals):
    """The first goal not yet covered, in consultation order."""
    return next((BY_GOAL[g] for g in GOAL_IDS if g not in set(met_goals)), None)


def summary(turns):
    """(counts by verdict, [(said, better)] worth practising)."""
    mine = [t for t in turns if t["who"] == "you" and t.get("verdict")]
    counts = {v: sum(1 for t in mine if t["verdict"] == v) for v in VERDICTS}
    fixes = [(t["malay"], t["better"]) for t in mine
             if t["verdict"] != "correct" and t.get("better")
             and normalise.tokens(t["better"]) != normalise.tokens(t["malay"])]
    return counts, fixes
