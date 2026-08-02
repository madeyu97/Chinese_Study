"""
Hokkien audio.

WHY THIS IS BUILT AS A PLUGGABLE LAYER
--------------------------------------
There is no Hokkien voice in Microsoft Edge TTS (which powers the Mandarin
side), no Hokkien voice in browser speech synthesis, and no offline Hokkien
TTS package on PyPI. Synthesis therefore has to come from an external
service, and the available ones are small academic or community projects
that move, rate-limit or go offline without notice.

So rather than hard-wiring one endpoint, each provider is a small adapter.
Run `python src/test_hokkien_audio.py` to see which ones respond from your
machine, then set HOKKIEN_TTS_PROVIDER in config.py. If a provider fails at
runtime the next one is tried automatically, and if all fail the app simply
shows the card without audio instead of breaking.

ACCENT — READ THIS
------------------
Every provider below synthesises TAIWANESE Hokkien. Penang Hokkien is
Zhangzhou-based with different tone contours and some different vocabulary,
so the audio is a PRONUNCIATION REFERENCE for the consonants, vowels and
word shapes — not a model of the Penang accent. The UI labels it as such.
Treat what you hear at the hawker stall as the authority.

CACHING
-------
Generated audio is stored in the database (hokkien_audio), not just on
disk, because Streamlit Cloud wipes the filesystem on every reboot. Each
clip is therefore synthesised once, ever — which also keeps load off these
small volunteer-run services.
"""

import hashlib
import logging
import urllib.parse
import urllib.request

from hokkien_engine import tailo_to_numeric

TIMEOUT = 20
_MIN_AUDIO_BYTES = 1024          # smaller than this is an error page, not audio


# ======================================================================
# PROVIDER ADAPTERS
# Each returns (audio_bytes, mime) or raises. Endpoint formats are as
# documented by their projects / used by other community tools; the test
# script is what actually confirms them from your network.
# ======================================================================
def _http_get(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "pinyin-immersion-app/1.0 (personal study)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read()
        mime = resp.headers.get("Content-Type", "audio/wav")
    return data, mime


def _provider_ithuan(hanji, tailo):
    """意傳科技 (ithuan.tw) — Taiwanese TTS over hàn-lô text."""
    text = hanji if hanji and hanji != "—" else tailo
    url = "https://hokbu.ithuan.tw/tts?" + urllib.parse.urlencode({"taibun": text})
    return _http_get(url)


def _provider_ntut_tailo(hanji, tailo):
    """NTUT 台語 TTS, romanisation input (numeric tones)."""
    url = "http://tts001.iptcloud.net:8804/synthesize_TL?" + \
        urllib.parse.urlencode({"text1": tailo_to_numeric(tailo)})
    return _http_get(url)


def _provider_ntut_hanji(hanji, tailo):
    """NTUT 台語 TTS, hàn-jī input."""
    if not hanji or hanji == "—":
        raise ValueError("no hanji for this entry")
    url = "http://tts001.iptcloud.net:8804/synthesize_SL?" + \
        urllib.parse.urlencode({"text1": hanji})
    return _http_get(url)


PROVIDERS = {
    "ithuan": _provider_ithuan,
    "ntut_tailo": _provider_ntut_tailo,
    "ntut_hanji": _provider_ntut_hanji,
}

# Order tried when the configured provider fails.
FALLBACK_ORDER = ["ithuan", "ntut_tailo", "ntut_hanji"]


def audio_key(hanji, tailo, provider):
    raw = f"{provider}|{hanji}|{tailo}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def synthesize(hanji, tailo, provider=None):
    """Return (audio_bytes, mime, provider_used) or (None, None, None).

    Never raises: audio is a nice-to-have, and a dead endpoint must not take
    the study session down with it.
    """
    order = []
    if provider:
        order.append(provider)
    order += [p for p in FALLBACK_ORDER if p != provider]

    for name in order:
        fn = PROVIDERS.get(name)
        if not fn:
            continue
        try:
            data, mime = fn(hanji, tailo)
            if data and len(data) >= _MIN_AUDIO_BYTES:
                return data, mime, name
            logging.warning(f"[HK-TTS] {name} returned {len(data or b'')} bytes "
                            f"— treating as failure")
        except Exception as e:
            logging.warning(f"[HK-TTS] {name} failed: {e}")
    return None, None, None
