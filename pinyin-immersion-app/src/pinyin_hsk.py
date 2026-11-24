# src/pinyin_hsk.py
"""
Pinyin for a Chinese sentence, the way HSK textbooks print it.

pypinyin reads each character from its phrase list, which is right for most
words but wrong for the little words whose reading depends on what's around
them. Checked against the HSK 3.0 deck's hand-written pinyin for the 1,066
official example sentences (tools/check_pinyin.py), these are put right here:

  地   de after a description (高兴地说), dì as ground (地上)
  得   de after a verb (说得好), děi as "must" (今天得复习)
  长   cháng long (很长), zhǎng grow (长大, 长得)
  都 dōu · 教 jiāo · 查 chá · 谁 shéi · 还 huán (还书, 还给)
  只   zhī counting animals (一只猫), zhǐ only
  了   liǎo in 不了 / 得了 (改变不了)
  一 不 their written tone changes (一个 yí, 一天 yì, 不是 bú; 第一,
       星期一 stay yī), and toneless in 想一想 and 去不去
  个 ge after a number or 这/那 · 里边 lǐbian · 喂 wéi on the phone
  儿   joined to the word before (哪儿 nǎr, 一点儿 yìdiǎnr)
  numbers written in digits: 2022年 èr líng èr èr nián, 2月 èr yuè
  toneless second syllables: 喜欢 xǐhuan, 漂亮 piàoliang, 妈妈 māma

Third-tone changes are not written (你好 nǐ hǎo), as in the textbooks.
Syllables come back separated by spaces, one per character except 儿.
"""

import functools
import re

from pypinyin import Style, lazy_pinyin

_CJK = re.compile(r"[一-鿿]+")
_FOURTH = set("àèìòùǜ")
_PLAIN = str.maketrans("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ", "aaaaeeeeiiiioooouuuuüüüü")
_DIGITS = "零一二三四五六七八九"
_NUMERALS = set("零一二两三四五六七八九十百千万几半")
_MEASURES = set("个本张条只件位家辆台座双杯块把片种次顿场部间门套份项道名所棵封支头颗篇首架节层朵盘碗瓶盒包段幅口岁")

# toneless second (or last) syllables
_NEUTRAL_WORDS = {
    "东西", "朋友", "知道", "衣服", "时候", "地方", "喜欢", "认识", "觉得", "休息", "明白",
    "便宜", "漂亮", "舒服", "客气", "意思", "事情", "名字", "眼睛", "关系", "先生", "学生",
    "早上", "晚上", "多少", "告诉", "清楚", "麻烦", "聪明", "热闹", "暖和", "凉快", "厉害",
    "打扮", "收拾", "商量", "消息", "生意", "师傅", "护士", "大夫", "丈夫", "姑娘",
    "部分", "困难", "主意", "窗户", "头发", "耳朵", "脑袋", "眉毛", "胳膊", "月亮", "太阳",
    "工夫", "功夫", "钥匙", "玻璃", "衣裳", "吩咐", "答应", "打听", "欺负", "笑话", "合同",
    "规矩", "结实", "糊涂", "马虎", "爱人", "客人", "地道", "力气", "脾气", "运气", "口气",
    "豆腐", "萝卜", "葡萄", "本事", "故事", "早晨", "还是", "别人", "记得", "认得", "懂得",
    "值得", "显得", "舍得", "心里", "晚上", "那边", "这边", "哪边", "那里", "这里", "哪里",
    "看见", "听见", "下巴", "嘴巴", "尾巴", "石头", "木头", "骨头", "馒头",
    "里头", "外头", "前头", "后头", "上头", "枕头", "念头", "码头", "喇叭", "琵琶", "蘑菇",
    "芝麻", "玫瑰", "狐狸", "骆驼", "疙瘩", "动静", "比方", "称呼", "风筝", "将就", "讲究",
    "交情", "叫唤", "觉悟", "宽敞", "苗条", "模糊", "便当", "体面", "应酬", "招呼", "折腾",
    "主意", "嘱咐", "琢磨", "作坊", "牌子", "知识", "认真", "要是", "味道", "咳嗽",
}
_NEUTRAL_WORDS -= {"认真", "看见", "听见", "那里", "这里", "哪里", "交情", "觉悟",
                   "体面", "便当"}
