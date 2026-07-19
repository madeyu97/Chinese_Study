# src/handwriting_engine.py
"""
Scoring and SRS logic for character-level handwriting drills.
Kept separate from db_manager to avoid circular imports.
"""

from datetime import date, timedelta

# ----------------------------------------------------------------------
# Stroke counts for common simplified Chinese characters.
# This is a curated subset — extend as needed. Unknown chars default to 8.
# ----------------------------------------------------------------------
STROKE_COUNTS = {
    "一": 1, "乙": 1, "二": 2, "十": 2, "七": 2, "八": 2, "九": 2, "人": 2,
    "入": 2, "几": 2, "了": 2, "刀": 2, "力": 2, "又": 2, "丁": 2, "儿": 2,
    "三": 3, "上": 3, "下": 3, "万": 3, "口": 3, "土": 3, "士": 3, "大": 3,
    "女": 3, "子": 3, "小": 3, "山": 3, "工": 3, "己": 3, "干": 3, "广": 3,
    "门": 3, "也": 3, "习": 3, "于": 3, "之": 3, "已": 3, "马": 3, "飞": 3,
    "个": 3, "么": 3, "义": 3, "亿": 3, "千": 3, "及": 3, "丸": 3, "夕": 3,
    "弓": 3, "才": 3, "寸": 3, "不": 4, "中": 4, "为": 4, "五": 4, "六": 4,
    "今": 4, "从": 4, "化": 4, "比": 4, "反": 4, "友": 4, "升": 4, "午": 4,
    "厅": 4, "历": 4, "区": 4, "卡": 5, "支": 4, "文": 4, "斗": 4, "斤": 4,
    "方": 4, "无": 4, "日": 4, "月": 4, "木": 4, "欠": 4, "止": 4, "毛": 4,
    "水": 4, "火": 4, "父": 4, "片": 4, "牙": 4, "牛": 4, "王": 4, "元": 4,
    "云": 4, "互": 4, "井": 4, "什": 4, "仁": 4, "介": 4, "公": 4, "兮": 4,
    "内": 4, "册": 5, "冗": 4, "凡": 3, "分": 4, "切": 4, "勿": 4, "匹": 4,
    "巨": 4, "币": 4, "心": 4, "戈": 4, "户": 4, "手": 4, "车": 4, "长": 4,
    "队": 4, "双": 4, "少": 4, "丑": 4, "巴": 4, "可": 5, "古": 5, "右": 5,
    "号": 5, "司": 5, "叶": 5, "只": 5, "史": 5, "台": 5, "外": 5, "央": 5,
    "失": 5, "头": 5, "奴": 5, "写": 5, "字": 6, "宁": 5, "它": 5, "对": 5,
    "尔": 5, "市": 5, "布": 5, "平": 5, "幼": 5, "弗": 5, "必": 5, "戊": 5,
    "打": 5, "扑": 5, "本": 5, "末": 5, "未": 5, "正": 5, "民": 5, "永": 5,
    "汁": 5, "犯": 5, "玄": 5, "玉": 5, "瓜": 5, "甘": 5, "生": 5, "用": 5,
    "甩": 5, "田": 5, "由": 5, "甲": 5, "申": 5, "白": 5, "皮": 5, "目": 5,
    "矛": 5, "石": 5, "示": 5, "立": 5, "去": 5, "出": 5, "刊": 5, "加": 5,
    "包": 5, "北": 5, "汉": 5, "发": 5, "记": 5, "讨": 5, "让": 5, "训": 5,
    "议": 5, "印": 5, "他": 5, "们": 5, "旧": 5, "件": 6, "任": 6, "份": 6,
    "仿": 6, "企": 6, "伏": 6, "伐": 6, "休": 6, "众": 6, "优": 6, "会": 6,
    "传": 6, "似": 6, "光": 6, "先": 6, "兆": 6, "全": 6, "再": 6, "决": 6,
    "划": 6, "刑": 6, "列": 6, "刚": 6, "创": 6, "动": 6, "匠": 6, "华": 6,
    "协": 6, "危": 6, "厌": 6, "压": 6, "县": 7, "参": 8, "吃": 6, "各": 6,
    "合": 6, "吉": 6, "同": 6, "名": 6, "后": 6, "向": 6, "吐": 6, "吓": 6,
    "吕": 6, "因": 6, "回": 6, "团": 6, "地": 6, "场": 6, "在": 6, "圭": 6,
    "圾": 6, "好": 6, "如": 6, "妃": 6, "妇": 6, "妈": 6, "她": 6, "存": 6,
    "孙": 6, "宅": 6, "守": 6, "安": 6, "寺": 6, "导": 6, "尘": 6, "尖": 6,
    "州": 6, "巡": 6, "巩": 6, "师": 6, "帆": 6, "年": 6, "并": 6, "庆": 6,
    "庄": 6, "异": 6, "弛": 6, "当": 6, "忌": 7, "忙": 6, "成": 6, "戎": 6,
    "扫": 6, "扣": 6, "扩": 6, "扪": 6, "扬": 6, "执": 6, "扯": 7, "扶": 7,
    "抓": 7, "投": 7, "抗": 7, "折": 7, "扼": 7, "找": 7, "把": 7, "报": 7,
    "曲": 6, "有": 6, "朱": 6, "朴": 6, "机": 6, "权": 6, "次": 6, "死": 6,
    "毕": 6, "氛": 8, "求": 7, "汗": 6, "江": 6, "池": 6, "污": 6, "汤": 6,
    "灯": 6, "灰": 6, "灾": 7, "百": 6, "竹": 6, "米": 6, "约": 6, "纪": 6,
    "羊": 6, "老": 6, "考": 6, "而": 6, "耳": 6, "聿": 6, "肉": 6, "自": 6,
    "至": 6, "舌": 6, "舟": 6, "色": 6, "艰": 8, "芋": 6, "芒": 6, "虫": 6,
    "血": 6, "行": 6, "衣": 6, "西": 6, "讲": 6, "许": 6, "论": 6, "设": 6,
    "访": 6, "讯": 6, "买": 6, "贞": 6, "负": 6, "走": 7, "赤": 7, "足": 7,
    "身": 7, "辛": 7, "辰": 7, "迁": 6, "迄": 6, "近": 7, "进": 7, "远": 7,
    "违": 7, "连": 7, "邦": 6, "邪": 6, "酉": 7, "采": 8, "里": 7, "重": 9,
    "金": 8, "防": 6, "阳": 6, "阴": 6, "阵": 6, "阶": 6, "我": 7, "你": 7,
    "时": 7, "作": 7, "但": 7, "位": 7, "低": 7, "住": 7, "佐": 7, "何": 7,
    "助": 7, "劲": 7, "劳": 7, "况": 7, "些": 8, "学": 8, "国": 8, "经": 8,
    "现": 8, "实": 8, "事": 8, "知": 8, "和": 8, "明": 8, "的": 8, "是": 9,
    "说": 9, "看": 9, "要": 9, "面": 9, "前": 9, "起": 10, "都": 10, "能": 10,
    "高": 10, "家": 10, "样": 10, "请": 10, "通": 10, "酒": 10, "猫": 11, "做": 11,
    "得": 11, "想": 13, "意": 13, "新": 13, "需": 14, "解": 13, "过": 6, "这": 7,
    "那": 6, "怎": 9, "感": 13, "觉": 9, "坏": 7, "多": 6, "短": 12, "热": 10,
    "冷": 7, "快": 7, "慢": 14, "美": 9, "贵": 9, "便": 9, "宜": 8, "啦": 11,
    "咯": 9, "咩": 9, "咧": 9, "啊": 10, "嘛": 14, "吗": 6, "呢": 8, "吧": 7,
    "刹": 8, "酱": 13,
}

