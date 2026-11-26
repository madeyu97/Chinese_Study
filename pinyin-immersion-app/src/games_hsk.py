# src/games_hsk.py
"""
Play on the HSK track: quick games over the HSK 1-4 syllabus, each aimed at
something Anki and the study pages don't cover.

  listen     hear a word, tap its characters - the other options sound
             close (shì / shí / sì), so the ear has to separate them
  meaning    see a word in characters, tap its meaning
  lookalike  ＿天 jīn tiān 'today': 今 or 令 or 会? characters that look
             nearly the same
  measure    一＿书 'a book': 本, not 张 or 条
  scramble   an official HSK example sentence, its words shuffled
  memory     turn over cards, match characters to meanings

Picture games (PICTURE_GAMES) link HSK words to pictures without English:
picture -> word, word -> picture, hear it -> picture, and memory. About a
quarter of HSK 1-4 has a picture (data/hsk/pictures.csv, each one checked
by eye); they draw on every level, not just the one tested, so they also
bring in new words - a few a game, next in syllabus order.

Words come from the syllabus up to the level the level test set: listening
games by the listening level, the rest by reading, the scramble by grammar.

Every answer is kept per word (db game_seen), and each game is filled in
this order (prioritise): words missed last time, words due again (a
Leitner box: 1, 3, 7, 21, 60 days), words not yet met - ones learnt in Anki
first - then whatever was played longest ago.

The herb game is separate (HERB_GAMES): name the herb from its characters,
find its characters from the name, or write herb names on the Write page.

Pure: the page (games_hsk_page.py) keeps the state and draws the cards.
Every round is {"prompt": card | None, "audio": text | None, "options":
[cards], "answer": index, "reveal": {zh, py, en}, "notes": [(zh, py, en)]}
where a card is {"kind": "word"|"text", "zh", "py", "en"} or, in the
picture games, {"kind": "image", "image": key} (the page turns the key into
the picture). Each round also names its "item": what game_seen records.
"""

import csv
import datetime
import functools
import random
import re
from pathlib import Path

from pypinyin import Style, lazy_pinyin, pinyin as _pinyin

import hsk
import placement

GAMES = {
    "listen": ("🎧", "Hear it, find it", "Hear a word, tap its characters. The others sound close."),
    "meaning": ("🔤", "Read it", "See a word in characters, tap what it means."),
    "lookalike": ("👀", "Look-alikes", "Tap the right character from ones that look nearly the same."),
    "measure": ("📏", "Measure words", "一＿书 'a book': which measure word fits?"),
    "scramble": ("🧩", "Sentence scramble", "Put an HSK example sentence back in order."),
    "memory": ("🃏", "Memory match", "Turn over two cards at a time; match characters to meanings."),
}
PICTURE_GAMES = {
    "pic_word": ("🖼️", "Picture → word", "See the picture, tap its word."),
    "word_pic": ("🔤", "Word → picture", "Read the word, tap its picture."),
    "listen_pic": ("🎧", "Hear it → picture", "Hear a word, tap its picture."),
    "pic_memory": ("🃏", "Picture memory", "Turn over two cards at a time; match each picture to its word."),
}
HERB_GAMES = {
    "herb_name": ("🌿", "Name the herb", "See the herb's characters, tap its name."),
    "herb_find": ("🔍", "Find the herb", "See the name, tap its characters — the others share a character or a category."),
    "herb_write": ("✍️", "Write herb names", "Herb names on the Write page, tier-1 herbs first."),
}
SKILL = {"listen": "listen", "meaning": "read", "lookalike": "read", "measure": "read",
         "memory": "read", "scramble": "grammar", "pic_word": "read", "word_pic": "read",
         "pic_memory": "read", "listen_pic": "listen"}
# what game_seen keeps results under: games testing the same link share one
FAMILY = {"listen": "listen", "meaning": "meaning", "memory": "meaning",
          "lookalike": "lookalike", "measure": "measure", "scramble": "scramble",
          "pic_word": "pic", "word_pic": "pic", "pic_memory": "pic", "listen_pic": "pic_listen",
          "herb_name": "herb", "herb_find": "herb"}
INTERVALS = (0, 1, 3, 7, 21, 60)       # days before a word comes back, by box
NEW_PER_GAME = 3                       # picture games: new words (past Anki / the level) a game
ROUNDS = 10
SCRAMBLE_ROUNDS = 6
MEMORY_PAIRS = 6
OPTIONS = 4