_FIXED = {"照片": ("zhào", "piàn"), "差不多": ("chà", "bu", "duō"),
          "对不起": ("duì", "bu", "qǐ"), "来不及": ("lái", "bu", "jí"),
          "了不起": ("liǎo", "bu", "qǐ"), "大学生": ("dà", "xué", "shēng"),
          "留学生": ("liú", "xué", "shēng"), "中学生": ("zhōng", "xué", "shēng"),
          "小学生": ("xiǎo", "xué", "shēng"), "研究生": ("yán", "jiū", "shēng"),
          "适应": ("shì", "yìng"), "为了": ("wèi", "le"), "因为": ("yīn", "wèi"),
          "为什么": ("wèi", "shén", "me"), "成为": ("chéng", "wéi"), "认为": ("rèn", "wéi"),
          "以为": ("yǐ", "wéi"), "作为": ("zuò", "wéi"), "行为": ("xíng", "wéi")}
_VERB_DOUBLES = set("看想试说听走等问找玩聊尝学练读写坐唱跳跑帮游洗休谈逛笑动比查摸闻")
_FAMILY = set("妈爸哥姐弟妹爷奶星谢叔婶舅姑")
_DIRS = set("过出起上下回进开")
# words ending in 得 that are words in their own right
_DE_WORDS = {"觉得", "记得", "认得", "懂得", "值得", "显得", "舍得", "晓得", "获得", "取得",
             "赢得", "难得", "使得", "免得", "省得", "来得", "落得", "博得", "求得", "心得"}
# verbs a direction is added to (走过来, 拿出去) and that take 过 (去过, 吃过)
_VERBS = set("走跑拿买开站送飞带搬爬跳坐寄传拉推放提举抬递扔接借还写看找想说唱聊笑哭"
             "去来吃喝听学见用做读玩卖住到试爱打穿等问讲教画骑游参经遇碰尝种睡管忘记变"
             "离完分考干成")
_NOT_VERB = set("我你他她它们也都就还又再快已没不别从在往向到这那很太真最更才能会要想该")
_NEUTRAL_SUFFIX = set("们么子")
_PLACE_SUFFIX = {"边", "面"}
_PLACE_FIRST = set("里外前后左右上下")
_ERHUA_NOT = {"女儿", "婴儿", "孤儿", "健儿", "幼儿", "儿子", "儿童", "儿歌", "儿女", "无儿",
              "男儿", "孙儿", "胎儿"}


# ----------------------------------------------------------------------
# numbers in digits
# ----------------------------------------------------------------------
def _small(n):
    """1-9999 in characters: 106 一百零六, 2350 两千三百五十."""
    units = [(1000, "千"), (100, "百"), (10, "十")]
    out, zero = "", False
    for size, name in units:
        d, n = divmod(n, size)
        if d:
            if zero:
                out += "零"
            out += ("两" if d == 2 and size >= 1000 else _DIGITS[d]) + name
            zero = False
        elif out:
            zero = True
    if n:
        out += ("零" if zero else "") + _DIGITS[n]
    return out[1:] if out.startswith("一十") else out


def number_chars(digits, after=""):
    """Digits as they're read: years and bus or room numbers one by one
    (2022年, 304路), counts as numbers (2个 两个, 58 五十八)."""
    if (len(digits) == 4 and after[:1] == "年") or (len(digits) >= 3 and after[:1] and after[:1] in "路号室") \
            or len(digits) >= 9 or (digits.startswith("0") and len(digits) > 1):
        return "".join(_DIGITS[int(d)] for d in digits)
    n = int(digits)
    if n == 0:
        return "零"
    if n >= 10000:
        high, low = divmod(n, 10000)
        return _small(high) + "万" + ("零" if 0 < low < 1000 else "") + (_small(low) if low else "")
    if n == 2 and after[:1] in _MEASURES | set("万千百"):
        return "两"
    return _small(n)


def _spell_digits(text):
    def decimal(m):
        whole, frac = m.group(1), m.group(2)
        out = number_chars(whole) + "点" + "".join(_DIGITS[int(d)] for d in frac)
        return out
    text = re.sub(r"(\d+(?:\.\d+)?)%", lambda m: "百分之" + m.group(1), text)
    text = re.sub(r"(\d+)\.(\d+)", decimal, text)
    return re.sub(r"\d+", lambda m: number_chars(m.group(), text[m.end():m.end() + 1]), text)


# ----------------------------------------------------------------------
# the readings
# ----------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _words():
    import hsk
    return {w["word"] for w in hsk.words_upto(4, include_erhua=True)}


def _dict_word(w):
    """In jieba's dictionary (项目, 特地, 地板) or the HSK list?"""
    if not w or len(w) < 2:
        return False
    import jieba
    if not jieba.dt.initialized:
        jieba.initialize()
    return jieba.dt.FREQ.get(w, 0) > 0 or w in _words()


