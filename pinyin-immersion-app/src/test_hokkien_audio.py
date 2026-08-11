"""
Which Hokkien TTS providers actually work from your network?

I could not test these endpoints when building the app (the build sandbox
can't reach them), and they're small academic/community services that move
or go offline. So run this once from your own machine:

    python src/test_hokkien_audio.py

It calls every provider with a known word, reports which respond with real
audio, and writes the working samples to ./tts_samples/ so you can LISTEN
and judge the quality yourself. Then set the winner in config.py:

    HOKKIEN_TTS_PROVIDER = "ithuan"      # or whichever sounded best

Optionally pre-generate audio for the whole verified deck so study sessions
never wait on a network call:

    python src/test_hokkien_audio.py --warm 200
"""

import time
import argparse
import os
import sys

from hokkien_audio import (PROVIDERS, synthesize, audio_key,
                           RATE_LIMIT_SECONDS)
from hokkien_engine import tailo_to_numeric

SAMPLES = [
    ("食飯", "tsia̍h-pn̄g", "to eat"),
    ("巴剎", "pa-sat", "wet market"),
    ("多謝", "to-siā", "thank you"),
]
OUT_DIR = "tts_samples"


def probe():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Testing {len(PROVIDERS)} providers…\n")
    working = []
    for name, fn in PROVIDERS.items():
        hanji, tailo, gloss = SAMPLES[0]
        try:
            data, mime = fn(hanji, tailo)
            ok = data and len(data) > 1024
            if ok:
                ext = "mp3" if "mp3" in (mime or "") else "wav"
                path = os.path.join(OUT_DIR, f"{name}.{ext}")
                with open(path, "wb") as f:
                    f.write(data)
                print(f"  ✅ {name:14} {len(data):>8} bytes  {mime:<24} -> {path}")
                working.append(name)
            else:
                print(f"  ❌ {name:14} responded with only "
                      f"{len(data or b'')} bytes (not audio)")
        except Exception as e:
            print(f"  ❌ {name:14} {type(e).__name__}: {e}")

    print()
    if not working:
        print("No provider responded. Options:")
        print("  • check your connection, then try again")
        print("  • these services do go down — try again later")
        print("  • the Hokkien section still works fully without audio")
        return working

    print(f"Working: {', '.join(working)}")
    print(f"Listen to the files in ./{OUT_DIR}/ and pick the best, then set")
    print(f'  HOKKIEN_TTS_PROVIDER = "{working[0]}"')
    print("in src/config.py.")
    print("\nNOTE: these voices are TAIWANESE Hokkien. Useful as a "
          "pronunciation reference, but Penang tones differ.")
    return working


def warm(limit, provider):
    """Pre-generate and cache audio for verified deck entries.

    The service allows about 3 clips per IP per minute, so this deliberately
    waits between requests. It is slow by design - roughly 20 seconds per
    clip - but it only ever has to happen once per phrase, and the clips
    land in your database where BOTH apps can serve them without ever
    calling the service again. Leave it running and come back later.
    """
    import db_manager as db
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT id, hokkien_hanji, tailo FROM hokkien_deck
                   WHERE status = 'verified' ORDER BY learn_rank LIMIT %s""",
                (limit,))
    rows = cur.fetchall()
    conn.close()
    print(f"\nWarming cache for {len(rows)} verified entries…")
    made = skipped = failed = 0
    for entry_id, hanji, tailo in rows:
        key = audio_key(hanji, tailo, provider or "auto")
        cached, _ = db.hokkien_audio_get(key)
        if cached:
            skipped += 1
            continue
        data, mime, used = synthesize(hanji, tailo, provider)
        if not data:
            failed += 1
            if failed >= 5 and made == 0:
                print("  Five failures in a row and nothing generated - "
                      "stopping rather than hammering the service.")
                break
            continue
        db.hokkien_audio_put(key, entry_id, data, mime, used)
        made += 1
        eta = (len(rows) - made - skipped) * RATE_LIMIT_SECONDS / 60
        print(f"  {made}/{len(rows)}  {hanji or tailo}   "
              f"(~{eta:.0f} min remaining)")
        time.sleep(RATE_LIMIT_SECONDS)
    print(f"Done. {made} new, {skipped} already cached, {failed} failed.")
    print("Cache:", db.hokkien_audio_stats())


def main():
    ap = argparse.ArgumentParser(description="Test/warm Hokkien TTS")
    ap.add_argument("--warm", type=int, default=0,
                    help="pre-generate audio for N verified entries "
                         "(slow: the service permits ~3 clips per minute)")
    ap.add_argument("--provider", default="",
                    help="force one provider (default: try all in order)")
    args = ap.parse_args()

    working = probe()
    if args.warm:
        if not working and not args.provider:
            print("\nSkipping warm-up — no provider is responding.")
            return 1
        warm(args.warm, args.provider or (working[0] if working else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
