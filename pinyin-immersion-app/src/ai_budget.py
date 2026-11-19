# src/ai_budget.py
"""
Every AI call goes through here, so the app lives within Groq's limits
instead of crashing into them.

The free plan allows each model 8,000 tokens a minute (and 200,000 a day).
One word's study material is two calls of about 4,000 tokens - so writing
words, grammar drills and sentences at once used to hit the limit within
seconds, and from then on every call sat in a queue of "429 Too Many
Requests" retries 20-30 seconds long: the first few words loaded quickly,
then everything crawled.

What this does:
- Keeps count of the tokens each model used in the last minute (and the
  calls still running), and starts a call only when its model has room.
- Each model has its own allowance, so when one is full the call moves to
  another that isn't (config.AI_FALLBACKS) instead of waiting for it.
- What's on screen goes first: work done ahead in the background
  (background()) waits while anything the learner is waiting for is
  queued, and leaves room in each model's allowance for it.
- A "429" marks the model full until the time Groq gives, and the call is
  tried elsewhere; so is a reply Groq couldn't read as JSON.
- gpt-oss models are asked to reason briefly (reasoning_effort "low"):
  their reasoning counts against the allowance, and for writing a few
  sentences the default spent more on thinking than on the answer.

ScheduledClient wraps the Groq client and has the same
client.chat.completions.create(...) and client.audio interfaces, so nothing
calling it changes.
"""

import contextlib
import logging
import re
import threading
import time
from collections import deque

from config import AI_FALLBACKS, AI_TOKENS_PER_MINUTE

WINDOW = 60.0
BACKGROUND_RESERVE = 0.35      # share of each allowance background work leaves free
FOREGROUND_WAIT = 150          # seconds a call the learner waits for may queue
BACKGROUND_WAIT = 600
_local = threading.local()


@contextlib.contextmanager
def background(still=None):
    """Calls made inside this block yield to anything the learner is
    waiting for. `still` (optional) is asked each time the call is
    considered: once it returns False - the learner has reached the card
    this was prepared for and is now waiting for it - the call stops
    yielding."""
    before = getattr(_local, "background", None)
    _local.background = still or (lambda: True)
    try:
        yield
    finally:
        _local.background = before


def priority():
    """A function telling whether the current call is background work."""
    return getattr(_local, "background", None) or (lambda: False)


def estimate_tokens(kwargs):
    """Roughly what Groq will count for a call: the prompt (about a token
    per Chinese character, four letters to a token otherwise) plus what the
    answer and its reasoning usually take."""
    text = "".join(str(m.get("content", "")) for m in kwargs.get("messages", []))
    cjk = len(re.findall(r"[㐀-鿿]", text))
    prompt = cjk + (len(text) - cjk) / 4
    out = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens") or \
        (900 if "qwen" in kwargs.get("model", "") else 1800)
    return int(prompt + out)


class _Model:
    def __init__(self, name):
        self.name = name
        self.limit = AI_TOKENS_PER_MINUTE.get(name, AI_TOKENS_PER_MINUTE.get("*", 8000))
        self.used = deque()            # (time, tokens) of calls finished in the window
        self.running = {}              # call id -> tokens reserved
        self.full_until = 0.0          # after a 429

    def load(self, now):
        while self.used and now - self.used[0][0] > WINDOW:
            self.used.popleft()
        return sum(t for _, t in self.used) + sum(self.running.values())

    def room(self, now):
        if now < self.full_until:
            return 0
        return self.limit - self.load(now)

    def frees_at(self, now, need):
        """When this model will have `need` tokens of room (roughly)."""
        if now < self.full_until:
            return self.full_until
        over = self.load(now) + min(need, self.limit) - self.limit
        for t, tokens in self.used:
            over -= tokens
            if over <= 0:
                return t + WINDOW
        return now + WINDOW