def _neutral(seg, syl):
    """Toneless syllables, in place: 喜欢 xǐhuan, 妈妈 māma, 看看 kànkan,
    我们 wǒmen, 里边 lǐbian, 走过来 zǒuguòlai."""
    import jieba
    n = len(seg)
    for w in sorted(_NEUTRAL_WORDS, key=len, reverse=True):
        for m in re.finditer(re.escape(w), seg):
            syl[m.end() - 1] = syl[m.end() - 1].translate(_PLAIN)
    for w, readings in _FIXED.items():
        for m in re.finditer(re.escape(w), seg):
            syl[m.start():m.end()] = list(readings)
    i = 0
    for w in jieba.lcut(seg):
        k = len(w)
        if k >= 2 and w[-1] in _NEUTRAL_SUFFIX and not (w[-1] == "子" and k > 2) \
                and w not in {"孔子", "老子", "原子", "电子", "分子", "孙子"}:
            syl[i + k - 1] = syl[i + k - 1].translate(_PLAIN)
        i += k
    for i in range(1, n):
        c, p = seg[i], seg[i - 1]
        aabb = (i + 2 < n and seg[i + 1] == seg[i + 2]) or (i >= 3 and seg[i - 3] == seg[i - 2])
        if c == p and (c in _FAMILY or (c in _VERB_DOUBLES and not aabb
                                        and seg[i - 2:i] not in _words())):
            syl[i] = syl[i].translate(_PLAIN)                   # 妈妈, 看看
        elif c in _PLACE_SUFFIX and p in _PLACE_FIRST:
            syl[i] = syl[i].translate(_PLAIN)                   # 里边, 外面
        elif c in "来去" and p in _DIRS and i >= 2 and seg[i - 2] in _VERBS \
                and seg[i - 2:i] not in ("一起",):
            syl[i] = syl[i].translate(_PLAIN)                   # 走过来, 拿出去


