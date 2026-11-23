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
             "两千零八; 万 for ten thousands (两万三千). 两 before a measure word (两个人, 两本书) "
             "and before 百 / 千 / 万 (两百, 两千); "
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
    # ---- HSK 2 ----
    _S("jianyu_causative", 25, "请 / 叫 / 让 + person + verb — get someone to do",
       "妈妈叫我去买菜。/ 我想请老师教我。/ 让他进来。",
       "Say you ask, tell or let someone do something.",
       notes="Subject + 请 / 叫 / 让 + person + verb (+ object): the person is the object of "
             "the first verb and the doer of the second. 请 = invite / ask politely, 叫 = "
             "tell, 让 = let / make. Negation goes before the first verb: 妈妈不让我去. "
             "Drill asking, telling and letting; never 让 + 去 + 他.",
       markers=("请", "叫", "让"), level=2, core=True,
       requires=((r"(请|叫|让)(我|你|他|她|我们|你们|他们|大家|[\u4e00-\u9fff]{1,3})"
                  r"[\u4e00-\u9fff]", "请 / 叫 / 让 needs a person and then a verb"),)),
    _S("shenmede", 29, "……什么的 — and so on", "苹果、香蕉什么的 / 唱歌、跳舞什么的",
       "End a list with 'and things like that'.",
       notes="Two or three examples, then 什么的: 我喜欢看书、听音乐什么的. Spoken and "
             "relaxed. Drill lists of food, hobbies, things to buy.",
       markers=("什么的",), level=2),
    _S("double_subject", 1, "Topic + subject + adjective — 她个子很高", "她个子很高。/ 我头疼。/ 这家店菜很好吃。",
       "Describe one feature of someone or something.",
       notes="The whole sentence is about the first noun; the second noun is the part "
             "described: 她个子很高 (she is tall - lit. she, height is high), 我头疼 (I have "
             "a headache), 这家店菜很便宜. No 的 needed (她的个子很高 is also fine). Drill "
             "people's looks, health, places.",
       markers=("个子", "头", "身体", "菜", "工作", "眼睛", "天气", "很", "疼"), level=2),
    _S("you_reach", 13, "有 + amount / 有…那么 — as much as", "他有三十岁吗？/ 你有他高吗？",
       "Ask or say whether something reaches an amount or a standard.",
       notes="有 + amount: reaching it (这条鱼有两公斤 / 他有三十岁吗？). A 有 B (那么 / 这么) "
             "+ adjective: as … as (你有他高吗？). Mostly in questions and negatives - the "
             "negative 没有…那么 is its own structure (meiyou_name).",
       contrast=("meiyou_name",), markers=("有",), level=2,
       requires=((r"有.{0,6}(岁|块|公斤|米|多|那么|这么|高|大|长|远|吗)",
                  "有 should reach an amount or a standard here"),)),
    _S("zheme_name", 14, "这么 / 那么 / 这样 — so, like this", "这么贵！/ 他那么忙 / 这样做",
       "Say 'so (much)' or 'like this / that'.",
       notes="这么 / 那么 + adjective: so …: 这么贵 (this expensive), 那么远 (that far). "
             "这样 / 那样 + verb: like this: 这样写, 你别那样说. 这么 for here and now, 那么 "
             "for there or what someone said. Drill surprise at prices and distances, "
             "showing how to do things.",
       markers=("这么", "那么", "这样", "那样"), level=2),
    # ---- HSK 3 ----
    _S("zongshi", 7, "总 / 总是 — always", "他总是迟到。/ 一到冬天就总生病。",
       "Say something always (or keeps on) happening.",
       notes="总是 / 总 + verb, often with a hint of complaint: 他总是迟到. Contrast 常常 "
             "(often) - 总是 is every time. Negative: 他总是不吃早餐 (always skips it); 不总是 "
             "= not always. Drill habits and complaints.",
       markers=("总是", "总"), level=3, core=True),
    _S("yi_mw_ye_bu", 17, "一 + measure word + 也 / 都 + 不 / 没 — not a single one",
       "我一个人也不认识。/ 他一块钱都没有。/ 一句也听不懂",
       "Say not even one: not a single person, word, ringgit.",
       notes="一 + measure word (+ noun) + 也 / 都 + 不 / 没 + verb: 我一句华语也不会说, 我一"
             "口都没吃. The 'one' thing goes before the verb, never after (我不认识一个人 means "
             "something else). 一点也不 + adjective is its own structure (yidian_bu).",
       contrast=("yidian_bu",), markers=("也不", "也没", "都不", "都没"), level=3, core=True,
       requires=((r"一[^也都]{1,4}(也|都)(不|没)", "needs 一 + measure word + 也 / 都 + 不 / 没"),)),
    _S("buyong", 2, "不用 / 不必 — no need to", "不用谢。/ 你不用来。/ 不必担心。",
       "Say something isn't necessary.",
       notes="不用 + verb (spoken) / 不必 + verb (a bit more formal): 你不用来 (you needn't "
             "come). It's the negative of 要 / 得 / 必须 for 'have to': 我得去 → 你不用去. "
             "Contrast 别 / 不要 (don't!): 不用 is relief, not a ban. Malaysians also say "
             "不用紧 (it's fine).",
       contrast=("bie",), markers=("不用", "不必"), level=3),
    _S("approx_adjacent", 4, "Two numbers side by side — about", "七八个人 / 十五六分钟 / 三四天",
       "Give a rough number by saying two neighbouring numbers.",
       notes="Two neighbouring numbers = roughly: 两三个 (two or three), 七八个人, 十五六岁, "
             "三四天. Always neighbours, smaller first; never with 九十 (that's 90). Contrast "
             "多 (二十多) and 左右 / 大概.",
       markers=("一两", "两三", "三四", "四五", "五六", "六七", "七八", "八九"), level=3),
    _S("bu_a_bu_b", 14, "不 A 不 B — just right", "不大不小 / 不冷不热 / 不多不少",
       "Say something is just right: neither too big nor too small.",
       notes="不 + adjective + 不 + its opposite = just right: 不大不小, 不冷不热, 不早不晚. "
             "Usually followed by 刚好 / 正好 / 很舒服. Only with pairs of opposites.",
       markers=("不大不小", "不冷不热", "不多不少", "不早不晚", "不高不矮", "不长不短",
                "不胖不瘦", "不远不近", "不贵不便宜"), level=3),
    _S("x_shenme_a", 28, "X 什么(啊) — what do you mean, X?", "贵什么啊! / 急什么? / 方便什么啊",
       "Brush off or contradict what someone said.",
       notes="Verb / adjective + 什么(啊) rejects it: 贵什么啊，才十块 (expensive? it's only ten), "
             "急什么 (what's the hurry?). Not a question about 'what'. Friendly but blunt; "
             "usually followed by the reason.",
       markers=("什么啊", "什么呀", "什么?", "什么？", "什么!", "什么！"), level=3,
       requires=((r"[\u4e00-\u9fff](什么)(啊|呀|？|\?|!|！|，|,)", "X 什么 must follow a verb or "
                  "adjective it rejects"),)),
    _S("gai_le", 16, "该……了 — it's time to", "该走了。/ 八点了，该上课了。/ 该你了。",
       "Say it's time for something, or someone's turn.",
       notes="该 + verb + 了 = it's time to: 该睡觉了, 该吃饭了. 该 + person + 了 = your turn: "
             "该你了. Different from 应该 (should).",
       contrast=("yinggai",), markers=("该",), level=3,
       requires=((r"该.{1,8}了", "该 … 了 needs the 了"),)),
    _S("zai_shang_xia", 23, "在……上 / 下 / 中 — in terms of, under, during",
       "在工作上 / 在老师的帮助下 / 在学习中",
       "Say in which area, under whose influence, or in the course of what.",
       notes="在 + topic + 上 = as far as … goes: 在工作上很认真. 在 + 的帮助 / 影响 / 情况 + 下 "
             "= with the help / influence of: 在朋友的帮助下. 在 + process + 中 = in the "
             "course of: 在学习中. Goes at the start or before the verb.",
       markers=("上", "下", "中"), level=3,
       requires=((r"在[^。，,]{1,10}(上|下|中)", "needs 在 … 上 / 下 / 中"),)),
    _S("verb_subject", 1, "A verb or clause as the subject", "哭没有用。/ 多运动对身体好。/ 你来也可以。",
       "Make an action the topic: 'crying won't help'.",
       notes="An action, with no 'to' or '-ing', can be the subject: 哭没有用 (crying is no "
             "use), 学华语很有意思, 早点睡比较好. A whole clause can be too: 你来也可以 (you "
             "coming is fine too). Drill opinions about activities.",
       markers=("没有用", "很好", "比较好", "最重要", "有意思", "也可以", "不好", "很难",
                "很容易", "对身体"), level=3),
    _S("mw_redup", 4, "Doubled measure words — every one / one by one", "个个都很大 / 一步一步地做",
       "Say every single one, or do something one at a time.",
       notes="Measure word doubled + 都 = every one: 个个都好吃, 天天 (every day), 张张都漂亮. "
             "一 + MW + 一 + MW (+ 地) + verb = one by one: 一个一个地来, 一步一步地学.",
       markers=("个个", "天天", "人人", "张张", "件件", "本本", "一步一步", "一个一个",
                "一句一句", "一天一天", "一点一点"), level=3),
    _S("time_since", 7, "Event + 已经 + time + 了 — it's been … since",
       "他走了已经三天了。/ 开学已经两个星期了。/ 我来马来西亚五年了。",
       "Say how long it has been since something happened.",
       notes="Event (verb that happens once: 来, 走, 毕业, 结婚) + (已经) + length of time + 了 = "
             "it's been that long since: 他来了三年了, 我们结婚十年了. Contrast duration of an "
             "activity (我学了两年 = studied for two years). Ask: 你来马来西亚多久了？",
       contrast=("le_le",), markers=("了",), level=3,
       requires=((r"(年|天|个月|个星期|个礼拜|个钟头|小时|分钟|多久)(多)?了", "needs a length of "
                  "time + 了 at the end"),)),
    _S("appear_disappear", 21, "Place + verb + 了 + someone / something — appeared, left",
       "前面开过来一辆车。/ 楼上搬来了一家人。/ 树上飞走了三只鸟。",
       "Say someone or something appeared at or left a place.",
       notes="Place first, then verb + direction / result + (了) + amount + thing: 前面走过来"
             "一个人 (someone came walking over), 家里来了客人, 店里少了一个人. The thing is new "
             "information, so it comes after the verb, usually with a number. Contrast "
             "place + 有 and place + verb + 着.",
       contrast=("zhe_scene", "place_you"), markers=("来", "走", "了"), level=3,
       requires=((r"(来|去|走|出|进|过来|过去|掉)了?(一|两|三|几|很多)", "needs verb + 来 / 走 … + "
                  "an amount + the new person or thing"),)),
    _S("yihui_yihui", 19, "一会……一会…… — now … now …", "一会进来，一会出去 / 天气一会冷，一会热",
       "Say something keeps switching between two things.",
       notes="一会 + A，一会 + B: he keeps going in and out, the weather keeps changing. "
             "Often with a little complaint. (Mainland writes 一会儿; Malaysians say 一会.)",
       markers=("一会",), level=3,
       requires=((r"一会.+一会", "needs 一会 twice"),)),
    _S("le_jiu", 16, "Verb + 了 + … + 就 + … — as soon as / after … then",
       "我下了班就去。/ 他吃了药就好多了。/ 你到了就打电话给我。",
       "Say one thing happens straight after another is done.",
       notes="First action + 了 (+ object), then 就 + second action: 我下了班就回家 (I go home "
             "once I finish work). Works for future and past; the 了 marks 'once done', not "
             "past. Close to 一……就 but less instant.",
       contrast=("yi_jiu",), markers=("就",), level=3,
       requires=((r"了.{0,8}就", "needs verb + 了 … 就"),)),
    _S("bu_bi", 13, "A 不比 B + adjective — no more … than", "我不比他高。/ 这个不比那个贵。",
       "Say A is not more … than B (they're about the same).",
       notes="A 不比 B + adjective means A is no more … than B, often 'about the same' or "
             "contradicting: 我不比他高 (I'm not taller than him - we're about the same). It "
             "is NOT the usual 'less than' - that's A 没有 B (那么) + adjective.",
       contrast=("meiyou_name", "bi_adj"), markers=("不比",), level=3),
    _S("dou_all", 18, "都 — all, both (after the group)", "我们都去。/ 他们都是老师。/ 这些都很贵。",
       "Say everyone or everything in a group does or is something.",
       notes="都 goes after the group and before the verb: 我们都喜欢 (not 都我们喜欢). The "
             "group must come first, even when it's the object: 这些菜我都喜欢. 都不 = none "
             "(我们都不去), 不都 = not all (我们不都去). With 也: 我们也都去. Drill groups "
             "of people and things, then the 都不 / 不都 pair.",
       contrast=("ye_also",), markers=("都",), level=1, core=True),
]