# what each common measure word counts - shown after the answer
MEASURES = {
    "个": "general", "本": "books, bound volumes", "条": "long thin things; rivers, roads, fish",
    "张": "flat things: tables, paper, tickets", "只": "animals; one of a pair",
    "位": "people (polite)", "家": "businesses: shops, firms", "件": "clothes on top; matters",
    "辆": "vehicles", "台": "machines", "座": "mountains, buildings, bridges", "双": "pairs",
    "杯": "a cup / glass of", "块": "lumps, pieces; money", "把": "things with a handle",
    "片": "slices, flat pieces; stretches", "种": "kinds", "次": "times, occurrences",
    "顿": "meals; a bout of", "场": "events: games, films, rain", "部": "films, phones, works",
    "间": "rooms", "门": "school subjects, courses", "套": "sets; flats", "份": "portions, copies, jobs",
    "项": "items, tasks", "道": "dishes; questions; lines", "名": "people (formal)",
    "所": "schools, hospitals", "棵": "trees", "封": "letters", "支": "pens; songs; teams",
    "头": "cattle, pigs", "颗": "small round things", "篇": "essays, articles", "首": "songs, poems",
    "架": "planes, pianos", "节": "class periods; sections", "层": "floors, layers",
    "朵": "flowers, clouds", "盘": "a plate of", "碗": "a bowl of", "瓶": "a bottle of",
    "盒": "a box of", "包": "a packet of", "段": "sections, periods", "幅": "pictures, paintings",
    "根": "long thin things: bananas, hairs", "列": "trains",
    "盏": "lamps", "匹": "horses", "扇": "doors, windows", "顶": "hats", "副": "pairs: glasses",
    "面": "flat things: mirrors, flags", "管": "tubes", "笔": "sums of money, deals",
    "条儿": "long thin things", "辈子": "a lifetime", "口": "family members; mouthfuls",
}
MEASURES.pop("条儿")
MEASURES.pop("辈子")

_CJK_ONLY = re.compile(r"[一-鿿]+")


def _plain(rows):
    return [w for w in rows if _CJK_ONLY.fullmatch(w["word"])]


def _word_card(zh, py="", en=""):
    return {"kind": "word", "zh": zh, "py": py, "en": en}


def _text_card(en):
    return {"kind": "text", "zh": "", "py": "", "en": en}


def _round(prompt, options, answer_n, reveal, audio=None, notes=None, item=None):
    return {"prompt": prompt, "audio": audio, "options": options, "answer": answer_n,
            "reveal": reveal, "notes": notes or [], "item": item or reveal["zh"]}


def _place(target, others, rng):
    """target among others, shuffled: (options, index of target)."""
    opts = others + [target]
    rng.shuffle(opts)
    return opts, opts.index(target)


