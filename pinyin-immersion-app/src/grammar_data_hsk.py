# src/grammar_data_hsk.py
"""
Structures the HSK 1-4 syllabus (2025) teaches that the app's own syllabus
didn't drill as structures of their own: no 是 before a date or a price,
how numbers are built, 第, dates and clock times, money, verb-object
words (睡觉), 和 joining nouns only, and where 都 goes.

Same fields as the rest of the curriculum (see grammar_curriculum.py); each
is listed under the section it belongs to, marked "(added)". hsk_grammar.py
says which HSK point each one teaches.
"""

from grammar_schema import Structure

_S = Structure

SECTIONS = {}

STRUCTURES = [
    _S("noun_predicate", 1, "No 是 before dates, ages, prices", "今天星期一。/ 他二十岁。/ 这个十块。",
       "Say the day, the date, someone's age or a price with no verb at all.",
       notes="A time, date, age or price can be the whole predicate: 今天星期一 / 明天"
             "十二号 / 我妹妹八岁 / 这个十块. No 是 is needed (今天是星期一 is also fine, "
             "but 他是二十岁 is wrong). The negative brings 是 back: 今天不是星期一 / 他不是"
             "二十岁. Drill: say the day, date, age, price; then deny one with 不是.",
       markers=("星期", "礼拜", "号", "岁", "块", "点", "月"), level=1, core=True),
    _S("numbers", 4, "Building numbers — 两 or 二, 零, 百, 千", "两个 / 二十二 / 一百零五 / 两千",
       "Say any number up to the thousands, and pick 两 or 二.",
       notes="Numbers are built in order: 三十五, 一百二十, 两千三百. 零 fills a gap: 一百零五, "
             "两千零八. 两 before a measure word (两个人, 两本书) and before 百 / 千 (两百, 两千); "
             "二 when counting, in 十二 / 二十, and in dates and phone numbers (二月, 十二号). "
             "Drill counting people and things, prices and years. Never 二个.",
       markers=("两", "二", "零", "百", "千"), level=1, core=True),
    _S("di_ordinal", 4, "第 + number — first, second", "第一次 / 第二天 / 第三课",
       "Say first, second, third (the order of something).",
       notes="第 + number + measure word / noun: 第一次 (the first time), 第二个, 第三天. "
             "Contrast plain number for how many: 三天 (three days) vs 第三天 (the third "
             "day). Dates and floors use no 第: 三月 (March), 三楼.",
       markers=("第",), level=1),
    _S("date_time", 6, "Dates and clock times", "十一月二十三号 / 星期一 / 九点半 / 两点十分",
       "Say the date, the day of the week and the time.",
       notes="Big to small: year, month, day, weekday, time — 2026年11月23号, 星期一, 早上九点. "
             "号 in speech, 日 in writing. Weekdays: 星期一 … 星期六, 星期天 (Malaysians also say "
             "礼拜一 … 礼拜天). Time: 两点 (not 二点), 九点半, 三点十五分, 七点零五. The time "
             "goes before the verb: 我八点上班. Drill saying when things happen.",
       markers=("年", "月", "号", "日", "星期", "礼拜", "点"), level=1, core=True),
    _S("money", 4, "Prices and money — 块 and 元", "二十四块(钱) / 一百块 / 多少钱？",
       "Ask and say how much something costs.",
       notes="Speech uses 块 (二十块, 两块五), writing and signs 元. 钱 after the amount is "
             "optional: 十块钱. 两块 not 二块. Malaysian ringgit is 块 too (马币 when it needs "
             "saying). The price can be the predicate with no verb: 这个十块. Drill asking "
             "多少钱 and answering.",
       markers=("块", "元", "钱"), level=1),
    _S("lihe_verbs", 25, "Verb-object words — 睡觉, 上班, 看病", "我没上班。/ 他睡觉了。/ 上了一天班",
       "Use the everyday 'verb + object' words: sleep, go to work, see a doctor, chat.",
       notes="睡觉, 上班, 下班, 上课, 下课, 说话, 看病, 生病 are a verb and its object fused: "
             "they take no second object (见面他 is wrong: 跟他见面). 了 and amounts can go "
             "in the middle: 上了一天班, 睡了八个钟头的觉 — but at this stage drill mostly the "
             "whole word with 了 / 没 / 在 around it: 他在上课 / 我没上班 / 睡觉了.",
       markers=("睡觉", "上班", "下班", "上课", "下课", "说话", "看病", "生病", "觉", "班", "课"),
       level=1),
    _S("he_and", 15, "和 — and (between nouns only)", "我和你 / 茶和咖啡 / 今天和明天",
       "Join two people or things with 'and'.",
       notes="和 joins nouns and pronouns: 我和她, 苹果和香蕉. It does NOT join sentences or "
             "verbs: 'I ate and went home' is 我吃了饭就回家了 / 我吃饭，然后回家 — never 和. "
             "In speech Malaysians often use 跟 the same way (我跟她). Drill: lists of two "
             "or three nouns; the subject 我和你 + 都.",
       contrast=("ye_also",), markers=("和", "跟"), level=1, core=True,
       requires=((r"(我|你|他|她|们|[一-鿿])(和|跟)[一-鿿]",
                  "和 / 跟 should join two nouns here"),)),
    _S("dou_all", 18, "都 — all, both (after the group)", "我们都去。/ 他们都是老师。/ 这些都很贵。",
       "Say everyone or everything in a group does or is something.",
       notes="都 goes after the group and before the verb: 我们都喜欢 (not 都我们喜欢). The "
             "group must come first, even when it's the object: 这些菜我都喜欢. 都不 = none "
             "(我们都不去), 不都 = not all (我们不都去). With 也: 我们也都去. Drill groups "
             "of people and things, then the 都不 / 不都 pair.",
       contrast=("ye_also",), markers=("都",), level=1, core=True),
]

LISTED = {
    1: [("No 是 before dates, ages, prices — HSK 1 (added)", "noun_predicate")],
    4: [("Numbers: 两 / 二, 零, 百, 千 — HSK 1 (added)", "numbers"),
        ("第 + number — HSK 1 (added)", "di_ordinal"),
        ("Prices: 块 / 元 — HSK 1 (added)", "money")],
    6: [("Dates and clock times — HSK 1 (added)", "date_time")],
    15: [("和 joining nouns — HSK 1 (added)", "he_and")],
    18: [("都 — all, both — HSK 1 (added)", "dou_all")],
    25: [("Verb-object words (睡觉, 上班) — HSK 1 (added)", "lihe_verbs")],
}