DEFAULT_STROKE_COUNT = 8  # median fallback for unknown chars


def get_stroke_count(char: str) -> int:
    return STROKE_COUNTS.get(char, DEFAULT_STROKE_COUNT)


def score_character(char: str, personal_freq: int) -> float:
    """
    Lower score = higher learning priority.

    Combines stroke count (lower = easier) with personal frequency
    (higher = appears in more of YOUR vocab). The 2x weight on personal
    frequency means a char appearing in 5 vocab words can offset roughly
    10 strokes of difficulty.
    """
    return get_stroke_count(char) - 2 * personal_freq


# ----------------------------------------------------------------------
# SRS for handwriting — same SM-2 pattern as srs_engine
# ----------------------------------------------------------------------
HW_GRADE_AGAIN, HW_GRADE_HARD, HW_GRADE_GOOD, HW_GRADE_EASY = 0, 1, 2, 3
HW_EASE_FLOOR = 1.3
HW_HARD_MULT = 1.2
HW_EASY_MULT = 2.5


def compute_next_review(current_interval: int, current_ease: float, grade: int):
    """Returns (new_interval_days, new_ease, next_review_iso_date)."""
    if grade == HW_GRADE_AGAIN:
        new_ease = max(HW_EASE_FLOOR, current_ease - 0.20)
        new_interval = 0
    elif grade == HW_GRADE_HARD:
        new_ease = max(HW_EASE_FLOOR, current_ease - 0.15)
        new_interval = max(1, int(current_interval * HW_HARD_MULT)) if current_interval >= 1 else 1
    elif grade == HW_GRADE_GOOD:
        new_ease = current_ease
        if current_interval == 0:
            new_interval = 1
        elif current_interval == 1:
            new_interval = 3
        else:
            new_interval = int(current_interval * current_ease)
    else:  # EASY
        new_ease = current_ease + 0.15
        if current_interval == 0:
            new_interval = 2
        elif current_interval == 1:
            new_interval = 4
        else:
            new_interval = int(current_interval * current_ease * HW_EASY_MULT)

    new_interval = min(new_interval, 365)
    next_review_date = (date.today() + timedelta(days=new_interval)).isoformat()
    return new_interval, round(new_ease, 2), next_review_date


# ----------------------------------------------------------------------
# Auto-grading: objective quality from the drill result.
# The component reports mistakes/hints/revealed; this maps them to an SRS
# grade deterministically (unit-tested in run_tests.py).
# ----------------------------------------------------------------------
def quality_from_result(mistakes: int, hints: int, revealed: bool,
                        is_new: bool) -> int:
    """0=Again 1=Hard 2=Good 3=Easy."""
    if revealed:
        return HW_GRADE_AGAIN
    effective = mistakes + hints
    if effective == 0:
        # A flawless review earns Easy; a flawless first meeting only Good —
        # new characters should come back soon regardless.
        return HW_GRADE_GOOD if is_new else HW_GRADE_EASY
    if effective == 1:
        return HW_GRADE_GOOD
    if effective <= 3:
        return HW_GRADE_HARD
    return HW_GRADE_AGAIN


def choose_context_word(char: str, candidates):
    """Pick the best vocab word to show as the recall cue for a character:
    the word the learner knows best (highest review_count), tie-broken by
    shortest (clearest context). `candidates` = iterable of dicts with
    chinese/pinyin/english/review_count."""
    best = None
    for w in candidates:
        if char not in w.get("chinese", ""):
            continue
        key = (-(w.get("review_count") or 0), len(w["chinese"]))
        if best is None or key < best[0]:
            best = (key, w)
    return best[1] if best else None
