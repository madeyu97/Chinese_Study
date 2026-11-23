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
    # ---- HSK 4 ----
    _S("shaowei", 14, "稍微 + verb / adjective + 一点 / 一下 — slightly", "稍微等一下 / 稍微便宜一点 / 稍微有点贵",
       "Say 'just a little', softening a request or a comparison.",
       notes="稍微 needs a small amount after it: 稍微 + verb + 一下 (稍微休息一下), 稍微 + adjective "
             "+ 一点 / 一些 (稍微快一点), or 稍微 + 有点 + adjective (稍微有点冷). Bare 稍微快 is "
             "wrong. Drill polite requests and bargaining.",
       markers=("稍微", "稍"), level=4,
       requires=((r"稍微?.{0,6}(一点|一些|一下|有点|一会)", "稍微 needs 一点 / 一下 / 有点 after it"),)),
    _S("que_but", 15, "Subject + 却 + verb — yet, but (unexpectedly)", "他很累，却睡不着。/ 东西便宜，质量却不好。",
       "Say the second half goes against what you'd expect.",
       notes="却 is an adverb: it goes after the second subject, before the verb - 价格便宜，"
             "质量却不好 - never at the start like 但是 (却质量 ✗). Often with 但是 too: 但他却没来.",
       contrast=("danshi",), markers=("却",), level=4),
    _S("bing_bu", 2, "并不 / 并没(有) — not at all, actually not", "这并不难。/ 我并没有生气。",
       "Correct an assumption: it's actually not so.",
       notes="并 + 不 / 没 strengthens a negative that contradicts what someone thinks: 他并不"
             "是老师 (he isn't actually a teacher). Usually after something was assumed.",
       markers=("并不", "并没"), level=4),
    _S("daodi", 3, "到底 / 究竟 — … on earth? / in the end", "你到底去不去？/ 他究竟是谁？/ 他到底来了。",
       "Press for a real answer, or say something finally happened.",
       notes="In a question 到底 / 究竟 presses: 你到底要什么？ (what on earth do you want?). It "
             "goes before the verb or question; it can't join 吗 (到底…吗 ✗). In a statement "
             "到底 = in the end, after all: 他到底还是来了.",
       markers=("到底", "究竟"), level=4),
    _S("cai_ne", 16, "才……呢 — really (emphatic)", "我才不去呢！/ 这里的菜才好吃呢！",
       "Insist strongly: I'm certainly not …, it's really …!",
       notes="才 + verb / adjective + 呢 stresses a contradicting point: 我才不信呢 (as if I'd "
             "believe it), 那场比赛才精彩呢 (now that was exciting). Spoken, emotional.",
       markers=("才",), level=4,
       requires=((r"才.{1,10}呢", "needs 才 … 呢"),)),
    _S("bu_zenme", 14, "不怎么 + verb / adjective — not very, not much", "不怎么好吃 / 我不怎么喜欢 / 他不怎么来",
       "Say something is not very much so, gently.",
       notes="不怎么 = not very / not often: 这家店不怎么好吃, 我不怎么看电视. Softer than 不. "
             "Contrast 不怎么样 (not up to much, at the end: 这家店不怎么样).",
       markers=("不怎么",), level=4),
    _S("yi_bi_yi", 13, "一 + MW + 比 + 一 + MW — more each time", "一天比一天热 / 一次比一次好",
       "Say something keeps getting more so, each time / day / year.",
       notes="一天比一天 + adjective = by the day: 天气一天比一天热. Also 一年比一年, 一次比一次. "
             "No 很 / 更 after it.",
       contrast=("yuelaiyue",), markers=("一天比一天", "一次比一次", "一年比一年", "一个比一个"),
       level=4),
    _S("gou_de", 14, "(真)够 + adjective + 的 — really quite", "今天真够热的！/ 这个够贵的。",
       "Say something is really (enough to comment on).",
       notes="够 + adjective + 的 = really rather, usually a remark: 真够累的, 你够忙的. Keep the 的.",
       markers=("够",), level=4, requires=((r"够.{1,5}的", "needs 够 … 的"),)),
    _S("zai_ye_bu", 16, "再也不 / 再也没 — never again", "我再也不去了。/ 他再也没来过。",
       "Say something will never happen again, or never did again.",
       notes="再也不 + verb (+ 了) for the future: 我再也不迟到了. 再也没 + verb (+ 过) for since "
             "then: 毕业以后，我再也没见过他. 再 and 也 stay together before 不 / 没.",
       markers=("再也不", "再也没"), level=4, core=True),
    _S("you_shenme_hao", 29, "有什么好 + verb + 的 — what's there to …?", "有什么好怕的？/ 没什么好说的。",
       "Say there's no reason to do or feel something.",
       notes="有什么好 + verb / feeling + 的 (？) = there's nothing to …: 有什么好担心的 (what's "
             "there to worry about?). 没(有)什么好 + verb + 的 says it plainly.",
       markers=("什么好",), level=4, requires=((r"什么好.{1,4}的", "needs 什么好 … 的"),)),
    _S("x_shi_x", 15, "X 是 X，(就是 / 不过) …… — it is X, but …", "便宜是便宜，就是质量不好。/ 累是累，不过很开心。",
       "Admit something, then add the catch.",
       notes="Adjective / verb + 是 + the same word concedes the point, then 就是 / 不过 / 可是 "
             "brings the 'but': 好吃是好吃，就是太贵. Also 我们讨论是讨论了，可是…. The repeated "
             "word must be the same.",
       markers=("是",), level=4, core=True,
       requires=((r"([\u4e00-\u9fff]{1,2})是\1", "needs the same word on both sides of 是"),)),
    _S("si_le", 9, "Adjective / feeling + 死了 / 得厉害 — terribly", "累死了 / 热死了 / 疼得厉害",
       "Exaggerate: it's terribly so.",
       notes="Adjective or feeling + 死了 = to death (spoken): 饿死了, 吵死了, 高兴死了. + 得厉害 = "
             "badly, a lot: 疼得厉害. Only for feelings and states.",
       contrast=("jile",), markers=("死了", "厉害"), level=4),
    _S("pot_liao", 9, "Verb + 得了 / 不了 — can / can't (manage)", "吃得了吗？/ 我去不了。/ 忘不了",
       "Say whether something is possible at all.",
       notes="Verb + 得了 (liǎo) / 不了 = can / can't, about whether it's possible at all: 这么多菜"
             "吃不了 (can't eat it all), 明天我去不了 (can't make it), 我忘不了 (can't forget). Not "
             "the 了 (le) of completion.",
       contrast=("pot_bu",), markers=("得了", "不了"), level=4),
    _S("gen_xiangbi", 13, "跟 / 和 …… 相比 — compared with", "跟去年相比，今年更热。",
       "Compare against something at the start of a sentence.",
       notes="跟 / 和 + B + 相比 (,) + A …: 跟巴士相比，地铁快多了. It sets the comparison first; "
             "the rest uses 更 / 多了 / 比较.",
       markers=("相比",), level=4),
    _S("double_neg", 2, "Double negatives — 没有……不 / 不能不", "没有人不喜欢。/ 我不能不去。/ 不可能没听说过",
       "Make a strong positive by negating twice.",
       notes="没有 + someone + 不 + verb = everyone: 没有人不知道. 不能不 / 不得不 = have to: "
             "我不得不走. 不可能没 = must have. The two negatives cancel and stress it.",
       markers=("没有人不", "不能不", "不得不", "不可能不", "不可能没", "不会不", "没有不"), level=4),
    _S("shouxian_qici", 15, "首先……，其次 / 然后…… — first …, second …",
       "首先要准备好，然后再出发。/ 首先是价格，其次是质量。",
       "Order points or steps in a list.",
       notes="首先 (first) … 其次 (second) … for points; 首先 … 然后 … 最后 … for steps. Formal "
             "but common in explanations.",
       markers=("首先",), level=4),
    _S("yushi", 15, "……，于是…… — so, and then (as a result)", "下雨了，于是我们回家。",
       "Say what happened as a result, in a story.",
       notes="于是 starts the clause that happened because of the first: 他饿了，于是去买东西吃. "
             "For past events in narration; for advice or the future use 所以 / 就.",
       contrast=("suoyi",), markers=("于是",), level=4),
    _S("bushi_jiushi", 15, "不是 A，就是 B — either A or B", "周末他不是游泳，就是打球。",
       "Say it's always one of two things.",
       notes="不是 … 就是 … = if not A then B, always one of the two: 他不是在家就是在公司. "
             "Contrast 不是 … 而是 (not A but B).",
       contrast=("bushi_ershi",), markers=("不是",), level=4,
       requires=((r"不是.+就是", "needs 不是 … 就是"),)),
    _S("jinguan", 15, "尽管……，但是 / 还是…… — even though", "尽管很累，他还是来了。",
       "Say something happens despite a fact.",
       notes="尽管 + a real fact, then 但是 / 可是 / 还是 / 却: 尽管下雨，我们还是去了. Like 虽然 "
             "but stronger. Not for hypotheses - that's 即使.",
       contrast=("suiran_danshi", "jishi_ye"), markers=("尽管",), level=4),
    _S("fouze", 27, "……，否则…… — otherwise", "快点走，否则来不及了。",
       "Say what will happen if something isn't done.",
       notes="Do this, 否则 (otherwise) that bad result: 你要带伞，否则会淋湿. Often after 要是 "
             "/ 必须 / 一定要. Spoken alternative: 不然.",
       markers=("否则", "不然"), level=4, core=True),
    _S("hao_purpose", 26, "……，好 + verb — so that", "早点睡，好明天早起。/ 给我打电话，好让我放心。",
       "Say the purpose of the first action.",
       notes="Second clause starts with 好 = so that: 我写下来，好记住 (I'll write it down so I "
             "remember). Often 好让 + person. Not 'good' here.",
       markers=("好",), level=4, requires=((r"[，,]\s*好[\u4e00-\u9fff]", "好 must start the second "
                                             "clause"),)),
    _S("num_lai", 4, "Number + 来 + measure word — about, getting on for", "三十来个人 / 一百来块 / 十来天",
       "Say an approximate number, around a round figure.",
       notes="Round number (十, 二十, 一百) + 来 + measure word = about: 二十来岁 (about twenty), "
             "一百来本书. Contrast 多 (more than) and 左右 (around, after the measure word).",
       contrast=("num_duo",), markers=("来",), level=4,
       requires=((r"(十|百|千|万)来(个|本|块|岁|天|年|人|次|分钟|公斤|间|张)", "needs a round number + 来 + "
                  "measure word"),)),
    _S("fractions", 4, "Decimals, fractions, percentages, times", "零点五 / 三分之一 / 百分之二十 / 两倍",
       "Say decimals, fractions, percentages and 'times as much'.",
       notes="Decimal: 点 (三点五 = 3.5, 零点五 = 0.5). Fraction: bottom 分之 top (三分之一 = 1/3). "
             "Percent: 百分之 + number (百分之二十). Times: 两倍 (twice); 比 … 贵两倍. Drill prices, "
             "discounts (打八折 is Malaysian/Chinese for 20% off) and statistics.",
       markers=("点", "分之", "倍", "折"), level=4),
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
    4: [("Number + 来 — HSK 4 (added)", "num_lai"),
        ("Decimals, fractions, percentages — HSK 4 (added)", "fractions"),
        ("Numbers: 两 / 二, 零, 百, 千 — HSK 1 (added)", "numbers"),
        ("第 + number — HSK 1 (added)", "di_ordinal"),
        ("Prices: 块 / 元 — HSK 1 (added)", "money"),
        ("Two neighbouring numbers — about — HSK 3 (added)", "approx_adjacent"),
        ("Doubled measure words — HSK 3 (added)", "mw_redup")],
    6: [("Dates and clock times — HSK 1 (added)", "date_time")],
    15: [("和 joining nouns — HSK 1 (added)", "he_and"),
         ("却 — HSK 4 (added)", "que_but"),
         ("X 是 X，就是 — HSK 4 (added)", "x_shi_x"),
         ("首先……其次 / 然后 — HSK 4 (added)", "shouxian_qici"),
         ("于是 — HSK 4 (added)", "yushi"),
         ("不是……就是 — HSK 4 (added)", "bushi_jiushi"),
         ("尽管 — HSK 4 (added)", "jinguan")],
    18: [("都 — all, both — HSK 1 (added)", "dou_all")],
    25: [("Verb-object words (睡觉, 上班) — HSK 1 (added)", "lihe_verbs"),
         ("请 / 叫 / 让 + person + verb — HSK 2 (added)", "jianyu_causative")],
    29: [("……什么的 — HSK 2 (added)", "shenmede"),
         ("有什么好……的 — HSK 4 (added)", "you_shenme_hao")],
    28: [("X 什么(啊) — HSK 3 (added)", "x_shenme_a")],
    13: [("有 + amount / 有…那么 — HSK 2 (added)", "you_reach"),
         ("A 不比 B — HSK 3 (added)", "bu_bi"),
         ("一 + MW + 比 + 一 + MW — HSK 4 (added)", "yi_bi_yi"),
         ("跟……相比 — HSK 4 (added)", "gen_xiangbi")],
    2: [("不用 / 不必 — HSK 3 (added)", "buyong"),
        ("并不 / 并没 — HSK 4 (added)", "bing_bu"),
        ("Double negatives — HSK 4 (added)", "double_neg")],
    3: [("到底 / 究竟 — HSK 4 (added)", "daodi")],
    9: [("死了 / 得厉害 — HSK 4 (added)", "si_le"),
        ("Verb + 得了 / 不了 — HSK 4 (added)", "pot_liao")],
    26: [("……，好 + verb — HSK 4 (added)", "hao_purpose")],
    27: [("……，否则…… — HSK 4 (added)", "fouze")],
    7: [("总 / 总是 — HSK 3 (added)", "zongshi"),
        ("Event + time + 了 — it's been … since — HSK 3 (added)", "time_since")],
    17: [("一 + MW + 也 / 都 + 不 / 没 — HSK 3 (added)", "yi_mw_ye_bu")],
    16: [("该……了 — HSK 3 (added)", "gai_le"),
         ("Verb + 了 … 就 — HSK 3 (added)", "le_jiu"),
         ("才……呢 — HSK 4 (added)", "cai_ne"),
         ("再也不 / 再也没 — HSK 4 (added)", "zai_ye_bu")],
    19: [("一会……一会…… — HSK 3 (added)", "yihui_yihui")],
    21: [("Place + verb + 了 + new thing — HSK 3 (added)", "appear_disappear")],
    23: [("在……上 / 下 / 中 — HSK 3 (added)", "zai_shang_xia")],
    14: [("这么 / 那么 / 这样 — HSK 2 (added)", "zheme_name"),
         ("不 A 不 B — HSK 3 (added)", "bu_a_bu_b"),
         ("稍微 — HSK 4 (added)", "shaowei"),
         ("不怎么 — HSK 4 (added)", "bu_zenme"),
         ("够……的 — HSK 4 (added)", "gou_de")],
}