LISTED = {
    1: [("No 是 before dates, ages, prices — HSK 1 (added)", "noun_predicate"),
        ("Topic + subject + adjective (她个子很高) — HSK 2 (added)", "double_subject"),
        ("A verb or clause as the subject — HSK 3 (added)", "verb_subject")],
    4: [("Numbers: 两 / 二, 零, 百, 千 — HSK 1 (added)", "numbers"),
        ("第 + number — HSK 1 (added)", "di_ordinal"),
        ("Prices: 块 / 元 — HSK 1 (added)", "money"),
        ("Two neighbouring numbers — about — HSK 3 (added)", "approx_adjacent"),
        ("Doubled measure words — HSK 3 (added)", "mw_redup")],
    6: [("Dates and clock times — HSK 1 (added)", "date_time")],
    15: [("和 joining nouns — HSK 1 (added)", "he_and")],
    18: [("都 — all, both — HSK 1 (added)", "dou_all")],
    25: [("Verb-object words (睡觉, 上班) — HSK 1 (added)", "lihe_verbs"),
         ("请 / 叫 / 让 + person + verb — HSK 2 (added)", "jianyu_causative")],
    29: [("……什么的 — HSK 2 (added)", "shenmede")],
    28: [("X 什么(啊) — HSK 3 (added)", "x_shenme_a")],
    13: [("有 + amount / 有…那么 — HSK 2 (added)", "you_reach"),
         ("A 不比 B — HSK 3 (added)", "bu_bi")],
    2: [("不用 / 不必 — HSK 3 (added)", "buyong")],
    7: [("总 / 总是 — HSK 3 (added)", "zongshi"),
        ("Event + time + 了 — it's been … since — HSK 3 (added)", "time_since")],
    17: [("一 + MW + 也 / 都 + 不 / 没 — HSK 3 (added)", "yi_mw_ye_bu")],
    16: [("该……了 — HSK 3 (added)", "gai_le"),
         ("Verb + 了 … 就 — HSK 3 (added)", "le_jiu")],
    19: [("一会……一会…… — HSK 3 (added)", "yihui_yihui")],
    21: [("Place + verb + 了 + new thing — HSK 3 (added)", "appear_disappear")],
    23: [("在……上 / 下 / 中 — HSK 3 (added)", "zai_shang_xia")],
    14: [("这么 / 那么 / 这样 — HSK 2 (added)", "zheme_name"),
         ("不 A 不 B — HSK 3 (added)", "bu_a_bu_b")],
}