def prioritise(keys, seen=None, today=None, n=ROUNDS, known=None, new_max=None, rng=None):
    """keys (syllabus order) in the order a game should take them.

    seen: {key: {"box", "last"}} from game_seen. First up to half the game
    from words missed last time (box 0), then words due again, then words
    not met yet - known ones (learnt in Anki, or up to the level) at random,
    then up to new_max new ones in syllabus order - then the rest of the
    missed, then whatever was played longest ago, then the other new ones.
    Every key comes back once: a game takes the first n it can use."""
    rng = rng or random.Random()
    seen = seen or {}
    today = today or datetime.date.today()
    known = None if known is None else set(known)

    def age(k):
        try:
            return (today - datetime.date.fromisoformat(seen[k]["last"][:10])).days
        except (TypeError, ValueError, KeyError):
            return 999

    missed, due, rest, fresh, new = [], [], [], [], []
    for k in keys:
        if k in seen:
            box = max(0, min(int(seen[k].get("box") or 0), len(INTERVALS) - 1))
            if box == 0:
                missed.append(k)
            elif age(k) >= INTERVALS[box]:
                due.append(k)
            else:
                rest.append(k)
        elif known is None or k in known:
            fresh.append(k)
        else:
            new.append(k)
    jitter = {k: rng.random() for k in keys}
    missed.sort(key=lambda k: (-age(k), jitter[k]))
    due.sort(key=lambda k: (-age(k), jitter[k]))
    rest.sort(key=lambda k: (-age(k), jitter[k]))
    rng.shuffle(fresh)
    cap = len(new) if new_max is None else new_max
    half = max(1, n // 2)
    return missed[:half] + due + fresh + new[:cap] + missed[half:] + rest + new[cap:]


def _take(order, make, n, rng):
    """The first n rounds make() can build from order, shuffled (missed
    words shouldn't all come first)."""
    rounds = []
    for k in order:
        if len(rounds) == n:
            break
        r = make(k)
        if r:
            rounds.append(r)
    rng.shuffle(rounds)
    return rounds


def level_for(game, levels):
    """The HSK level a game draws from (1 until the level test sets one)."""
    levels = levels or {}
    if game == "scramble":
        return hsk.grammar_upto(levels)
    return levels.get(SKILL.get(game, "read")) or 1


# ----------------------------------------------------------------------
# listen: similar-sounding words
# ----------------------------------------------------------------------
def _sound(word):
    return {"bare": lazy_pinyin(word),
            "tone": lazy_pinyin(word, style=Style.TONE3, neutral_tone_with_five=True),
            "init": lazy_pinyin(word, style=Style.INITIALS, strict=False)}


def sound_distance(a, b):
    """How alike two words sound (higher = closer), same length only."""
    if len(a) != len(b):
        return -1
    sa, sb = _sound(a), _sound(b)
    if sa["tone"] == sb["tone"]:
        return -1                                  # a homophone: can't be told apart by ear
    score = 0
    for i in range(len(a)):
        if sa["bare"][i] == sb["bare"][i]:
            score += 3                             # same syllable, maybe another tone
        elif sa["init"][i] and sa["init"][i] == sb["init"][i]:
            score += 1
        if sa["bare"][i][len(sa["init"][i]):] == sb["bare"][i][len(sb["init"][i]):]:
            score += 1                             # same final (shì / zhì)
    return score


def listen_rounds(level, n=ROUNDS, rng=None, seen=None, today=None):
    rng = rng or random.Random()
    pool = {w["word"]: w for w in _plain(hsk.words_upto(level))}
    near = _plain(hsk.words_upto(min(4, level + 1)))

    def make(key):
        t = pool[key]
        cands = [(sound_distance(t["word"], w["word"]), rng.random(), w) for w in near
                 if w["word"] != t["word"]]
        cands = sorted((c for c in cands if c[0] > 0), key=lambda c: (-c[0], c[1]))
        picked = []
        for _, _, w in cands:
            if len(picked) == OPTIONS - 1:
                break
            if all(w["word"] != p["word"] for p in picked):
                picked.append(w)
        if len(picked) < OPTIONS - 1:
            return None
        opts, ans = _place(t, picked, rng)
        return _round(
            None, [_word_card(o["word"]) for o in opts], ans,
            {"zh": t["word"], "py": t["pinyin"], "en": placement.show(t["english"])},
            audio=t["word"],
            notes=[(o["word"], o["pinyin"], placement.show(o["english"])) for o in opts
                   if o is not t])
    return _take(prioritise(list(pool), seen, today, n, rng=rng), make, n, rng)


# ----------------------------------------------------------------------
# meaning: characters -> English
# ----------------------------------------------------------------------
def _meaning_pool(level):
    return [w for w in _plain(hsk.words_upto(level)) if placement._tokens(w)
            and placement.show(w["english"])]


def meaning_rounds(level, n=ROUNDS, rng=None, seen=None, today=None):
    rng = rng or random.Random()
    pool = _meaning_pool(level)
    by = {w["word"]: w for w in pool}

    def make(key):
        t = by[key]
        item = placement.make_item(t, pool, rng)
        return _round(
            _word_card(t["word"]), [_text_card(o) for o in item["options"]],
            item["options"].index(item["answer"]),
            {"zh": t["word"], "py": t["pinyin"], "en": item["answer"]})
    return _take(prioritise(list(by), seen, today, n, rng=rng), make, n, rng)


# ----------------------------------------------------------------------
# look-alike characters
# ----------------------------------------------------------------------
def _char_py(ch):
    return _pinyin(ch)[0][0]


def cue_word(ch, level):
    """The HSK word (up to level) that best shows ch: two or three
    characters, lowest level first, the character itself if nothing else."""
    words = [w for w in _plain(hsk.words_upto(level)) if ch in w["word"]]
    if not words:
        words = [w for w in _plain(hsk.words_upto(4)) if ch in w["word"]]
    multi = [w for w in words if 2 <= len(w["word"]) <= 3]
    pick = sorted(multi or words, key=lambda w: (w["level"], len(w["word"])))
    return pick[0] if pick else None


def _char_note(ch):
    """(character, pinyin, meaning or a word it's in) for after the answer."""
    w = cue_word(ch, 4)
    if not w:
        return ch, _char_py(ch), ""
    if w["word"] == ch:
        return ch, w["pinyin"], placement.show(w["english"])
    return ch, _char_py(ch), f"as in {w['word']} {w['pinyin']} '{placement.show(w['english'])}'"


def lookalike_rounds(level, n=ROUNDS, rng=None, seen=None, today=None):
    rng = rng or random.Random()
    words = {w["word"] for w in hsk.words_upto(4)}
    chars = hsk.lookalike_chars(level)

    def make(ch):
        w = cue_word(ch, level)
        if not w:
            return None
        # no option that would make another real word in the blank (今天 / 明天)
        others = [d for d in hsk.lookalikes(ch) if w["word"].replace(ch, d) not in words]
        if len(others) < OPTIONS - 1:
            return None
        others = others[:5]
        rng.shuffle(others)
        opts, ans = _place(ch, others[:OPTIONS - 1], rng)
        blank = w["word"].replace(ch, "＿")
        return _round(
            _word_card(blank, w["pinyin"], placement.show(w["english"])),
            [_word_card(o) for o in opts], ans,
            {"zh": w["word"], "py": w["pinyin"], "en": placement.show(w["english"])},
            notes=[_char_note(o) for o in opts if o != ch], item=ch)
    return _take(prioritise(list(chars), seen, today, n, rng=rng), make, n, rng)


# ----------------------------------------------------------------------
# measure words
# ----------------------------------------------------------------------
# The measure word each noun takes in everyday speech, and the others that are
# also right. CC-CEDICT lists measure words in no useful order (菜: 棵 before
# 道, 音乐: 张), so only these hand-checked nouns are asked.
_M = {
    "个": "人 孩子 学生 小学生 问题 办法 东西 地方 机场 词 球 篮球 书包 杯子 饺子 面包 苹果 西瓜 碗 "
          "箱子 节目 公园 图书馆 游戏 决定 成绩 会议 爸爸 妈妈 哥哥 弟弟 姐姐 妹妹 奶奶 朋友 同学 "
          "鸡蛋 字 名字 星期 月 国家 城市 门 手机 故事 习惯 机会 计划 意见 世界",
    "位": "老师 医生 经理 校长 客人 先生 女士 教授 律师 司机 警察 顾客 教练 作家 师傅 父亲",
    "名": "运动员 记者 护士",
    "本": "书 本子 笔记本 词典 字典 护照 课本 杂志 小说 笔记 说明书",
    "张": "照片 票 机票 地图 卡 纸 床 桌子 脸 嘴 沙发 报纸 菜单 表格 图 图片 纸巾",
    "把": "椅子 伞 勺子 牙刷 刀 钥匙",
    "条": "裤子 裙子 路 马路 街 河 船 鱼 新闻 腿 狗 毛巾 短信 消息 道路 街道 公路 江 胳膊 生命 法律",
    "件": "衣服 事 事情 礼物 行李 大衣 衬衫 上衣 雨衣 毛衣 家具 商品 外套",
    "辆": "汽车 车 自行车 公交车 出租车",
    "台": "电脑 电视 空调 洗衣机 电梯 冰箱",
    "部": "电影 电话 电视剧 作品 话剧",
    "首": "歌 音乐",
    "家": "宾馆 饭店 饭馆 商店 书店 超市 公司 银行 商场 店 医院 电影院 酒店 工厂 剧院 旅馆",
    "所": "大学 学校 学院",
    "间": "教室 房间 屋子 卫生间 办公室 厨房 客厅 餐厅 厕所",
    "座": "山 房子 楼 桥 城 花园",
    "只": "猫 鸟 鸡 羊 动物 耳朵 老虎",
    "头": "牛",
    "双": "鞋 手 脚 筷子 眼睛 袜子",
    "杯": "茶 咖啡 红茶 酒 啤酒 果汁",
    "瓶": "牛奶 矿泉水 水",
    "碗": "饭 米饭",
    "道": "菜 题",
    "节": "课",
    "门": "历史 外语 语言 课程 功课 口语 技术 科学 知识 专业",
    "颗": "糖 牙 星星 心",
    "块": "蛋糕 冰 黑板 手表 肉 巧克力 饼干 牌子",
    "片": "海 草地 叶子 森林",
    "篇": "课文 文章 日记",
    "份": "工作 工资 文件 资料",
    "封": "信 邮件",
    "支": "笔 铅笔 队",
    "棵": "树 草",
    "朵": "花 云 鲜花",
    "幅": "画",
    "场": "比赛 雨 雪 表演 考试 病 京剧 梦 感冒",
    "架": "飞机 钢琴",
    "顿": "早饭 午饭 晚饭 早餐 午餐 晚餐",
    "根": "香蕉 头发 烟",
    "列": "火车",
    "种": "药 颜色 水果 运动",
    "盏": "灯",
    "匹": "马",
    "扇": "窗 窗户",
    "顶": "帽子",
    "副": "眼镜",
    "面": "镜子",
    "管": "牙膏",
    "笔": "钱 奖学金 生意",
    "项": "任务",
}
# other measure words that are right too, so they're never wrong options
_ALSO = {"人": "位口", "老师": "个", "医生": "个", "经理": "个", "客人": "个", "爸爸": "位",
         "妈妈": "位", "朋友": "位", "同学": "位", "奶奶": "位", "运动员": "个位", "护士": "个位",
         "记者": "个位", "医院": "所个", "电影院": "个", "大学": "个", "学校": "个", "饭店": "个",
         "公司": "个", "商店": "个", "银行": "个", "超市": "个", "店": "个", "教室": "个",
         "房间": "个", "屋子": "个", "办公室": "个", "厨房": "个", "卫生间": "个", "山": "个",
         "房子": "个栋套", "楼": "个栋层", "桥": "个", "城市": "座", "图书馆": "座家", "公园": "座",
         "猫": "个", "鸟": "个", "鸡": "个", "羊": "头个", "狗": "只个", "动物": "种个",
         "牛": "条个", "耳朵": "个双", "眼睛": "只个", "手": "只", "脚": "只", "筷子": "把",
         "鞋": "只", "袜子": "只", "茶": "壶瓶", "咖啡": "瓶", "酒": "瓶", "啤酒": "瓶罐",
         "果汁": "瓶", "牛奶": "杯盒", "矿泉水": "杯", "水": "杯", "饭": "顿", "面条": "根",
         "课": "门", "历史": "种", "外语": "种", "语言": "种", "糖": "块", "蛋糕": "个",
         "手表": "个", "花": "枝", "画": "张", "病": "种", "考试": "次", "表演": "个",
         "苹果": "颗", "西瓜": "颗", "面包": "片块", "饺子": "只", "球": "只", "篮球": "只",
         "书包": "只", "杯子": "只", "碗": "只", "箱子": "只", "节目": "场", "游戏": "场",
         "决定": "项", "成绩": "项", "会议": "场次", "问题": "道", "办法": "种条",
         "沙发": "条套", "报纸": "份", "菜单": "份", "礼物": "份", "工作": "个", "菜": "盘个",
         "题": "个", "信": "个", "邮件": "个", "药": "片盒", "水果": "个", "颜色": "个",
         "运动": "项个", "头发": "", "香蕉": "把个", "早饭": "份", "午饭": "份", "晚饭": "份",
         "车": "部", "汽车": "部", "电话": "个", "手机": "部台", "门": "扇道", "窗户": "扇",
         "电影": "个", "歌": "个", "床": "个", "桌子": "个", "照片": "个", "地图": "个",
         "纸": "", "钥匙": "个", "刀": "个", "椅子": "个", "伞": "个", "故事": "段", "习惯": "种",
         "机会": "次", "计划": "项", "意见": "条", "世界": "", "事": "个", "事情": "个",
         "衣服": "套", "鱼": "个", "新闻": "个", "短信": "个", "消息": "个", "队": "个",
         "云": "片", "海": "", "草地": "块", "树叶": "", "课文": "", "文章": "", "日记": "",
         "笔": "个", "铅笔": "个", "冰箱": "个", "电脑": "个", "电视": "个", "空调": "个",
         "笔记": "个", "表格": "份", "图": "幅", "图片": "幅", "纸巾": "包", "窗": "个",
         "窗户": "个", "帽子": "个", "镜子": "个", "牙膏": "支", "钱": "", "奖学金": "份",
         "生意": "单", "胳膊": "只", "法律": "部项", "功课": "", "口语": "", "技术": "项种",
         "科学": "种", "知识": "种", "专业": "个", "电视剧": "", "作品": "篇件个", "话剧": "台场",
         "钢琴": "台", "家具": "套", "商品": "种个", "外套": "", "鲜花": "束枝", "叶子": "",
         "森林": "", "工资": "", "文件": "个", "资料": "", "早餐": "份", "午餐": "份",
         "晚餐": "份", "京剧": "出", "梦": "个", "感冒": "次", "心": "个", "烟": "支", "学院": "个",
         "客厅": "个", "餐厅": "家个", "厕所": "个", "顾客": "个名", "教练": "个名", "作家": "个名",
         "师傅": "个", "父亲": "个", "巧克力": "颗", "饼干": "片", "牌子": "个", "工厂": "座个",
         "剧院": "座个", "旅馆": "个", "城": "个", "花园": "个", "任务": "个", "道路": "",
         "街道": "", "公路": "", "江": "", "生命": "个", "说明书": "份"}
MEASURE_OF = {noun: m for m, nouns in _M.items() for noun in nouns.split()}


def measure_answer(word):
    """The measure word to ask for with a noun, from the hand-checked list
    (None for nouns not on it)."""
    return MEASURE_OF.get(word["word"])


def measure_ok(word):
    """Every measure word that's right with the noun."""
    w = word["word"]
    return {MEASURE_OF.get(w, "")} | set(_ALSO.get(w, "")) | set(word.get("measure") or ()) - {""}


def measure_rounds(level, n=ROUNDS, rng=None, seen=None, today=None):
    rng = rng or random.Random()
    import hsk_grammar as hg
    nouns = {w["word"]: w for w in _plain(hsk.words_upto(level)) if measure_answer(w)}
    special = [k for k, w in nouns.items() if measure_answer(w) != "个"]
    general = [k for k, w in nouns.items() if measure_answer(w) == "个"]
    # mostly nouns with a measure word of their own; 个 now and then
    k = min(len(general), max(1, n // 5))
    targets = [nouns[x] for x in prioritise(special, seen, today, n - k, rng=rng)[:n - k]
               + prioritise(general, seen, today, k, rng=rng)[:k]]
    rng.shuffle(targets)
    common = [m for m in MEASURES]
    rounds = []
    for t in targets:
        m = measure_answer(t)
        others = [x for x in common if x not in measure_ok(t)]
        rng.shuffle(others)
        opts, ans = _place(m, others[:OPTIONS - 1], rng)
        phrase = f"一{m}{t['word']}"
        rounds.append(_round(
            _word_card(f"一＿{t['word']}", t["pinyin"], placement.show(t["english"])),
            [_word_card(o) for o in opts], ans,
            {"zh": phrase, "py": hg.sentence_pinyin(phrase),
             "en": f"{placement.show(t['english'])} · {m}: {MEASURES[m]}" + (
                 f" · also {'、'.join(sorted(also))}" if (also := set(_ALSO.get(t["word"], ""))
                                                         - {m}) else "")},
            notes=[(o, _char_py(o), MEASURES[o]) for o in opts if o != m], item=t["word"]))
    return rounds


# ----------------------------------------------------------------------
# sentence scramble
# ----------------------------------------------------------------------
@functools.lru_cache(maxsize=4)
def _scramble_pool(level):
    return tuple(placement.grammar_pool(level, game=True))


def scramble_items(level, n=SCRAMBLE_ROUNDS, rng=None, seen=None, today=None):
    """Official example sentences up to the grammar level, half of them from
    the level itself."""
    rng = rng or random.Random()
    now = {ex["hanzi"]: ex for ex in _scramble_pool(level)}
    before = {ex["hanzi"]: ex for lv in range(1, level) for ex in _scramble_pool(lv)
              if ex["hanzi"] not in now}
    k = n if not before else max(n // 2, n - len(before))
    picked = [now[x] for x in prioritise(list(now), seen, today, k, rng=rng)[:k]]
    picked += [before[x] for x in prioritise(list(before), seen, today, n - len(picked),
                                             rng=rng)[:n - len(picked)]]
    rng.shuffle(picked)
    return [placement.make_grammar_item(ex, rng) for ex in picked]


# ----------------------------------------------------------------------
# memory: characters <-> meanings
# ----------------------------------------------------------------------
def memory_cards(level, pairs=MEMORY_PAIRS, rng=None, seen=None, today=None):
    rng = rng or random.Random()
    by = {w["word"]: w for w in _meaning_pool(level)}
    chosen = []
    for w in (by[k] for k in prioritise(list(by), seen, today, pairs, rng=rng)):
        if all(not placement._clash(w, c) for c in chosen):
            chosen.append(w)
        if len(chosen) == pairs:
            break
    cards = [{"pair": w["word"], "face": f, "img": "", "zh": w["word"], "py": w["pinyin"],
              "en": placement.show(w["english"])} for w in chosen for f in ("word", "text")]
    rng.shuffle(cards)
    return cards


def memory_matches(cards, reported, already=()):
    """Keep only real pairs (a word and its meaning) from what the board reports."""
    ok = set(already)
    by_pair = {}
    for n in set(reported or []):
        if isinstance(n, int) and 0 <= n < len(cards):
            by_pair.setdefault(cards[n]["pair"], []).append(n)
    for ns in by_pair.values():
        if len(ns) == 2 and cards[ns[0]]["face"] != cards[ns[1]]["face"]:
            ok.update(ns)
    return ok


# ----------------------------------------------------------------------
# herbs
# ----------------------------------------------------------------------
HERB_CSV = Path(__file__).resolve().parent.parent / "data" / "herbs.csv"


@functools.lru_cache(maxsize=1)
def herbs():
    """data/herbs.csv as {zh (simplified), trad, py, name, action, category,
    tier, latin}."""
    out = []
    if not HERB_CSV.exists():
        return out
    with open(HERB_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            trad = (r.get("Chinese") or "").strip()
            if not trad:
                continue
            name, _, action = (r.get("English") or "").partition(" - ")
            try:
                tier = int(float(r.get("Tier") or 9))
            except ValueError:
                tier = 9
            out.append({"zh": (r.get("Alt_script") or "").strip() or trad, "trad": trad,
                        "py": (r.get("Pinyin") or "").strip().lower(), "name": name.strip(),
                        "action": action.strip(), "category": (r.get("Category") or "").strip(),
                        "tier": tier, "latin": (r.get("Latin") or "").strip()})
    return out


def _herb_targets(pool, n, rng):
    """Tier-1 herbs first: most rounds from the lowest tiers there are."""
    weights = [1 / h["tier"] ** 2 for h in pool]
    picked = []
    while len(picked) < min(n, len(pool)):
        h = rng.choices(pool, weights)[0]
        if h not in picked:
            picked.append(h)
    return picked


def _herb_reveal(h):
    trad = f" ({h['trad']})" if h["trad"] != h["zh"] else ""
    return {"zh": h["zh"] + trad, "py": h["py"],
            "en": h["name"] + (f" — {h['action']}" if h["action"] else "")
                  + (f" · {h['latin']}" if h["latin"] else "")}


def herb_rounds(game, n=ROUNDS, rng=None, pool=None):
    """herb_name: characters -> name; herb_find: name -> characters, the
    wrong ones sharing a character with it where possible (白芍 / 赤芍)."""
    rng = rng or random.Random()
    pool = list(pool or herbs())
    rounds = []
    for t in _herb_targets(pool, n, rng):
        same_cat = [h for h in pool if h is not t and h["category"] == t["category"]]
        rest = [h for h in pool if h is not t and h["category"] != t["category"]]
        rng.shuffle(same_cat)
        rng.shuffle(rest)
        if game == "herb_find":
            shares = [h for h in pool if h is not t and set(h["zh"]) & set(t["zh"])]
            rng.shuffle(shares)
            order = shares[:2] + same_cat + rest
        else:
            order = same_cat + rest
        picked = []
        for h in order:
            if len(picked) == OPTIONS - 1:
                break
            if (h["name"].lower() != t["name"].lower() and h["zh"] != t["zh"]
                    and all(h["name"] != p["name"] and h["zh"] != p["zh"] for p in picked)):
                picked.append(h)
        opts, ans = _place(t, picked, rng)
        if game == "herb_find":
            prompt = _word_card("", t["py"], t["name"])
            cards = [_word_card(o["zh"]) for o in opts]
        else:
            prompt = _word_card(t["zh"])
            cards = [_text_card(o["name"]) for o in opts]
        rounds.append(_round(prompt, cards, ans, _herb_reveal(t), item=t["zh"],
                             notes=[(o["zh"], o["py"], o["name"]) for o in opts if o is not t]))
    return rounds


def rounds_for(game, levels, rng=None, seen=None, today=None, known=None):
    if game in PICTURE_GAMES:
        return picture_rounds(game, rng=rng, seen=seen, today=today, known=known)
    level = level_for(game, levels)
    return {"listen": listen_rounds, "meaning": meaning_rounds, "lookalike": lookalike_rounds,
            "measure": measure_rounds}[game](level, rng=rng, seen=seen, today=today)


# ----------------------------------------------------------------------
# picture games
# ----------------------------------------------------------------------
PICTURES_CSV = Path(__file__).resolve().parent.parent / "data" / "hsk" / "pictures.csv"


@functools.lru_cache(maxsize=1)
def pictures():
    """HSK words with a picture, syllabus order: the word's row plus
    "image" (a game_images key)."""
    if not PICTURES_CSV.exists():
        return []
    with open(PICTURES_CSV, encoding="utf-8") as f:
        img = {r["word"]: r["image"] for r in csv.DictReader(f)}
    return [{**w, "image": img[w["word"]]} for w in hsk.words_upto(4, include_erhua=True)
            if w["word"] in img]


def picture_words(level):
    """HSK words (up to level) that have a picture."""
    return {p["word"] for p in pictures() if p["level"] <= level}


def known_for_pictures(levels, anki_words=None):
    """Words the picture games treat as learnt: what Anki covers, if you've
    said, and every word up to the reading level. The rest are new."""
    lv = (levels or {}).get("read") or 1
    return set(hsk.anki_known(anki_words or 0)) | {w["word"] for w in hsk.words_upto(lv)}


def _same_meaning(a, b):
    """Two picture words one picture could stand for: the same picture,
    meanings that share a word (饭店 / 饭馆), or one inside the other
    (饭 / 米饭)."""
    return (a["image"] == b["image"] or placement._clash(a, b)
            or a["word"] in b["word"] or b["word"] in a["word"])


def picture_options(t, pool, familiar, rng, n=OPTIONS - 1):
    """n other picture words for t: none that could also be right, words
    already met first, the same part of speech first (a picture of a verb
    among nouns gives itself away)."""
    others = [p for p in pool if p["word"] != t["word"] and not _same_meaning(t, p)]
    rng.shuffle(others)
    others.sort(key=lambda p: (p["word"] not in familiar, p["pos"][:1] != t["pos"][:1]))
    picked = []
    for p in others:
        if len(picked) == n:
            break
        if all(not _same_meaning(p, q) for q in picked):
            picked.append(p)
    return picked


def _pic_card(p):
    return {"kind": "image", "image": p["image"]}


def picture_rounds(game, n=ROUNDS, rng=None, seen=None, today=None, known=None):
    """pic_word: picture -> word; word_pic: word -> picture; listen_pic:
    hear the word -> picture."""
    rng = rng or random.Random()
    pool = pictures()
    by = {p["word"]: p for p in pool}
    known = set(known or ())
    familiar = known | set(seen or ())

    def make(key):
        t = by[key]
        others = picture_options(t, pool, familiar, rng)
        if len(others) < OPTIONS - 1:
            return None
        opts, ans = _place(t, others, rng)
        reveal = {"zh": t["word"], "py": t["pinyin"], "en": placement.show(t["english"]),
                  "image": t["image"]}
        notes = [(o["word"], o["pinyin"], placement.show(o["english"])) for o in opts if o is not t]
        if game == "pic_word":
            return _round(_pic_card(t), [_word_card(o["word"], o["pinyin"]) for o in opts], ans,
                          reveal, notes=notes)
        prompt = _word_card(t["word"], t["pinyin"]) if game == "word_pic" else None
        return _round(prompt, [_pic_card(o) for o in opts], ans, reveal, notes=notes,
                      audio=t["word"] if game == "listen_pic" else None)
    order = prioritise(list(by), seen, today, n, known=known or None, new_max=NEW_PER_GAME, rng=rng)
    return _take(order, make, n, rng)


def picture_memory(pairs=MEMORY_PAIRS, rng=None, seen=None, today=None, known=None):
    """Memory cards: each picture word as a picture and as characters, no two
    that one picture could stand for."""
    rng = rng or random.Random()
    by = {p["word"]: p for p in pictures()}
    chosen = []
    for k in prioritise(list(by), seen, today, pairs, known=set(known or ()) or None,
                        new_max=1, rng=rng):
        if all(not _same_meaning(by[k], c) for c in chosen):
            chosen.append(by[k])
        if len(chosen) == pairs:
            break
    cards = [{"pair": p["word"], "face": f, "image": p["image"] if f == "image" else "",
              "zh": p["word"], "py": p["pinyin"], "en": placement.show(p["english"])}
             for p in chosen for f in ("image", "word")]
    rng.shuffle(cards)
    return cards
