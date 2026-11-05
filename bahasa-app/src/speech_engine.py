# src/speech_engine.py
"""
The speaking side of the app: transcribe with Whisper (set to Malay), grade
with the model.

Whisper tends to write what it hears in standard spelling, and sometimes in
Indonesian spelling, so a colloquial answer (tak, nak, dah) can come back as
tidak / hendak / sudah. Grading therefore accepts either register, and the
answer checker (malay/checker.py) normalises both sides before comparing.
"""

import json
import logging
import os

from dotenv import load_dotenv
from groq import Groq

from config import GRADING_MODEL, WHISPER_LANGUAGE, WHISPER_MODEL

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY") or "missing-key")

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# overall grade -> SRS grade
GRADE_MAP = {"again": 0, "hard": 1, "good": 2, "easy": 3}


def transcribe_audio(audio_bytes, filename="speech.webm"):
    """Send recorded audio to Groq's Whisper.
    Returns {"text", "language", "duration"}, or None on failure."""
    if not audio_bytes:
        logging.error("transcribe_audio received empty bytes.")
        return None
    try:
        resp = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=WHISPER_MODEL,
            language=WHISPER_LANGUAGE,
            response_format="verbose_json",
            temperature=0.0,
        )
        return {
            "text": (resp.text or "").strip(),
            "language": getattr(resp, "language", WHISPER_LANGUAGE),
            "duration": getattr(resp, "duration", 0.0),
        }
    except Exception as e:
        logging.error(f"Whisper transcription failed: {e}")
        return None


def grade_speech(expected_malay, expected_english, transcribed_text):
    """Ask the model to grade words, grammar and (proxy) pronunciation of a
    spoken attempt at a given sentence."""
    prompt = f"""
You are a strict but encouraging tutor of MALAYSIAN Malay (Bahasa Melayu as
spoken in Malaysia) grading a learner's spoken attempt. They were asked to
say a specific sentence; below is the sentence and what Whisper transcribed
from their recording.

EXPECTED SENTENCE
  Malay:   {expected_malay}
  Meaning: {expected_english}

WHISPER TRANSCRIPTION OF THE LEARNER'S SPEECH
  {transcribed_text or "(empty - Whisper heard nothing intelligible)"}

Colloquial and standard forms are BOTH correct and interchangeable: tak =
tidak, nak = hendak/mahu, dah = sudah, je = sahaja/saja, ni = ini, tu = itu,
kat = di/dekat, sikit = sedikit, takde = tiada/tak ada. Whisper often writes
colloquial speech in standard spelling, so never mark down a register swap.
Indonesian forms (bisa for boleh, karena for kerana, uang for wang/duit,
mengerti for faham) are NOT Malaysian: count them as a word error and name
the Malaysian form in the feedback.

Grade three criteria on a 0-10 integer scale:

1. VOCAB - did they produce the right words? Be a little generous with
   transcription slips that keep the meaning.
2. GRAMMAR - is the sentence well-formed AND equivalent in meaning to the
   expected one? Wrong affixes (makan for dimakan, makanan for memakan)
   count here.
3. PRONUNCIATION (proxy) - inferred from how faithfully Whisper transcribed
   the expected words:
     9-10: exact or near-exact
     6-8 : most words right, a few errors
     3-5 : a partly different sentence
     0-2 : garbled or empty
   Say in the feedback that this score is indirect.

Then map the overall performance to an SRS grade:
    "again" = effectively failed
    "hard"  = struggled but the gist was there
    "good"  = solid attempt with minor issues
    "easy"  = essentially perfect

Return ONLY a JSON object:
{{
  "vocab_score": <int 0-10>,
  "grammar_score": <int 0-10>,
  "pronunciation_score": <int 0-10>,
  "overall_grade": "again" | "hard" | "good" | "easy",
  "feedback": "<2-4 short sentences, specific and actionable>"
}}
""".strip()

    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GRADING_MODEL,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        for k in ("vocab_score", "grammar_score", "pronunciation_score"):
            data[k] = max(0, min(10, int(data.get(k, 0))))
        if data.get("overall_grade") not in GRADE_MAP:
            avg = (data["vocab_score"] + data["grammar_score"] + data["pronunciation_score"]) / 3
            data["overall_grade"] = ("again" if avg < 3 else "hard" if avg < 6
                                     else "good" if avg < 8.5 else "easy")
        return data
    except Exception as e:
        logging.error(f"Speech grading failed: {e}")
        return None
