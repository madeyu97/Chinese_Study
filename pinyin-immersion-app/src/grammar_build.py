# src/grammar_build.py
"""
The Build stage (HSK track): put a sentence back together from its words.

Between hearing a structure (identify) and saying it from a situation
(produce) there was nothing in the middle - you either recognised it or
had to produce it whole. Build is that middle step: the English meaning,
the sentence's words shuffled into tiles, and you tap them into order.
Word order is where most structures live (了 after the verb, 都 after the
group, 把 + thing before the verb), so getting the order right is
practising the structure itself.

The sentences are the set's own identify sentences - already checked to
use the structure, and just heard - so Build needs no extra writing and
works on drill sets stored before it existed. Pure: the page renders it.
"""

import random
import re

import jieba

from dictionary_engine import is_cjk_char

MIN_TILES, MAX_TILES = 3, 8
PER_SET = 3

# time words that may stand before or after the subject (今天我去 / 我今天去)
TIME_WORDS = {"今天", "明天", "昨天", "现在", "早上", "晚上", "下午", "上午", "中午", "每天",
              "以前", "以后", "后来", "刚才", "最近", "今年", "明年", "去年", "周末", "星期天",
              "礼拜天", "平时", "有时候", "有时"}
SUBJECTS = {"我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "大家", "咱们", "您"}

_PUNCT = re.compile(r"[，。！？、；：,.!?;:\s“”\"'‘’（）()…—]")


def core(sentence):
    """The sentence without punctuation - what the tiles must rebuild."""
    return _PUNCT.sub("", sentence or "")


# grammar words that get a tile of their own even when jieba glues them to a
# neighbour (把门 → 把 + 门, 在家 → 在 + 家): where they go is the point
SPLIT = ("把", "被", "比", "给", "跟", "对", "往", "从", "在", "都", "也", "就", "才", "还",
         "又", "再", "没", "不")


def _is_word(w):
    """An HSK word (比赛, 可能, 没有) stays one tile; jieba's glued pairs (把门,
    在家, 去过) aren't HSK words, so they come apart."""
    try:
        import hsk
        return len(w) > 1 and hsk.word(w) is not None
    except Exception:
        return False


def _split(words, markers):
    marks = sorted(set(markers) | set(SPLIT), key=len, reverse=True)
    out = []
    for w in words:
        if w in _WHOLE or w in markers or _is_word(w):   # a word in its own right (比赛, 不错)
            out.append(w)
            continue
        if len(w) == 2 and w[1] in "过着":   # verb + aspect: 去过 → 去 + 过
            out.extend(w)
            continue
        for m in marks:
            if m in w and m != w and len(w) <= 4:
                i = w.index(m)
                out.extend(p for p in (w[:i], m, w[i + len(m):]) if p)
                break
        else:
            out.append(w)
    return out


# two-character words that start with a SPLIT character but are words in
# their own right, not grammar word + something
_WHOLE = {"不错", "不过", "不用", "不要", "不同", "不久", "不但", "不管", "不如", "还是", "还有",
          "再见", "都是", "也许", "就是", "才能", "在于", "现在", "比较", "给予", "从来", "从前",
          "对不", "对面", "跟着", "往往", "没有", "没事", "被子", "把握", "又是", "比如", "对于",
          "难过", "经过", "通过", "过去", "过来", "错过", "超过", "接着", "随着", "沿着", "顺着"}


def tiles_of(sentence, markers=(), max_tiles=None, glue=True):
    """The sentence cut into words (jieba), punctuation dropped, grammar words
    on tiles of their own - or None if it would make too few or too many
    tiles (MAX_TILES unless max_tiles says) to be a fair puzzle. glue=False
    leaves jieba's words whole rather than gluing single characters to fit."""
    most = max_tiles or MAX_TILES
    text = core(sentence)
    if not text or not all(is_cjk_char(c) for c in text):
        return None
    words = _split([w for w in jieba.lcut(text) if w.strip()], markers)
    if len(words) > most and glue:
        # fold the longest run of single characters into its neighbour until
        # it fits: 个 + 人 → 个人, keeping particles like 了 / 吗 apart
        keep = set("了吗呢吧着过的得地都也就才还又再不没把被比") | SUBJECTS

        def fold(both_single):
            for i in range(len(words) - 1):
                a, b = words[i], words[i + 1]
                if a in keep or b in keep or len(a) != 1 or (both_single and len(b) != 1):
                    continue
                words[i:i + 2] = [a + b]
                return True
            return False
        while len(words) > most:
            if not (fold(True) or fold(False)):
                return None
    return words if MIN_TILES <= len(words) <= most else None


def _shuffled(words, seed):
    rng = random.Random(seed)
    order = list(range(len(words)))
    for _ in range(20):
        rng.shuffle(order)
        if [words[i] for i in order] != words:
            return [words[i] for i in order]
    return list(reversed(words))


def items(payload, structure, n=PER_SET):
    """Up to n Build items from a set's identify sentences that use the
    structure: {"hanzi", "pinyin", "english", "tiles"}."""
    from grammar_drills import structure_problem
    out, seen = [], set()
    for it in payload.get("identify") or []:
        hanzi = str(it.get("hanzi") or "")
        if not hanzi or core(hanzi) in seen or structure_problem(hanzi, structure):
            continue
        words = tiles_of(hanzi, structure.markers)
        if not words or "".join(words) != core(hanzi):
            continue
        seen.add(core(hanzi))
        out.append({"hanzi": hanzi, "pinyin": it.get("pinyin", ""),
                    "english": it.get("english", ""), "answer": words,
                    "tiles": _shuffled(words, hanzi)})
        if len(out) == n:
            break
    return out


def check(built, item):
    """'correct' if the tiles make the sentence - or the same sentence with a
    time word on the other side of the subject (今天我去 = 我今天去) -
    else 'wrong'."""
    answer = item["answer"]
    if "".join(built) == "".join(answer):
        return "correct"
    if len(built) == len(answer) >= 2 and built[2:] == answer[2:] \
            and built[:2] == answer[1::-1][:2] \
            and {built[0], built[1]} & TIME_WORDS and {built[0], built[1]} & SUBJECTS:
        return "correct"
    return "wrong"