class Scheduler:
    def __init__(self, clock=time.monotonic):
        self.models = {}
        self.lock = threading.Condition()
        self.waiters = {}              # waiting call -> its "still background?" function
        self.clock = clock
        self._ids = 0

    def _foreground_waiting(self, me):
        return any(not is_bg() for w, is_bg in self.waiters.items() if w != me)

    def model(self, name):
        if name not in self.models:
            self.models[name] = _Model(name)
        return self.models[name]

    def candidates(self, name):
        return [name] + [m for m in AI_FALLBACKS.get(name, []) if m != name]

    def acquire(self, name, need, is_background=lambda: False, tried=()):
        """Wait for a model with room; returns (model name, call id).
        Background work waits while the learner waits for anything, and
        leaves part of each allowance free for them."""
        start = self.clock()
        me = object()
        with self.lock:
            self.waiters[me] = is_background
            try:
                while True:
                    now = self.clock()
                    bg = is_background()
                    names = [m for m in self.candidates(name) if m not in tried] or \
                        self.candidates(name)
                    if not (bg and self._foreground_waiting(me)):
                        # background work tries the other models first, keeping
                        # the one the learner's calls go to free for them
                        for m in (names[1:] + names[:1] if bg else names):
                            st = self.model(m)
                            spare = st.limit * BACKGROUND_RESERVE if bg else 0
                            # a call bigger than allowance-minus-reserve still runs
                            # once its model is idle
                            if st.room(now) >= min(need + spare, st.limit):
                                self._ids += 1
                                st.running[self._ids] = need
                                return m, self._ids
                    if now - start > (BACKGROUND_WAIT if bg else FOREGROUND_WAIT):
                        raise TimeoutError("no AI model had room in time")
                    soonest = min(self.model(m).frees_at(now, need) for m in names)
                    self.lock.wait(timeout=max(0.2, min(5.0, soonest - now)))
            finally:
                del self.waiters[me]
                self.lock.notify_all()

    def release(self, name, call_id, used=None):
        with self.lock:
            st = self.model(name)
            reserved = st.running.pop(call_id, 0)
            if used is not None:
                st.used.append((self.clock(), used or reserved))
            self.lock.notify_all()

    def mark_full(self, name, seconds):
        with self.lock:
            st = self.model(name)
            st.full_until = max(st.full_until, self.clock() + seconds)
            self.lock.notify_all()


def _retry_after(err):
    """Seconds Groq asks us to wait, from the header or the message."""
    try:
        v = err.response.headers.get("retry-after")
        if v:
            return float(v)
    except Exception:
        pass
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(err))
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    m = re.search(r"try again in (\d+)m", str(err))
    return int(m.group(1)) * 60 if m else 20.0


class _Completions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        sched, inner = self.owner.scheduler, self.owner.inner
        import groq
        wanted, tried, attempts = kwargs["model"], [], 0
        is_bg = priority()
        while True:
            attempts += 1
            need = estimate_tokens(kwargs)
            name, call_id = sched.acquire(wanted, need, is_bg, tried)
            call = dict(kwargs, model=name)
            if "qwen" in name:
                call["reasoning_effort"] = "none"     # answer straight away, as JSON
            elif name.startswith("openai/gpt-oss"):
                if call.get("reasoning_effort") in (None, "none"):
                    call["reasoning_effort"] = "low"
            else:
                call.pop("reasoning_effort", None)
            try:
                resp = inner.chat.completions.create(**call)
            except groq.RateLimitError as e:
                wait = _retry_after(e)
                sched.release(name, call_id, used=need)
                sched.mark_full(name, wait)
                logging.warning(f"[AI] {name} at its limit for {wait:.0f}s"
                                f"{' (daily)' if 'per day' in str(e) else ''}; trying elsewhere")
                tried.append(name)
                if attempts >= 6:
                    raise
                continue
            except (groq.BadRequestError, groq.InternalServerError, groq.APIConnectionError,
                    groq.APITimeoutError) as e:
                sched.release(name, call_id, used=need // 2)
                retryable = not isinstance(e, groq.BadRequestError) or "json_validate_failed" in str(e)
                if not retryable or attempts >= 3:
                    raise
                logging.warning(f"[AI] {name}: {str(e)[:120]} - trying again")
                tried.append(name)
                continue
            except Exception:
                sched.release(name, call_id)
                raise
            usage = getattr(resp, "usage", None)
            sched.release(name, call_id, used=getattr(usage, "total_tokens", None) or need)
            if name != wanted:
                logging.info(f"[AI] {wanted} was full: answered by {name}")
            return resp


class _Chat:
    def __init__(self, owner):
        self.completions = _Completions(owner)


class ScheduledClient:
    """The Groq client, with every chat call scheduled (see module doc)."""

    def __init__(self, inner, scheduler=None, audio=None):
        self.inner = inner
        self.scheduler = scheduler or Scheduler()
        self.chat = _Chat(self)
        self._audio = audio

    @property
    def audio(self):                      # Whisper: its own limits, the client's own retries
        return (self._audio or self.inner).audio

    def __getattr__(self, name):
        return getattr(self.inner, name)
