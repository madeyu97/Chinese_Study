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


def _provider_ithuan_tailo(hanji, tailo):
    """意傳科技 hap-sing - the audio service behind 鬥拍字 (suisiann.ithuan.tw).

    Endpoint taken from the project's own frontend
    (github.com/i3thuan5/TauPhahJi-BangTsam), which builds
        https://hapsing.ithuan.tw/bangtsam?taibun=<KIP romanisation>
    Diacritic Tâi-lô is what the site displays and passes, so it is tried
    first.
    """
    url = "https://hapsing.ithuan.tw/bangtsam?" + \
        urllib.parse.urlencode({"taibun": tailo})
    return _http_get(url)


def _provider_ithuan_numeric(hanji, tailo):
    """Same service, numeric tones (tsiah8-png7) in case it prefers them."""
    url = "https://hapsing.ithuan.tw/bangtsam?" + \
        urllib.parse.urlencode({"taibun": tailo_to_numeric(tailo)})
    return _http_get(url)


def _provider_ithuan_hanji(hanji, tailo):
    """Same service given hàn-jī instead of romanisation."""
    if not hanji or hanji == "—":
        raise ValueError("no hanji for this entry")
    url = "https://hapsing.ithuan.tw/bangtsam?" + \
        urllib.parse.urlencode({"taibun": hanji})
    return _http_get(url)


PROVIDERS = {
    "ithuan_tailo": _provider_ithuan_tailo,
    "ithuan_numeric": _provider_ithuan_numeric,
    "ithuan_hanji": _provider_ithuan_hanji,
}

# Order tried when the configured provider fails.
FALLBACK_ORDER = ["ithuan_tailo", "ithuan_numeric", "ithuan_hanji"]

# The service asks for no more than 3 clips per IP per minute
# ("1 IP 1分鐘內上 tsē 下載 3 句音檔"). It is run by a small non-profit and
# costs them real money, so the warm-up path honours this strictly.
RATE_LIMIT_SECONDS = 21


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
