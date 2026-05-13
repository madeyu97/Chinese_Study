# src/speech_engine.py
"""
Handles the recall side of the app: transcribe with Whisper, grade with LLM.
"""

import os
import json
import logging
from groq import Groq
from dotenv import load_dotenv

from config import WHISPER_MODEL, GRADING_MODEL

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def transcribe_audio(audio_bytes, filename="speech.webm"):
    """
    Send recorded audio to Groq's Whisper.
    Returns: {"text": str, "language": str, "duration": float} or None on failure.
    """
    if not audio_bytes:
        logging.error("transcribe_audio received empty bytes.")
        return None
    try:
        resp = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=WHISPER_MODEL,
            language="zh",
            response_format="verbose_json",
            temperature=0.0,
        )
        return {
            "text": (resp.text or "").strip(),
            "language": getattr(resp, "language", "zh"),
            "duration": getattr(resp, "duration", 0.0),
        }
    except Exception as e:
        logging.error(f"Whisper transcription failed: {e}")
        return None


def grade_speech(expected_chinese, expected_pinyin, expected_english, transcribed_text):
    """
    Ask the LLM to grade vocab, grammar, and (proxy) pronunciation.
    """
    prompt = f"""
You are a strict but encouraging Mandarin Chinese tutor grading a student's
spoken attempt. They were asked to say a specific sentence; below is what
the sentence was supposed to be, and what Whisper transcribed from their
recording.

EXPECTED SENTENCE
  Characters: {expected_chinese}
  Pinyin:     {expected_pinyin}
  Meaning:    {expected_english}

WHISPER TRANSCRIPTION OF STUDENT'S SPEECH
  {transcribed_text or "(empty - Whisper heard nothing intelligible)"}

Grade three criteria on a 0-10 integer scale:

1. VOCAB - did they produce the right characters / words?
   Be a little generous with near-homophone substitutions Whisper sometimes
   makes (e.g. 在 vs 再). If the meaning is preserved, that's fine.

2. GRAMMAR - is the sentence structurally well-formed AND equivalent in
   meaning to the expected sentence? A grammatical but different sentence
   should score lower here.

3. PRONUNCIATION (proxy) - inferred from Whisper transcription fidelity:
     9-10: Whisper transcribed the expected characters exactly or near-exactly
     6-8 : Most characters right, a few errors
     3-5 : Whisper produced a partly-different sentence
     0-2 : Whisper produced garbled / empty output
   Mention explicitly in feedback that this score is indirect and cannot
   assess tone accuracy.

Then map the overall performance to an SRS grade:
    "again" = effectively failed
    "hard"  = struggled but the gist was there
    "good"  = solid attempt with minor issues
    "easy"  = essentially perfect

Return ONLY a JSON object, no prose around it:
{{
  "vocab_score": <int 0-10>,
  "grammar_score": <int 0-10>,
  "pronunciation_score": <int 0-10>,
  "overall_grade": "again" | "hard" | "good" | "easy",
  "feedback": "<2-4 sentences, specific and actionable. Tell them what to fix next time. Acknowledge the pronunciation score is indirect.>"
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
        if data.get("overall_grade") not in ("again", "hard", "good", "easy"):
            avg = (data["vocab_score"] + data["grammar_score"] + data["pronunciation_score"]) / 3
            data["overall_grade"] = (
                "again" if avg < 3 else
                "hard" if avg < 6 else
                "good" if avg < 8.5 else
                "easy"
            )
        return data
    except Exception as e:
        logging.error(f"Speech grading failed: {e}")
        return None


GRADE_MAP = {"again": 0, "hard": 1, "good": 2, "easy": 3}
