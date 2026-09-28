# src/grammar_data_2.py
"""Grammar curriculum, groups 4-8: measure words, aspect, time, duration and
frequency, modal verbs."""

from grammar_schema import Structure

SECTIONS = {
    4: "Measure Words & Quantity",
    5: "Aspect & Event Structure",
    6: "Time & Temporal Relationships",
    7: "Duration, Frequency & Repetition",
    8: "Modal Verbs",
}

_S = Structure
_MW = ("本", "张", "件", "杯", "瓶", "只", "条", "辆", "台", "家", "间", "位", "名")
_LE = ("Never call 了 'past tense': it marks a completed action (which can be in "
       "the future or a condition) or a change of situation. Past states and "
       "habits take no 了. Malaysians often pronounce 了 'liao'. ")

STRUCTURES = [
    # ------------------------------------------------------------------
    # 4. Measure words & quantity
    # ------------------------------------------------------------------
    _S("mw_ge", 4, "个 — the all-purpose measure word", "一个人 / 两个苹果 / 这个",
       "Count things with 个 when there is no special measure word (or you don't know it).",
       notes="Numbers and 这/那/哪/几 need a measure word before a noun; 个 is the "
             "default and very common in speech. 两 (not 二) before measure words.",
       markers=("个",), level=1, core=True),
    _S("mw_common", 4, "Common measure words", "一本书 · 一张票 · 一件衣服 · 一杯咖啡 · 一辆车",
       "Use the right measure word for books, tickets, clothes, cups, animals, vehicles and more.",
       notes="Choose measure words that fit the learner's known nouns: 本 books, 张 "
             "flat things (tickets, tables, beds, photos), 件 clothes and matters, 杯 "
             "cups/glasses, 瓶 bottles, 只 animals and one of a pair, 条 long things "
             "(fish, roads, trousers), 辆 vehicles, 台 machines, 家 shops/companies/"
             "restaurants, 间 rooms, 位 people (polite), 名 people (formal). 次/遍 count "
             "actions and have their own structures. Identify: which noun could follow?",
       markers=_MW, level=2, core=True),
    _S("num_mw_noun", 4, "Number + measure word + noun", "三个人 / 两杯咖啡",
       "Say how many of something.",
       notes="Always number + measure word + noun (NOT 三人 in everyday speech). 两, "
             "not 二, before a measure word. Vary the measure words with the nouns "
             "the learner knows.",
       level=1, core=True),
    _S("zhe_na_mw", 4, "这 / 那 + measure word + noun", "这本书 / 那家店 / 这两个人",
       "Point to 'this one' or 'that one'.",
       notes="A measure word is needed after 这/那 (这个, 那本). With a number: 这两本, "
             "那三个. 这些/那些 for plurals.",
       markers=("这", "那"), level=1),
    _S("yidian", 4, "一点 — a little", "喝一点水 / 便宜一点 / 快一点",
       "Say 'a little' of something, or ask for something to be a bit more so.",
       notes="Before a noun (一点水); after an adjective to compare or request (便宜"
             "一点, 慢一点). NOT before an adjective to mean 'slightly' - that is 有点 "
             "(有点贵). Never 一点儿.",
       markers=("一点",), level=1),
    _S("yixie", 4, "一些 — some", "买一些水果 / 一些人",
       "Talk about an unspecified amount: some.",
       notes="一些 + noun, or after a verb (做一些事). 这些/那些 = these/those.",
       markers=("些",), level=2),
    _S("haoji", 4, "好几 + measure word — quite a few", "好几个人 / 好几次 / 好几天",
       "Say there were quite a few — more than you'd expect.",
       notes="Emphasises a surprisingly large number: 我等了好几个钟头 / 他来过好几次.",
       markers=("好几",), level=3),
    _S("jige", 4, "几个 — a few (not a question)", "买几个 / 几个朋友",
       "Say 'a few' — the same 几, used in a statement.",
       notes="In a statement 几 means a few (我有几个问题 / 买几个面包). Identify: is it "
             "a question or 'a few'?",
       contrast=("ji_howmany",), markers=("几",), level=2),
    _S("num_duo", 4, "Number + 多 — more than, -odd", "二十多个人 / 一个多钟头 / 三百多块",
       "Say 'more than' a round number: twenty-odd, an hour and a bit.",
       notes="With round tens/hundreds 多 goes BEFORE the measure word (二十多个, 一百"
             "多块); with a single digit and a divisible amount it goes AFTER (一个多"
             "钟头, 两块多).",
       markers=("多",), level=3),
    _S("quantity_de_noun", 4, "Amount + 的 + noun", "三天的时间 / 两个钟头的车 / 一百块的东西",
       "Describe a noun by its amount: a three-day trip, a two-hour drive.",
       notes="Amount or duration + 的 + noun: 两个钟头的路, 五分钟的休息. Keep apart "
             "from V + duration + 的 + O (看了两个钟头的书), a separate structure.",
       markers=("的",), level=3, also_in=(7,)),
    _S("yigong", 4, "一共 — altogether", "一共 + 多少 / 数量",
       "Give or ask for a total.",
       notes="一共多少钱？ / 我们一共五个人 / 他一共来了三次 (counts of times too).",
       markers=("一共",), level=2, also_in=(7,)),
    _S("dayue", 4, "大约 / 大概 — about, roughly", "大约 / 大概 + 数量",
       "Say a number is approximate.",
       notes="Before the number (大概三十个人). 大概 before a verb also means "
             "'probably' (他大概不来了) - include both meanings in identify tasks.",
       markers=("大约", "大概"), level=2),
    _S("chabuduo", 4, "差不多 — about / almost / much the same", "差不多 + 数量 / 差不多了",
       "Say 'about', 'almost', or 'pretty much the same'.",
       notes="差不多十点了 (almost), 差不多五十块 (about), 这两个差不多 (similar), 差不"
             "多了 (nearly done / that'll do).",
       markers=("差不多",), level=2),
    _S("zuoyou", 4, "左右 — or so", "数量 + 左右",
       "Put 左右 after a number to mean 'or so'.",
       notes="After the number (八点左右, 五十块左右). Don't stack it with 大概 in the "
             "same phrase.",
       contrast=("dayue",), markers=("左右",), level=2),
    _S("duo_shao_verb", 4, "多 / 少 + verb — more / less", "多吃一点 / 少喝酒 / 多穿一件",
       "Tell someone to do more or less of something.",
       notes="The syllabus lists '多/少 + adjective'; the everyday pattern is 多/少 "
             "before a VERB (多喝水, 少吃糖), often with 一点 after. Advice and "
             "requests.",
       markers=("多", "少"), level=2),
    _S("bijiao_adj", 4, "比较 + adjective — fairly, relatively", "比较 + 形容词",
       "Say something is fairly or relatively so.",
       notes="今天比较热 / 这家比较便宜. Softer than 很 and implies a comparison.",
       markers=("比较",), level=2, also_in=(14,)),
    _S("zui_adj", 4, "最 + adjective — the most", "最 + 形容词 / 最 + 动词",
       "Say something is the most (or least) of all.",
       notes="最好吃 / 最喜欢 / 最不喜欢 / 最早.",
       markers=("最",), level=1, also_in=(13, 14)),

    # ------------------------------------------------------------------
    # 5A. 了
    # ------------------------------------------------------------------
    _S("le_verb", 5, "Verb + 了 — it got done", "吃了 / 买了三本书",
       "Mark that an action is completed — past, future or conditional.",
       notes=_LE + "Show completion in the future too (明天下了班我找你) and in "
             "sequence (吃了饭再去). A bare V了 + object sounds unfinished (我吃了饭…), "
             "so give the object an amount or add a follow-up clause.",
       contrast=("le_final", "mei_neg"), markers=("了",), level=2, core=True),
    _S("le_final", 5, "Sentence-final 了 — now it's different", "下雨了。/ 我饿了。/ 他不来了。",
       "Signal a change: something is now the case that wasn't before.",
       notes=_LE + "New situation or change of state (天黑了, 我明白了, 他不做工了 = "
             "he's stopped working). Also 吃饭了! (it's time). Identify: what has "
             "changed?",
       contrast=("le_verb",), markers=("了",), level=2, core=True),
    _S("le_le", 5, "Verb + 了 + … + 了 — so far, and still going",
       "我学了两年华语了。/ 我等了半个钟头了。",
       "Say how much has happened up to now, implying it continues or matters now.",
       notes=_LE + "Double 了 = up to now: 我吃了三碗了 (and might eat more) vs 我吃了"
             "三碗 (that's what I ate). 等了一个钟头 (finished waiting) vs 等了一个钟头了 "
             "(still waiting). This contrast is the point of the drill.",
       contrast=("le_verb",), markers=("了",), level=3),
    _S("le_quantity", 5, "Verb + 了 + amount — how much got done", "买了三本书 / 喝了两杯咖啡",
       "Say how much of something was done.",
       notes=_LE + "The amount is what makes a V了 sentence sound complete. Vary "
             "measure words.",
       markers=("了",), level=2),
    _S("le_negation", 5, "Negating 了: 没 + verb / 不……了", "我没吃。/ 我不吃了。",
       "Say something didn't happen, or that you've stopped or changed your mind.",
       notes=_LE + "Completed-action negation drops 了: 我没去 (NOT 我没去了); the exception is a length of time + 没 + verb + 了 (我三天没睡了 = haven't slept for three days). 不……了 = "
             "not any more / changed plan: 我不去了, 我不喝了 (I've had enough).",
       contrast=("le_verb",), markers=("没", "不"), level=2),
    _S("le_vs_mei", 5, "了 vs 没 — did it or didn't", "吃了 ↔ 没吃",
       "Hear and say whether something happened.",
       notes=_LE + "Minimal pairs heard aloud; questions 你吃了吗？/ 吃了没有？ answered "
             "吃了 / 还没 / 没吃.",
       contrast=("le_verb", "mei_neg"), markers=("了", "没"), level=2, kind="contrast"),
    _S("le_vs_guo", 5, "了 vs 过 — this time vs ever", "我去了槟城 ↔ 我去过槟城",
       "Tell 'did it (this occasion)' from 'have done it (at some time)'.",
       notes=_LE + "去了 = went (this time; may still be there); 去过 = have been "
             "(experience; came back). 我吃了榴莲 (just now) vs 我吃过榴莲 (I've had "
             "durian before).",
       contrast=("le_verb", "guo_exp"), markers=("了", "过"), level=2, core=True,
       kind="contrast", also_in=(30,)),
    _S("le_vs_zai", 5, "了 vs 在 — done vs in progress", "他吃了饭 ↔ 他在吃饭",
       "Tell a finished action from one happening right now.",
       notes=_LE,
       contrast=("le_verb", "zai_v"), markers=("了", "在"), level=2, kind="contrast"),
    _S("le_vs_zhe", 5, "了 vs 着 — the action vs the lasting state", "门开了 ↔ 门开着",
       "Tell 'it happened' from 'it stays that way'.",
       notes=_LE + "门开了 (the door opened - a change) vs 门开着 (the door is standing "
             "open). 他戴了帽子 (put a hat on) vs 他戴着帽子 (is wearing a hat).",
       contrast=("le_verb", "zhe_state"), markers=("了", "着"), level=3,
       kind="contrast", also_in=(30,)),

    # ------------------------------------------------------------------
    # 5B. 过
    # ------------------------------------------------------------------
    _S("guo_exp", 5, "Verb + 过 — have done before", "我去过怡保。",
       "Say you have (ever) done something.",
       notes="Experience at some time, not a specific occasion; often with 以前 or "
             "没. Questions: 你去过……吗？/ 有没有去过？",
       contrast=("le_verb",), markers=("过",), level=2, core=True),
    _S("mei_guo", 5, "没 + verb + 过 — have never", "我没吃过榴莲。",
       "Say you have never done something.",
       notes="Keep 过: 我没去过槟城 (have never been) vs 我没去 (didn't go, one "
             "occasion). 从来没……过 is the stronger 'never ever'.",
       contrast=("mei_neg", "conglai_mei"), markers=("过",), level=2),
    _S("guo_quantity", 5, "Verb + 过 + number of times", "我去过两次。/ 我看过三遍。",
       "Say how many times you've done something.",
       notes="过 + number + 次/遍; with a person: 我见过他一次.",
       markers=("过",), level=3),
    _S("guo_vs_bare", 5, "With or without 过", "我去过日本 ↔ 我以前住槟城",
       "Know when experience needs 过, and when a past habit or plan doesn't.",
       notes="过 marks experience (have been). Without it: 我去日本 = I'm going; 我以前"
             "住在槟城 = I used to live (以前 does the work, no marker needed).",
       contrast=("guo_exp",), level=3, kind="contrast"),

    # ------------------------------------------------------------------
    # 5C. Progressive / continuous
    # ------------------------------------------------------------------
    _S("zai_v", 5, "在 + verb — in the middle of doing", "他在吃饭。",
       "Say an action is going on, now or at the time.",
       notes="在 here is before a verb, not a place. Also past: 我打电话给你的时候，你在"
             "做什么？ Negative: 没在…… (他没在睡觉).",
       markers=("在",), level=1, core=True),
    _S("zhengzai_v", 5, "正在……(呢) — right in the middle of", "我正在做工(呢)。",
       "Stress that an action is happening at that very moment.",
       notes="正在 = right now / right then; final 呢 adds 'I'm busy, you see'. "
             "Unlike 在, it doesn't combine with 一直 or 常常 (他一直在等你, NOT 他一直"
             "正在等你).",
       contrast=("zai_v",), markers=("正在",), level=2, core=True),
    _S("zheng_v", 5, "正 + verb — just as, right then", "我正要出门。/ 他正吃饭呢。",
       "Say something was happening, or about to, at exactly that moment.",
       notes="正 usually needs 呢 or a following clause: 我正要打电话给你，你就来了 / "
             "我正想说.",
       markers=("正",), level=3),
    _S("zhe_state", 5, "Verb + 着 — a lasting state", "门开着。/ 他穿着恤衫。/ 墙上挂着一张画。",
       "Describe a state that continues: standing open, wearing, hanging, sitting.",
       notes="The resulting state, not the action: 穿着 = wearing (not putting on). "
             "Place + V着 + thing describes scenes (桌上放着一本书). V着 + V (manner) "
             "is a later structure.",
       contrast=("zai_v",), markers=("着",), level=3, core=True),
    _S("zai_vs_zhengzai", 5, "在 vs 正在", "他在做工 ↔ 他正在开会",
       "Hear 'is doing' against 'is right in the middle of doing'.",
       notes="Often interchangeable; 正在 adds 'at this very moment'. Only 在 goes "
             "with 一直 / 常常 / 还 for ongoing or repeated activity (他一直在学, 他常常在"
             "巴刹买菜). Identify tasks: which one fits, or does either work?",
       contrast=("zai_v", "zhengzai_v"), markers=("在",), level=2, kind="contrast",
       also_in=(30,)),
    _S("zai_vs_zhe", 5, "在 / 正在 vs 着 — doing vs being in a state",
       "他在穿衣服 ↔ 他穿着新衣服",
       "Tell an action in progress from the state it leaves.",
       notes="在 + action (putting on, opening, hanging up) vs V着 (wearing, standing "
             "open, hanging).",
       contrast=("zai_v", "zhe_state"), markers=("在", "着"), level=3, core=True,
       kind="contrast", also_in=(30,)),

    # ------------------------------------------------------------------
    # 5D. Imminent events
    # ------------------------------------------------------------------
    _S("yao_le", 5, "要……了 — about to", "要下雨了。/ 巴士要来了。",
       "Say something is about to happen.",
       notes="Imminent change; the final 了 is needed.",
       contrast=("kuai_le",), markers=("要",), level=2),
    _S("kuai_le", 5, "快……了 — nearly", "快到了。/ 快十点了。",
       "Say something is very close to happening, or a point is nearly reached.",
       notes="快 + verb / adjective / number + 了: 快好了, 快十二点了, 快放工了.",
       markers=("快",), level=2),
    _S("kuaiyao_le", 5, "快要……了 — any moment now", "快要下雨了。",
       "Say something is about to happen, very soon.",
       notes="Combines 快 and 要. Cannot take a specific time word (that needs 就要).",
       contrast=("jiuyao_le",), markers=("快要",), level=2),
    _S("jiuyao_le", 5, "就要……了 — about to (at a set time)", "我们明天就要走了。",
       "Say something is about to happen, often giving the time.",
       notes="就要 can take a time word (下个礼拜就要考试了); 快要 cannot.",
       contrast=("kuaiyao_le",), markers=("就要",), level=3),
    _S("mashang_le", 5, "马上(就)……了 — in a moment", "我马上到了。/ 马上就好了。",
       "Say something will happen in just a moment.",
       notes="Very common in Malaysia: 马上到 / 马上来 (on my way). 马上 on its own "
             "(immediately) is a separate structure.",
       markers=("马上",), level=2),
    _S("jiuyao_vs_kuaiyao", 5, "就要……了 vs 快要……了", "明天就要走了 ↔ 快要走了",
       "Only 就要 can take a time word; 快要 just means very soon.",
       notes="Pair drill: sentences with a time word need 就要; without one either "
             "works, 快要 feeling more immediate.",
       contrast=("jiuyao_le", "kuaiyao_le"), markers=("就要", "快要"), level=3,
       kind="contrast"),

    # ------------------------------------------------------------------
    # 5E. 已经 / 还 / 又 / 再
    # ------------------------------------------------------------------
    _S("yijing_le", 5, "已经……了 — already", "他已经走了。/ 已经十点了。",
       "Say something has already happened, or a point has already been reached.",
       notes="已经 + verb or time + 了.",
       contrast=("hai_mei",), markers=("已经",), level=2),
    _S("hai_mei", 5, "还没(有)……(呢) — not yet", "我还没吃(呢)。",
       "Say something hasn't happened yet but is expected to.",
       notes="No 了 (NOT 还没吃了); 呢 optional and natural. Short answer to 吃了吗？: "
             "还没. Covers 还没有.",
       contrast=("yijing_le",), markers=("还没",), level=2),
    _S("yijing_hai", 5, "已经……了，还…… — already… yet still…", "已经十点了，他还没起床。",
       "Contrast what has already happened with what still hasn't (or still is).",
       notes="Often a complaint or surprise: 已经吃了三碗了，还饿？",
       markers=("已经",), level=3),
    _S("hai_still", 5, "还 — still", "他还在做工。/ 你还饿吗？",
       "Say something is still the case or still going on.",
       notes="还 + verb / 在 / adjective. (还 = also, and 还是 = or / had better, are "
             "other structures.)",
       markers=("还",), level=2, also_in=(16,)),
    _S("you_again", 5, "又 — again (it happened again)", "他又迟到了。",
       "Say something has happened again — often with annoyance.",
       notes="又 for repetition that has happened, or is certain/regular (明天又是"
             "拜一). Usually with 了.",
       contrast=("zai_again",), markers=("又",), level=2, also_in=(16,)),
    _S("zai_again", 5, "再 — again (next time) / then", "明天再来。/ 再说一遍。",
       "Say something will be done again, or not until later.",
       notes="再 for repetition not yet done (请再说一遍) and for 'then / not until' "
             "(吃了饭再去).",
       contrast=("you_again",), markers=("再",), level=2, also_in=(6, 16)),

    # ------------------------------------------------------------------
    # 6. Time & temporal relationships
    # ------------------------------------------------------------------
    _S("dur_basic", 6, "Duration after the verb", "我等了十分钟。/ 他睡了八个钟头。",
       "Say how long something lasted — the length of time goes after the verb.",
       notes="Points in time go before the verb; lengths of time go after (住了两年, "
             "等了一个钟头). Negated duration comes before: 我两天没睡. Malaysian 钟头 "
             "for hours is common.",
       level=2, core=True, also_in=(7,)),
    _S("time_vs_duration", 6, "Point in time vs length of time", "我八点等你 ↔ 我等了八分钟",
       "Hear whether a time word says when or how long — and put it in the right place.",
       notes="Pair drill on position: when = before the verb; how long = after it.",
       contrast=("time_before_verb", "dur_basic"), level=2, core=True, kind="contrast"),
    _S("de_shihou", 6, "……的时候 — when, while", "我吃饭的时候 / 小时候",
       "Say when something happens by linking it to another event.",
       notes="Clause + 的时候 comes first: 我到的时候，他已经走了. Covers 当……的时候 "
             "(same meaning, more formal).",
       markers=("时候",), level=2, also_in=(20, 27, 35)),
    _S("yiqian", 6, "……以前 / 之前 — before", "吃饭以前 / 三天之前 / 我以前……",
       "Say something happens before something else, or used to be so.",
       notes="Clause or time + 以前/之前 (睡觉以前, 两年以前). Alone at the start, 以前 "
             "= in the past (我以前住在槟城). 之前 is interchangeable, a little more "
             "specific.",
       contrast=("yihou",), markers=("以前", "之前"), level=2, also_in=(27,)),
    _S("yihou", 6, "……以后 / 之后 — after", "下班以后 / 三天之后 / 以后",
       "Say something happens after something else, or from now on.",
       notes="Clause or time + 以后/之后; with 了: 吃了饭以后. Alone, 以后 = in "
             "future / from now on (以后别迟到).",
       contrast=("yiqian",), markers=("以后", "之后"), level=2, also_in=(27,)),
    _S("cong_dao", 6, "从……到…… — from … to …", "从八点到五点 / 从怡保到槟城",
       "Give the start and end of a period or a journey.",
       notes="Time or place; often with 都 or a following verb (从拜一到拜五都要做工).",
       markers=("从",), level=2, also_in=(21,)),
    _S("cong_kaishi", 6, "从……开始 — starting from", "从明天开始……",
       "Say when something begins and carries on.",
       notes="New rules and changes: 从明天开始我不喝咖啡了. Also 从……起.",
       markers=("开始", "起"), level=3),
    _S("dao_weizhi", 6, "到……为止 — up until", "到现在为止 / 到拜五为止",
       "Say up to what point something holds.",
       notes="到现在为止还没有消息 / 优惠到拜五为止.",
       markers=("为止",), level=4),
    _S("yizhi", 6, "一直 — all along, continuously", "一直 + 动词",
       "Say something has kept going, or kept (not) happening.",
       notes="我一直在等你 / 他一直不来 / 一直走 (go straight on).",
       markers=("一直",), level=2),
    _S("gang", 6, "刚 / 刚刚 — just (did)", "我刚到。/ 他刚刚走。",
       "Say something happened only a moment ago.",
       notes="Adverb before the verb; 刚刚 is the same and very common in Malaysia. "
             "Usually no 了 with 刚. Can mean 'only just' (我刚来一个礼拜).",
       contrast=("gangcai",), markers=("刚",), level=2),
    _S("gangcai", 6, "刚才 — just now", "刚才你说什么？",
       "Refer to a moment ago as a time: just now.",
       notes="A time word: can start the sentence, take 了 and be negated (刚才我没听"
             "到).",
       contrast=("gang",), markers=("刚才",), level=2),
    _S("mashang", 6, "马上 — right away", "马上 + 动词",
       "Say something happens immediately.",
       notes="我马上来 / 马上到 (on my way). The imminent 马上……了 is a separate "
             "structure.",
       markers=("马上",), level=1),
    _S("xian", 6, "先 — first", "先 + 动词",
       "Say what you'll do first.",
       notes="你先走 / 我先吃. Usually followed by 再 or 然后.",
       markers=("先",), level=2),
    _S("xian_zai", 6, "先……再…… — first … then …", "先吃饭，再去看戏。",
       "Put two actions in order: first this, then that.",
       notes="再 here = then / not until (future or instructions).",
       contrast=("ranhou",), markers=("先",), level=2, also_in=(15, 27)),
    _S("ranhou", 6, "然后 — and then", "……，然后……",
       "Link events in sequence.",
       notes="Past or future (我们先吃饭，然后去巴刹). Very common as a filler in "
             "Malaysian speech. 再 is only future/instructions.",
       contrast=("xian_zai",), markers=("然后",), level=2, also_in=(15,)),
    _S("zuihou", 6, "最后 — finally, in the end", "最后……",
       "Say what happened (or will happen) last.",
       notes="最后我们没去 / 最后一天 / 最后他还是来了.",
       markers=("最后",), level=2, also_in=(15,)),
    _S("tongshi", 6, "同时 — at the same time", "……的同时 / 同时……",
       "Say two things happen at once.",
       notes="我们同时到的 / 做工的同时也在学华语.",
       markers=("同时",), level=4),

    # ------------------------------------------------------------------
    # 7. Duration, frequency & repetition
    # ------------------------------------------------------------------
    _S("dur_verb_obj", 7, "Verb + object + verb + duration", "他学华语学了两年。",
       "Say how long you did something when the verb has an object.",
       notes="Repeat the verb: 看书看了两个钟头 / 等巴士等了半个钟头. Alternative: "
             "V + duration + (的) + O.",
       contrast=("dur_before_obj",), markers=("了",), level=3),
    _S("dur_before_obj", 7, "Verb + duration + (的) + object", "我看了两个钟头(的)书。",
       "Say how long you did an activity — the time sits between verb and object.",
       notes="With ordinary nouns. With a pronoun object the time follows it (等了你"
             "半天).",
       markers=("了",), level=3),
    _S("ci_times", 7, "次 — number of times", "去过三次 / 一个礼拜两次 / 几次",
       "Say how many times something happens or happened.",
       notes="V + (过/了) + number + 次; frequency: 一天三次. Questions: 去过几次？",
       contrast=("bian_times",), markers=("次",), level=2, core=True),
    _S("bian_times", 7, "遍 — times through, start to finish", "再说一遍 / 看了两遍",
       "Count complete run-throughs: say it again, read it twice.",
       notes="遍 = the whole thing from beginning to end (请再说一遍).",
       contrast=("ci_times",), markers=("遍",), level=2),
    _S("ci_vs_bian", 7, "次 vs 遍", "去过两次 ↔ 看了两遍",
       "Choose between counting occasions and complete run-throughs.",
       notes="Pair drill: 次 counts occasions (去槟城三次); 遍 counts full "
             "repetitions of something with a beginning and end (看了三遍).",
       contrast=("ci_times", "bian_times"), markers=("次", "遍"), level=3, core=True,
       kind="contrast", also_in=(30,)),
    _S("mei_every", 7, "每 — every", "每天 / 每个人 / 每个礼拜",
       "Say every day, every person, every week.",
       notes="每 + (measure word) + noun, usually with 都 after (每天都……).",
       markers=("每",), level=2),
    _S("meici_dou", 7, "每次……都…… — every time", "每次去巴刹都买榴莲。",
       "Say something happens every single time.",
       notes="每次 + event + 都 + result.",
       markers=("每次",), level=3),
    _S("v_yixia", 7, "Verb + 一下 — do briefly, have a go", "看一下 / 等一下 / 试一下",
       "Soften a request, or say you'll do something quickly.",
       notes="Very common in Malaysia (等一下, 我看一下, 你帮我一下).",
       contrast=("v_yihui",), markers=("一下",), level=1),
    _S("v_yihui", 7, "Verb + 一会 / 一阵子 — for a while", "休息一会 / 等了一阵子",
       "Say something lasted a little while.",
       notes="The syllabus' 一会儿, without 儿. 一会 is mainland usage; Malaysians "
             "mostly say 一下, 一阵子 or 一下子. Recognise 一会, produce 一阵子 / 一下.",
       markers=("一会", "一阵"), level=3),
    _S("yixia_vs_yihui", 7, "一下 vs 一会 — a quick go vs a stretch of time",
       "看一下 ↔ 看了一会",
       "Tell a quick, light action from a length of time.",
       notes="一下 counts the action (brief, softened); 一会/一阵子 measures time.",
       contrast=("v_yixia", "v_yihui"), markers=("一下", "一会", "一阵"), level=3,
       kind="contrast", also_in=(30,)),
    _S("redup_verb", 7, "Verb doubled — AA / A一A", "看看 / 试试 / 想想 / 等等",
       "Double a verb to make it casual: have a look, give it a try.",
       notes="One-syllable verbs: AA or A一A (看一看); done: AA + 了 → 看了看. "
             "Softens requests (你尝尝).",
       level=2, core=True, also_in=(35,)),
    _S("redup_abab", 7, "Two-syllable verbs doubled — ABAB", "休息休息 / 考虑考虑 / 介绍介绍",
       "Double a two-syllable verb to make it casual.",
       notes="ABAB (not AABB, which is for adjectives).",
       level=3, also_in=(35,)),
    _S("redup_adj", 7, "Adjective doubled", "好好 / 慢慢 / 早早 / 高高兴兴",
       "Double an adjective for vividness, or to say how to do something.",
       notes="AA(地) + verb: 慢慢吃, 好好休息, 早早起床; AABB for two-syllable "
             "adjectives: 高高兴兴, 干干净净.",
       level=3, also_in=(14, 35)),

    # ------------------------------------------------------------------
    # 8. Modal verbs
    # ------------------------------------------------------------------
    _S("xiang_want", 8, "想 — want to, would like to", "想 + 动词",
       "Say what you'd like or intend to do.",
       notes="Softer than 要. 想 also means 'think' (我想他不来) and 'miss' (我想你) - "
             "identify tasks can include these. Negative 不想.",
       contrast=("yao_want",), markers=("想",), level=1, core=True),
    _S("yao_want", 8, "要 — want / need to / going to", "要 + 动词 / 要 + 东西",
       "Say what you want, need or are going to do — firmly.",
       notes="我要咖啡 (want / ordering), 我要做工 (have to / going to), 明天要下雨 "
             "(will). For 'don't want to' use 不想 (不要 = don't!). 要……了 = about to "
             "is a separate structure.",
       contrast=("xiang_want",), markers=("要",), level=1, core=True),
    _S("xiangyao", 8, "想要 — would like (to have)", "想要 + 东西 / 动词",
       "Say what you'd like to have or do.",
       notes="我想要一杯冰水. Between 想 (soft) and 要 (firm).",
       markers=("想要",), level=2),
    _S("hui_can", 8, "会 — know how to / will probably", "会 + 动词",
       "Say you know how to do something, or that it's likely to happen.",
       notes="Learned skills (我会游泳, 他会讲福建话); likelihood (明天会下雨, 他不会来"
             "的).",
       contrast=("neng", "keyi"), markers=("会",), level=1, core=True),
    _S("neng", 8, "能 — can (able / circumstances allow)", "能 + 动词",
       "Say you are able to, or that circumstances allow it.",
       notes="Ability or circumstance (我今天不能来, 你能帮我吗？); capacity (他能吃三"
             "碗).",
       contrast=("hui_can", "keyi"), markers=("能",), level=1, core=True),
    _S("keyi", 8, "可以 — may, can (allowed)", "可以 + 动词",
       "Ask for or give permission, or say something is an option.",
       notes="Permission (这里可以抽烟吗？); option (你可以搭巴士). Refusing: 不可以 / "
             "不行.",
       contrast=("hui_can", "neng"), markers=("可以",), level=1, core=True),
    _S("hui_neng_keyi", 8, "会 vs 能 vs 可以", "我会游泳 · 今天不能游 · 这里可以游吗？",
       "Choose between knowing how, being able, and being allowed.",
       notes="Pair drill across all three: skill learned (会), ability or "
             "circumstance (能), permission or option (可以).",
       contrast=("hui_can", "neng", "keyi"), markers=("会", "能", "可以"), level=2,
       core=True, kind="contrast", also_in=(30,)),
    _S("yinggai", 8, "应该 — should / probably", "应该 + 动词",
       "Say what someone should do, or what is probably true.",
       notes="Advice (你应该多喝水); expectation (他应该到了).",
       markers=("应该",), level=2),
    _S("dei_must", 8, "得 (děi) — have to", "得 + 动词",
       "Say you have to do something (spoken).",
       notes="Pronounced děi; spoken. Negative is 不用 (not 不得): 我得走了 / 你不用来. "
             "Use contexts where 得 is clearly děi.",
       markers=("得",), level=3),
    _S("bixu", 8, "必须 — must", "必须 + 动词",
       "Say something is strictly necessary.",
       notes="Stronger and more formal than 得; negative 不必 / 不用.",
       markers=("必须",), level=3),
    _S("xuyao", 8, "需要 — need", "需要 + 东西 / 动词",
       "Say what is needed.",
       notes="你需要什么？/ 不需要 / 需要多久？",
       markers=("需要",), level=2),
    _S("yuanyi", 8, "愿意 — be willing to", "愿意 + 动词",
       "Say someone is willing to do something.",
       notes="你愿意帮我吗？/ 他不愿意去.",
       contrast=("ken",), markers=("愿意",), level=3),
    _S("gan", 8, "敢 — dare", "敢 + 动词",
       "Say someone dares (or doesn't dare) to do something.",
       notes="我不敢吃榴莲 / 你敢吗？",
       markers=("敢",), level=2),
    _S("ken", 8, "肯 — be willing, agree to", "肯 + 动词",
       "Say whether someone agrees to do something — often they won't.",
       notes="Mostly negative: 他不肯来 / 他怎么也不肯说.",
       contrast=("yuanyi",), markers=("肯",), level=3),
    _S("keneng", 8, "可能 — maybe, might", "可能 + 动词 / 可能……",
       "Say something might be so.",
       notes="Before the verb or the sentence: 他可能不来 / 可能会下雨.",
       markers=("可能",), level=2),
    _S("yiding", 8, "一定 — definitely / must", "一定 + 动词",
       "Say something is certain, or insist it must be done.",
       notes="他一定知道 (surely); 你一定要来 (you must come!). 不一定 = not "
             "necessarily.",
       markers=("一定",), level=2),
    _S("yinggai_yiding_keneng", 8, "应该 vs 一定 vs 可能", "他应该到了 · 他一定到了 · 他可能到了",
       "Say how sure you are: probably, certainly, maybe.",
       notes="Pair drill on certainty: 一定 (sure) > 应该 (should be / expected) > 可能 "
             "(might).",
       contrast=("yinggai", "yiding", "keneng"), markers=("应该", "一定", "可能"),
       level=3, kind="contrast"),
]

