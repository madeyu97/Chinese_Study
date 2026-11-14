# src/clock.py
"""
The learner's clock, not the server's.

Streamlit Cloud and Supabase run on UTC, which in Malaysia (UTC+8) put the
start of "today" at 8am - in the middle of a morning session. Everything
that asks what day or time it is goes through here instead.

A study day starts at 4am local time, as in Anki: a session at 1am still
counts towards the day you were in, and the morning's reviews are ready
when you wake. The time zone comes from APP_TZ (an environment variable or
Streamlit secret), Asia/Kuala_Lumpur by default.
"""

import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Kuala_Lumpur"
DAY_STARTS_AT = 4          # local hour at which a new study day begins


def tz():
    name = os.getenv("APP_TZ")
    if not name:
        try:
            import streamlit as st
            name = st.secrets.get("APP_TZ")
        except Exception:
            name = None
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def now():
    """The local time now, time-zone aware."""
    return datetime.now(tz())


def study_day(moment):
    """The study day a local moment belongs to."""
    return (moment - timedelta(hours=DAY_STARTS_AT)).date()


def today():
    """Today's study day (a date)."""
    return study_day(now())


def day_start(day=None):
    """When a study day began, as a time-zone aware datetime."""
    return datetime.combine(day or today(), time(DAY_STARTS_AT), tz())
