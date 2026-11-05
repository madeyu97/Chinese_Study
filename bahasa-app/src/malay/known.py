"""Which words in a Malay sentence has the learner not met?

Used to keep generated sentences inside the learner's vocabulary (at most
one new word). A token counts as known when:
  - it is a function word or core word (below), a number, or on the
    learner's list;
  - it is a colloquial / standard variant of a known word (tak = tidak);
  - it is a known word plus clitics (rumahnya, bukulah, kubawa);
  - it is another voice of a known verb: makan / memakan / dimakan,
    masukkan / memasukkan / dimasukkan (same root, same suffix);
  - it is a plain reduplication of a known word (budak-budak).
Other derivations (ajar -> pelajaran) are new words: their meaning has to
be learned, so they are reported as unknown.
"""
from __future__ import annotations

from malay import morphology, normalise

FUNCTION_WORDS = set("""
saya aku awak kamu engkau kau anda dia ia beliau kami kita mereka korang diorang
ini itu ni tu sini sana situ yang dan atau tetapi tapi serta
di ke dari daripada pada kepada untuk dengan oleh dalam tentang hingga sampai
akan sudah dah telah belum masih sedang baru pernah
tidak tak bukan jangan tiada takde ada
ialah adalah juga pun lah kah tah je sahaja saja kan ya
sangat amat paling lebih kurang terlalu
semua setiap banyak sedikit sikit beberapa
apa siapa mana bila kenapa mengapa bagaimana berapa macam
nak hendak mahu boleh dapat perlu mesti harus mungkin
oh eh ah hah hmm okey ok
satu dua tiga empat lima enam tujuh lapan sembilan sepuluh sebelas belas puluh ratus
ribu juta seratus seribu kosong
encik puan cik
""".split())

# A few everyday content words any sentence may lean on, as the Chinese app
# allowed 人, 东西, 去, 来, 说: without them a beginner's sentences can't be
# written at all.
CORE_WORDS = set("""
orang benda perkara masa waktu tempat hari pergi datang balik cakap kata buat bagi
baik bagus besar kecil
""".split())


def _keys(word):
    """Ways a known word makes other forms known."""
    a = morphology.analyse(word)
    return {word, a.voice_key}


def allowed_set(known_words, extra=()):
    """Everything that counts as known, precomputed for fast checks."""
    words = {w.lower() for w in known_words} | FUNCTION_WORDS | CORE_WORDS | \
        {w.lower() for w in extra}
    canon = set()
    for w in list(words):
        canon.update(normalise.canonical(w))
    keys = set()
    for w in words | canon:
        if " " not in w:
            keys |= _keys(w)
    return {"words": words | canon, "keys": keys}


def is_known(token, allowed):
    t = token.lower()
    if t in allowed["words"] or t.isdigit():
        return True
    if all(c in allowed["words"] for c in normalise.canonical(t)):
        return True
    a = morphology.analyse(t)
    if a.voice_key in allowed["keys"]:
        return True
    if "-" in t:
        left, _, right = t.partition("-")
        if left == right and is_known(left, allowed):
            return True
    return False


def unknown_words(text, allowed):
    """Tokens in `text` the learner hasn't met, in order, without repeats."""
    if not isinstance(allowed, dict):
        allowed = allowed_set(allowed)
    out = []
    for tok in normalise.tokens(text):
        if not is_known(tok, allowed) and tok not in out:
            out.append(tok)
    return out


def same_word(token, word):
    """Is `token` a form of `word` (itself, the other register, with clitics,
    or another voice: dimakan / makannya for makan)?"""
    t, w = token.lower(), word.lower()
    if t == w or normalise.canonical(t) == normalise.canonical(w):
        return True
    return morphology.analyse(t).voice_key == morphology.analyse(w).voice_key


def words_used(text, words):
    """Which of `words` appear in the text, in any of their forms."""
    toks = normalise.tokens(text)
    return [w for w in words if any(same_word(t, w) for t in toks)]