def _segment(seg):
    """Syllables for a run of characters with no punctuation in it."""
    words = _words()
    syl = lazy_pinyin(seg, style=Style.TONE)
    for i, c in enumerate(seg):              # tone changes are worked out below
        if c == "一":
            syl[i] = "yī"
        elif c == "不":
            syl[i] = "bù"
        elif c == "了" and seg[i:i + 2] not in ("了解", "了不"):
            syl[i] = "le"
        elif c == "的" and not ((seg[i - 1:i + 1] == "目的" and not _dict_word(seg[i - 2:i]))
                               or seg[i:i + 2] in ("的确", "的士")):
            syl[i] = "de"
    _neutral(seg, syl)
    out = list(syl)
    n = len(seg)

    def after(i, chars):
        return i > 0 and seg[i - 1] in chars

    for i, c in enumerate(seg):
        p = seg[i - 1] if i else ""
        nx = seg[i + 1] if i + 1 < n else ""
        two_l = seg[i - 1:i + 1] if i else ""
        two_r = seg[i:i + 2] if i + 1 < n else ""
        if c == "地":
            word_l = _dict_word(two_l) and not _dict_word(seg[i - 2:i])
            if not (word_l or _dict_word(two_r) or (nx and nx in "上下里面方点图铁址区球")
                    or after(i, "在满土当本各外草")):
                out[i] = "de"                                   # 高兴地说
        elif c == "得":
            if two_r == "得到":
                out[i] = "dé"
            elif two_l in _DE_WORDS or (two_r and two_r[1] in "到分意出知" and _dict_word(two_r)):
                pass                                            # 觉得, 得到 (pypinyin has them)
            elif not p or after(i, "也就还都总必我你他她们天定要可非"):
                out[i] = "děi"                                  # 今天得复习
            else:
                out[i] = "de"                                   # 说得好
        elif c == "长":
            if two_r in ("长城", "长江", "长期", "长途", "长度", "长短") or \
                    after(i, "很太多真最更较这那么好不") or (nx and nx in "时期短久度"):
                out[i] = "cháng"
            elif (nx and nx in "大高得成出胖着") or two_l in (
                    "成长", "生长", "校长", "家长", "部长", "院长", "班长", "市长", "队长"):
                out[i] = "zhǎng"
        elif c == "都" and two_l != "首都" and two_r != "都市":
            out[i] = "dōu"
        elif c == "教" and not (two_r in words or two_l in words):
            out[i] = "jiāo"                                     # 教我们
        elif c == "查":
            out[i] = "cha" if (p == "查" and syl[i] in ("cha", "zha")) else "chá"
        elif c == "谁":
            out[i] = "shéi"
        elif c == "还" and ((nx in ("给", "钱", "书") if nx else False)
                           or seg[i + 1:i + 3] in ("回去", "回来")):
            out[i] = "huán"                                     # 还书
        elif c == "只":
            out[i] = "zhī" if after(i, _NUMERALS) or after(i, "这那哪每") else "zhǐ"
        elif c == "了" and i >= 2 and two_r != "了解" and (
                (p == "不" and seg[i - 2] not in _NOT_VERB)
                or (p == "得" and seg[i - 2] in _VERBS and seg[i - 2:i] not in _DE_WORDS)):
            out[i] = "liǎo"                                     # 改变不了
        elif c == "着" and (after(i, "睡") or (after(i, "不") and seg[i - 2:i - 1] in _VERBS)):
            out[i] = "zháo"                                     # 睡不着
        elif c == "个" and p != "个" and (after(i, _NUMERALS) or after(i, "这那哪每")
                                          or two_r not in ("个子", "个人", "个别", "个性", "个个")):
            out[i] = "ge"                                       # 一个, 洗个澡
        elif c == "过" and syl[i] == "guò" and not (two_r in words or two_l in words) \
                and after(i, _VERBS) and not (nx and nx in "来去"):
            out[i] = "guo"                                      # 去过
        elif c == "将" and two_r not in ("将军",):
            out[i] = "jiāng"
        elif c == "喂" and i == 0:
            out[i] = "wéi"
        elif c == "场" and (after(i, _NUMERALS) or after(i, "这那哪每")):
            out[i] = "cháng" if nx and nx in "雨雪病梦" else "chǎng"
        elif c == "种" and (after(i, _NUMERALS) or after(i, "这那哪每各")):
            out[i] = "zhǒng"
        elif c == "种" and nx and nx in "着了过树花菜在":
            out[i] = "zhòng"
        elif c == "假" and (after(i, "放请暑寒休") or seg[i - 2:i] == "放了"):
            out[i] = "jià"
        elif c == "一":
            if p and p == nx and p not in _NUMERALS and seg[i - 2:i - 1] != "一":
                out[i] = "yi"                                   # 想一想, 擦一擦
            elif nx and nx not in "十零一二三四五六七八九号月日楼" and \
                    not after(i, "第十百千万零一二三四五六七八九期初统唯之") and \
                    seg[i:i + 3] != "一年级":
                out[i] = "yí" if set(syl[i + 1]) & _FOURTH else "yì"
        elif c == "不":
            if p and nx and (p == nx or seg[i - 2:i] == seg[i + 1:i + 3]):
                out[i] = "bu"                                   # 去不去, 喜不喜欢
            elif nx and ((after(i, _VERBS) and nx in "了起到完见懂动及住清开成上下着定")
                         or (nx == "了" and p not in _NOT_VERB)):
                out[i] = "bu"                                   # 打不开, 来不及
            elif nx and set(syl[i + 1]) & _FOURTH:
                out[i] = "bú"                                   # 不是
    # 儿 joins the syllable before it: 哪儿 nǎr
    merged = []
    for i, c in enumerate(seg):
        if c == "儿" and merged and _erhua(seg, i):
            merged[-1] += "r"
        else:
            merged.append(out[i])
    return merged


def _erhua(seg, i):
    return i > 0 and seg[i - 1:i + 1] not in _ERHUA_NOT and seg[i:i + 2] not in _ERHUA_NOT


def sentence_pinyin(text):
    """Pinyin for a whole sentence: syllables separated by spaces, no
    punctuation (see the module notes for what's put right)."""
    out = []
    for seg in _CJK.findall(_spell_digits(text or "")):
        out += _segment(seg)
    return " ".join(out)


def word_pinyin(words):
    """Pinyin for each word of a sentence already split into words, read in
    the sentence (so 地 in 高兴 地 说 is de): one string per word."""
    text = "".join(words)
    out, pos = [], 0
    # read run by run, so a reading sees its neighbours
    sylls = []
    for m in re.finditer(r"[一-鿿]+|[^一-鿿]+", _spell_digits(text)):
        part = m.group()
        if _CJK.fullmatch(part):
            for c, s in zip(part, _segment_aligned(part)):
                sylls.append(s)
        else:
            sylls += [""] * len(part)
    if len(sylls) != len(text):          # digits changed the length: word by word instead
        return [sentence_pinyin(w) for w in words]
    for w in words:
        out.append(" ".join(s for s in sylls[pos:pos + len(w)] if s))
        pos += len(w)
    return out


def _segment_aligned(seg):
    """Like _segment, one entry per character: a joined 儿 leaves ''."""
    merged = _segment(seg)
    out, k = [], 0
    for i, c in enumerate(seg):
        if c == "儿" and _erhua(seg, i):
            out.append("")
        else:
            out.append(merged[k])
            k += 1
    return out
