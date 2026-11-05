# src/llm.py
"""
One place for model calls that return JSON. Every writer in the app (word
content, contrasts, mnemonics, later the sentence and grammar writers) goes
through chat_json, so tests replace `client` once.
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY") or "missing-key")

# Writes per item before giving up: each rejected draft is rewritten with
# the problems fed back.
MAX_ATTEMPTS = 3


def chat_json(model, prompt, temperature):
    kwargs = dict(messages=[{"role": "user", "content": prompt}], model=model,
                  response_format={"type": "json_object"}, temperature=temperature)
    if "qwen" in model:
        kwargs["reasoning_effort"] = "none"
    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    return json.loads(text)