LISTED = {
    4: [
        ("General measure word 个", "mw_ge"),
        ("Common measure words: 本、张、件、杯、瓶、只、条、辆、台、家、间、位、名、次、遍", "mw_common"),
        ("Number + measure word + noun", "num_mw_noun"),
        ("这/那 + measure word + noun", "zhe_na_mw"),
        ("几 + measure word", "ji_howmany"),
        ("多少 + measure word", "duoshao"),
        ("一点儿", "yidian"),
        ("一些", "yixie"),
        ("好几个", "haoji"),
        ("几个", "jige"),
        ("多 + measure word", "num_duo"),
        ("数量 + 的 + noun", "quantity_de_noun"),
        ("一共…… — altogether", "yigong"),
        ("大约 / 大概…… — approximately", "dayue"),
        ("差不多…… — approximately/almost", "chabuduo"),
        ("左右 — approximately", "zuoyou"),
        ("多 / 少 + adjective", "duo_shao_verb"),
        ("比较 + adjective", "bijiao_adj"),
        ("最 + adjective", "zui_adj"),
    ],
    5: [
        ("Verb + 了 — completed/relevant event", "le_verb"),
        ("Sentence-final 了 — change of state", "le_final"),
        ("Verb + 了 + object + 了", "le_le"),
        ("了 with duration", "le_le"),
        ("了 with quantity", "le_quantity"),
        ("Negative forms involving 了", "le_negation"),
        ("了 vs 没", "le_vs_mei"),
        ("了 vs 过", "le_vs_guo"),
        ("了 vs 在", "le_vs_zai"),
        ("了 vs 着", "le_vs_zhe"),
        ("V + 过 — past experience", "guo_exp"),
        ("没 + V + 过", "mei_guo"),
        ("V + 过 + quantity", "guo_quantity"),
        ("过 vs 了", "le_vs_guo"),
        ("过 vs experience without explicit marker", "guo_vs_bare"),
        ("在 + V", "zai_v"),
        ("正在 + V", "zhengzai_v"),
        ("正 + V", "zheng_v"),
        ("正在……呢", "zhengzai_v"),
        ("V + 着", "zhe_state"),
        ("着 — continuing state", "zhe_state"),
        ("在 vs 正在", "zai_vs_zhengzai"),
        ("在/正在 vs 着", "zai_vs_zhe"),
        ("要……了", "yao_le"),
        ("快……了", "kuai_le"),
        ("快要……了", "kuaiyao_le"),
        ("就要……了", "jiuyao_le"),
        ("马上……了", "mashang_le"),
        ("就要……了 vs 快要……了", "jiuyao_vs_kuaiyao"),
        ("已经……了", "yijing_le"),
        ("还没……", "hai_mei"),
        ("还没有……", "hai_mei"),
        ("已经……了，还……", "yijing_hai"),
        ("还…… — still", "hai_still"),
        ("又…… — again/already", "you_again"),
        ("再…… — again/in future", "zai_again"),
    ],
    6: [
        ("Time phrase + sentence", "time_before_verb"),
        ("Time duration", "dur_basic"),
        ("Point in time vs duration", "time_vs_duration"),
        ("……的时候 — when/while", "de_shihou"),
        ("……以前 — before", "yiqian"),
        ("……以后 — after", "yihou"),
        ("……之前 — before", "yiqian"),
        ("……之后 — after", "yihou"),
        ("……以前/以后 + noun/verb", "yiqian"),
        ("从……到…… — from…to…", "cong_dao"),
        ("从……开始 — from/beginning", "cong_kaishi"),
        ("到……为止 — until", "dao_weizhi"),
        ("一直…… — continuously", "yizhi"),
        ("刚…… — just", "gang"),
        ("刚才…… — just now", "gangcai"),
        ("刚刚…… — just", "gang"),
        ("马上…… — immediately", "mashang"),
        ("先…… — first", "xian"),
        ("再…… — then/again", "xian_zai"),
        ("然后…… — then", "ranhou"),
        ("最后…… — finally", "zuihou"),
        ("同时…… — simultaneously", "tongshi"),
        ("当……的时候…… — when…", "de_shihou"),
    ],
    7: [
        ("V + 了 + duration", "dur_basic"),
        ("V + O + V + duration", "dur_verb_obj"),
        ("V + duration + O", "dur_before_obj"),
        ("Duration + 的 + noun", "quantity_de_noun"),
        ("次 — number of occurrences", "ci_times"),
        ("遍 — number of complete repetitions", "bian_times"),
        ("次 vs 遍", "ci_vs_bian"),
        ("每…… — every", "mei_every"),
        ("每次……都……", "meici_dou"),
        ("一共……次", "yigong"),
        ("……几次", "ci_times"),
        ("V + 一下", "v_yixia"),
        ("V + 一会儿", "v_yihui"),
        ("Verb reduplication: 看看、试试、想想", "redup_verb"),
        ("One-syllable reduplication: AA", "redup_verb"),
        ("Two-syllable reduplication: ABAB", "redup_abab"),
        ("Adjective reduplication: 好好、慢慢、早早", "redup_adj"),
        ("一下 vs 一会儿", "yixia_vs_yihui"),
    ],
    8: [
        ("想 — want/intend", "xiang_want"),
        ("要 — want/need/about to", "yao_want"),
        ("想要 — want", "xiangyao"),
        ("会 — know how to / likely to", "hui_can"),
        ("能 — ability/circumstances", "neng"),
        ("可以 — permission/possibility", "keyi"),
        ("会 vs 能 vs 可以", "hui_neng_keyi"),
        ("应该 — should/probably", "yinggai"),
        ("得 — must/have to", "dei_must"),
        ("必须 — must", "bixu"),
        ("需要 — need", "xuyao"),
        ("愿意 — be willing", "yuanyi"),
        ("敢 — dare", "gan"),
        ("肯 — be willing", "ken"),
        ("可能 — may/possibly", "keneng"),
        ("一定 — certainly/must", "yiding"),
        ("应该 vs 一定 vs 可能", "yinggai_yiding_keneng"),
    ],
}
