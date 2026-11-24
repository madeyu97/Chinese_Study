# src/hsk_grammar_2.py
"""HSK 2's grammar points: which structures teach them, and the cards for
structures first met at HSK 2. Merged into hsk_grammar's MAP / LEXICAL /
LEARN (see there)."""

MAP = {
    "g2-01": ("loc_words_1", "loc_words_2"),                    # —面
    "g2-02": ("loc_words_2",),                                  # 左、右
    "g2-03": ("redup_verb", "redup_abab"),                      # 看看、说一说
    "g2-04": ("keneng",),                                       # 可能
    "g2-05": ("lihe_verbs",),                                   # 帮忙、游泳 …
    "g2-06": ("weishenme",),                                    # 为什么
    "g2-07": (),                                                # 自己
    "g2-08": ("zheme_name", "mei_every"),                       # 那么 这么 这样 每
    "g2-09": ("redup_adj",),                                    # 高高的、高高兴兴
    "g2-10": ("numbers", "num_duo"),                            # 万、好多、多
    "g2-11": ("mw_common",),                                    # 条 位 间 名
    "g2-12": ("mw_common",),                                    # 包
    "g2-13": ("ci_times",),                                     # 次
    "g2-14": ("duo_a", "hao_a", "zui_adj"),                     # 多 好 最
    "g2-15": ("gen_with",),                                     # 一起
    "g2-16": ("hai_still", "hai_mei", "yijing_le", "kuai_le", "kuaiyao_le", "zheng_v"),
    "g2-17": ("adverb_verb",),                                  # 常、经常
    "g2-18": ("bie",),                                          # 别
    "g2-19": ("xian_zai", "yi_jiu"),                            # 再2、就1
    "g2-20": ("dou_meanings", "jiu_emphatic", "haishi_better"),  # 都2 就2 还是1
    "g2-21": ("cong_dao", "cong_from"),                         # 从 (time, place)
    "g2-22": ("wang_toward",),                                  # 往
    "g2-23": ("cong_from",),                                    # 从 (path)
    "g2-24": ("gei_prep",),                                     # 给
    "g2-25": ("bi_adj",),                                       # 比
    "g2-26": ("gen_with",),                                     # 跟 (with)
    "g2-27": ("yinwei_suoyi",),                                 # 因为 (prep)
    "g2-28": ("he_and",),                                       # 跟 (and)
    "g2-29": ("danshi", "suiran_danshi", "haishi_or", "yinwei_suoyi", "suoyi"),
    "g2-30": ("deg_de", "de_manner", "de_de_de"),               # 得、地
    "g2-31": ("guo_exp", "mei_guo"),                            # 过
    "g2-32": ("zhe_state",),                                    # 着
    "g2-33": ("a_particle", "de_final", "ba_particle"),         # 呢 吧 的 啊
    "g2-34": ("res_dong", "dir_lai_qu", "deg_de"),              # 听懂、回去、跑得很快
    "g2-35": ("de_nominal",),                                   # 老师的、白色的
    "g2-36": ("serial_verbs", "qu_place_v", "lai_place_v"),
    "g2-37": ("jianyu_causative",),                             # 请他来、叫朋友帮忙
    "g2-38": (),
    "g2-39": (),
    "g2-40": (),
    "g2-41": ("shenmede",),                                     # 什么的
    "g2-42": ("haishi_better",),                                # 还是……吧
    "g2-43": ("yao_le", "kuaiyao_le", "jiuyao_le"),             # 要/快要/就要……了
    "g2-44": ("dou_meanings",),                                 # 都……了
    "g2-45": ("topic_comment",),                                # 那本书我看过了
    "g2-46": ("noun_predicate",),                               # 王老师上海人
    "g2-47": ("rel_v_de", "rel_person"),                        # 唱歌的女孩
    "g2-48": ("res_cuo", "res_dong", "res_hao", "res_wan", "res_negation", "res_le"),
    "g2-49": ("dir_lai_qu", "dir_shang", "dir_xia"),
    "g2-50": ("dir_jin", "dir_chu", "dir_hui", "dir_guo", "dir_simple"),
    "g2-51": ("dir_compound",),
    "g2-52": ("deg_de", "deg_de_hen"),
    "g2-53": ("dur_basic", "le_le", "dur_verb_obj"),
    "g2-54": ("bi_quantity",),
    "g2-55": ("double_subject", "topic_comment"),
    "g2-56": ("haishi_or",),
    "g2-57": ("bie",),
    "g2-58": ("de_nominal",),
    "g2-59": ("you_reach",),
    "g2-60": ("zhe_scene",),
    "g2-61": ("bi_adj",),
    "g2-62": ("bi_quantity",),
    "g2-63": ("you_reach", "meiyou_name", "bi_vs_meiyou"),
    "g2-64": ("bi_verb",),
    "g2-65": ("shi_de", "shi_de_time", "shi_de_place", "shi_de_manner", "shi_de_agent",
              "shi_de_question", "shi_de_neg", "shi_de_vs_le"),
    "g2-66": ("jianyu_causative",),
    "g2-67": ("v_gei",),
    "g2-68": ("haishi_or",),
    "g2-69": ("suiran_danshi",),
    "g2-70": ("yinwei_suoyi",),
    "g2-71": ("yi_jiu",),
    "g2-72": ("zhe_state", "zai_vs_zhe"),
    "g2-73": ("zheng_v",),
    "g2-74": ("guo_exp", "le_vs_guo"),
    "g2-75": ("di_ordinal",),
    "g2-76": ("jige",),
    "g2-77": ("num_duo",),
    "g2-78": ("num_duo",),
}

LEXICAL = {
    "g2-07": "自己 (oneself) — vocabulary: 你自己去 (go by yourself).",
    "g2-38": "Noun phrases as a category — every drill uses them.",
    "g2-39": "Verb phrases as a category — every drill uses them.",
    "g2-40": "Adjective phrases as a category — every drill uses them.",
}

LEARN = {
    "loc_words_2": (
        "Position words: 旁边 (beside), 中间 (between), 左边 / 右边 (left / right), 附近 "
        "(nearby), 对面 (opposite). They follow the noun: 银行旁边 (next to the bank).",
        "English 'next to the bank' puts the position first; Chinese puts it last."),
    "redup_verb": (
        "Doubling a verb makes it brief and casual: 看看 (have a look), 试试 (give it a "
        "try), 说一说 (say a bit). 看了看 = took a quick look.",
        "Only for actions you choose to do: 喜欢喜欢 ✗, 是是 ✗."),
    "redup_abab": (
        "Two-syllable verbs double as ABAB: 休息休息 (rest a bit), 介绍介绍 (introduce "
        "briefly).",
        "Not AABB — that's for adjectives: 休休息息 ✗."),
    "keneng": (
        "可能 = maybe, probably: 他可能不来 (he might not come). It goes before the verb, or "
        "at the start: 可能他忘了.",
        "As a noun 可能 is 'possibility' (有可能), but don't put it after the verb."),
    "weishenme": (
        "为什么 = why, before the verb: 你为什么不去？ Answer with 因为 (because).",
        "Not at the end like English 'why not?': 你不去为什么 ✗."),
    "zheme_name": (
        "这么 / 那么 + adjective = so …: 这么贵！ (so expensive!). 这样 / 那样 + verb = like "
        "this / that: 这样写 (write it like this).",
        "这么 is near you or now; 那么 is about there or what someone said."),
    "mei_every": (
        "每 + measure word + noun = every: 每天 (every day), 每个人 (everyone). It usually "
        "takes 都 before the verb: 每天都下雨.",
        "每 still needs a measure word: 每人 ✗ in speech → 每个人 (天 and 年 count "
        "as their own)."),
    "redup_adj": (
        "Doubled adjectives are vivid: 高高的 (nice and tall), 慢慢地走 (walk slowly), "
        "高高兴兴 (happily).",
        "No 很 with them: 很高高的 ✗."),
    "num_duo": (
        "多 after a round number = more than: 二十多个人 (20-odd people). With one-digit "
        "numbers it goes after the measure word: 一个多钟头 (over an hour), 三年多.",
        "二十多 = 21–29; 两个多 = between two and three."),
    "ci_times": (
        "次 counts times, after the verb: 去过三次 (been three times), 一个星期两次 (twice a "
        "week).",
        "The count follows the verb, not before it: 三次去 ✗."),
    "duo_a": (
        "多 + adjective + 啊 = how …!: 多漂亮啊! (how beautiful!).",
        "As a question 多 + adjective asks 'how … ?': 多高？ — tone and 啊 decide."),
    "hao_a": (
        "好 + adjective (+ 啊) = so …: 好热啊! (so hot!), 好累 (so tired). Very common in "
        "Malaysian speech.",
        "Here 好 isn't 'good' — it's just 'so'."),
    "zui_adj": (
        "最 + adjective or verb = most: 最好 (the best), 最喜欢 (like most).",
        "最 alone is enough — no 很 after it: 最很好 ✗."),
    "hai_still": (
        "还 = still: 他还在做工 (he's still working), 你还饿吗？ (are you still hungry?).",
        "'Not yet' is 还没 + verb, not 还不."),
    "hai_mei": (
        "还没 + verb (+ 呢) = not yet: 我还没吃(呢) (I haven't eaten yet).",
        "No 了: 还没吃了 ✗."),
    "yijing_le": (
        "已经 + verb + 了 = already: 他已经走了 (he's already gone). Also with times: 已经十点了.",
        "Keep the 了 at the end."),
    "kuai_le": (
        "快 + verb / time + 了 = nearly, about to: 快到了 (almost there), 快十点了.",
        "The 了 is needed: 快到 alone sounds unfinished."),
    "kuaiyao_le": (
        "快要 + verb + 了 = about to: 快要下雨了 (it's about to rain).",
        "No time word before it — 明天快要走了 ✗ → 明天就要走了."),
    "zheng_v": (
        "正 + verb (+ 呢) = right at that moment: 我正要出门 (I was just about to go out), "
        "他正吃着饭呢.",
        "正 is about the exact moment; 在 is just 'in progress'."),
    "bie": (
        "别 + verb = don't: 别走 (don't go), 别忘了 (don't forget). Shorter and more "
        "direct than 不要.",
        "Not for 'don't want': that's 不要 / 不想."),
    "xian_zai": (
        "先 … 再 … = first …, then …: 先吃饭，再去看戏 (eat first, then go to the show).",
        "再 here is 'then (later)', not 'again'."),
    "yi_jiu": (
        "一 + A + 就 + B = as soon as A, B: 我一到家就睡觉 (I sleep as soon as I get home).",
        "Both 一 and 就 go before verbs, after the subjects."),
    "dou_meanings": (
        "都 = all (我们都去); with 连 = even (连他都知道); and 都 … 了 = already, so late: 都"
        "十点了! (it's already ten!).",
        "In 都…了 the 都 is a complaint about lateness, not 'all'."),
    "jiu_emphatic": (
        "就 stresses 'exactly / right': 就是他! (it's him!), 车站就在那里 (the station is "
        "right there).",
        "Stress 就 when you say it; it isn't 'then' here."),
    "haishi_better": (
        "还是 … 吧 = you'd better / let's just: 还是你去吧 (you'd better go), 还是坐德士吧.",
        "It's advice after thinking it over, not a question."),
    "cong_dao": (
        "从 A 到 B = from A to B, for time or place: 从八点到五点, 从怡保到槟城.",
        "Both halves come before the verb: 从八点到五点上班."),
    "cong_from": (
        "从 + place = from: 我从怡保来 (I come from Ipoh); for a path, through: 从后门进去 "
        "(go in by the back door).",
        "从 + place goes before the verb, not after it."),
    "wang_toward": (
        "往 + direction + verb = towards: 往前走 (go straight ahead), 往左转 (turn left).",
        "It's always before the verb: 走往前 ✗."),
    "gei_prep": (
        "给 + person + verb = to / for someone: 给我打电话 (call me), 给你买了一个 (bought one "
        "for you).",
        "Before the verb, not after: 打电话给我 is heard too, but 给我打电话 is standard."),
    "bi_adj": (
        "A 比 B + adjective = A is more … than B: 他比我高 (he's taller than me).",
        "No 很 or 非常: 他比我很高 ✗. Use 更 or an amount instead."),
    "yinwei_suoyi": (
        "因为 … 所以 … = because …, so …: 因为下雨，所以我没去. Either half can be dropped.",
        "English uses one word; Chinese happily uses both."),
    "danshi": (
        "但是 / 但 / 可是 = but, starting the second half: 很好吃，但是有点贵.",
        "Not at the end of a sentence."),
    "suiran_danshi": (
        "虽然 … 但是 … = although …, (but) …: 虽然很贵，但是很好吃.",
        "English drops 'but' after 'although'; Chinese keeps 但是."),
    "haishi_or": (
        "还是 = or, in questions: 你要咖啡还是茶？ (coffee or tea?).",
        "In statements 'or' is 或者: 今天或者明天都可以."),
    "suoyi": (
        "所以 = so, therefore, starting the result: 我很累，所以早睡.",
        "It starts the second half, never the first."),
    "deg_de": (
        "Verb + 得 + description = how well / how it was done: 他跑得快 (he runs fast), 你做"
        "得好.",
        "With an object, repeat the verb: 他说华语说得很好 (or 他华语说得很好)."),
    "de_manner": (
        "Description + 地 + verb = how it's done: 慢慢地走 (walk slowly), 高兴地说.",
        "地 goes before the verb; 得 comes after it."),
    "de_de_de": (
        "Three 'de's, one sound: 的 before a noun (我的书), 得 after a verb (跑得快), 地 before "
        "a verb (慢慢地走).",
        "They sound the same — position tells you which to write."),
    "guo_exp": (
        "Verb + 过 = have done it at some point: 我去过怡保 (I've been to Ipoh).",
        "It's about experience, not one specific time — that's 了."),
    "mei_guo": (
        "没 + verb + 过 = have never: 我没吃过榴莲 (I've never had durian).",
        "Keep 过: 我没吃榴莲 means I didn't eat it (this time)."),
    "zhe_state": (
        "Verb + 着 = a state that stays: 门开着 (the door is open), 他穿着新衣服.",
        "着 is the state; 在 is the action going on (他在穿衣服 = he's getting dressed)."),
    "a_particle": (
        "啊 / 呀 on the end adds warmth or emphasis: 好啊! (sure!), 是啊 (yeah), 你去哪里啊？",
        "It doesn't change the meaning — leave it out in writing."),
    "de_final": (
        "的 at the end makes it a firm statement: 我知道的 (I do know), 他会来的 (he will come).",
        "Overused it sounds pushy; it's for reassurance."),
    "res_dong": (
        "Verb + 懂 = understand by doing it: 听懂 (understand by hearing), 看懂 (by reading).",
        "'Didn't understand' is 没听懂; 'can't understand' is 听不懂."),
    "dir_lai_qu": (
        "Verb + 来 = towards the speaker, verb + 去 = away: 拿来 (bring it here), 带去 (take "
        "it there).",
        "Where you are decides it: 寄来 (send to me), 寄去 (send away)."),
    "de_nominal": (
        "Description + 的 with no noun = the one that is …: 红的 (the red one), 我买的 (the one "
        "I bought). 这件是新的 (this one is new).",
        "Leaving out the noun is normal once it's known."),
    "qu_place_v": (
        "去 + place + verb = go somewhere to do something: 去巴刹买菜, 去银行拿钱.",
        "The place goes between 去 and the purpose."),
    "lai_place_v": (
        "来 + place + verb = come somewhere to do something: 来我家吃饭 (come to my place for "
        "dinner).",
        "来 is towards the speaker; 去 is away."),
    "jianyu_causative": (
        "请 / 叫 / 让 + person + verb: ask, tell or let someone do it: 妈妈叫我去买菜 (mum told "
        "me to buy food), 让他进来 (let him in).",
        "The person sits in the middle: 让进来他 ✗. 'Not let' is 不让."),
    "shenmede": (
        "List two or three examples and end with 什么的 = and so on: 我喜欢看书、听音乐什么的.",
        "Casual speech — written lists use 等."),
    "jiuyao_le": (
        "就要 + verb + 了 = about to, soon — can take a time word: 我们明天就要走了 (we leave "
        "tomorrow).",
        "快要 can't have a time word before it; 就要 can."),
    "yao_le": (
        "要 + verb + 了 = going to, about to: 要下雨了 (it's going to rain), 巴士要来了.",
        "The 了 makes it 'about to'; without it 要 is 'want'."),
    "topic_comment": (
        "Put what you're talking about first, then say something about it: 这本书，我看过 "
        "(this book, I've read it). Often the object moves to the front.",
        "Very common in speech — not a mistake, a way of focusing."),
    "rel_v_de": (
        "Verb phrase + 的 + noun = the … that …: 我买的菜 (the food I bought), 在唱歌的女孩 "
        "(the girl who's singing).",
        "The description always goes before the noun — no 'who / that' word."),
    "rel_person": (
        "Describe a person before the noun with 的: 坐在那里的人 (the person sitting there), "
        "教我华语的老师.",
        "English puts 'who …' after the person; Chinese puts it before."),
    "res_cuo": (
        "Verb + 错 = do it wrong: 听错 (misheard), 走错 (went the wrong way), 写错.",
        "Not 错 + verb: 错说 ✗."),
    "res_hao": (
        "Verb + 好 = done properly, ready: 做好了 (it's done), 准备好 (ready), 坐好 (sit "
        "properly).",
        "Here 好 is 'finished and right', not 'good'."),
    "res_wan": (
        "Verb + 完 = finish: 吃完 (finish eating), 做完了 (finished doing it).",
        "'Haven't finished' is 没做完, not 不做完."),
    "res_negation": (
        "Results are negated with 没: 没听懂 (didn't understand), 没找到 (didn't find it).",
        "Not 不听懂 ✗ — 不 + result means 'can't', and that's 听不懂."),
    "res_le": (
        "Result + 了 = it happened: 找到了 (found it), 听懂了 (got it). 了 comes after the "
        "whole verb + result.",
        "Not between them: 找了到 ✗."),
    "dir_shang": (
        "Verb + 上来 / 上去 = up (towards / away): 你上来吧 (come up), 我上去找你 (I'll come "
        "up to you).",
        "来 / 去 depend on where the speaker is."),
    "dir_xia": (
        "下来 / 下去 = down: 你下来 (come down), 他下去了 (he went down).",
        "下去 also means 'carry on' later on — here it's direction."),
    "dir_jin": (
        "进来 / 进去 = in: 请进来 (come in), 我进去看看 (I'll go in and look).",
        "Speaker inside: 进来; outside: 进去."),
    "dir_chu": (
        "出来 / 出去 = out: 你出来一下 (come out a moment), 我们出去吃 (let's eat out).",
        "出去吃 = go out to eat — direction then purpose."),
    "dir_hui": (
        "回来 / 回去 = back: 你几点回来？ (when are you coming back?), 我要回去了 (I'm going "
        "back).",
        "Home where the speaker is: 回来; elsewhere: 回去."),
    "dir_guo": (
        "过来 / 过去 = over: 你过来一下 (come over here), 我过去找你 (I'll come over).",
        "Movement across a space, towards or away."),
    "dir_simple": (
        "Verb + 进 / 出 / 上 / 下 / 回 / 过 = the direction of the action: 走进 (walk in), 跑出 "
        "(run out), 坐下 (sit down).",
        "The place goes after: 走进房间."),
    "dir_compound": (
        "Verb + direction + 来 / 去: 走进来 (walk in, towards me), 拿回去 (take back), 跑出去.",
        "A place goes before 来 / 去: 走进房间来, not 走进来房间."),
    "deg_de_hen": (
        "Verb + 得 + 很 / 太 / 不 + adjective: 说得很好 (speaks well), 吃得太快, 写得不好.",
        "The negative goes after 得: 说得不好, not 不说得好."),
    "dur_basic": (
        "How long goes after the verb: 我等了十分钟 (I waited ten minutes), 睡了八个钟头.",
        "Not before it like English 'for ten minutes I waited'."),
    "le_le": (
        "Verb + 了 + time + 了 = have been doing (and still are): 我学了两年华语了 (I've been "
        "learning for two years).",
        "One 了 = it lasted that long and stopped; two 了 = still going."),
    "dur_verb_obj": (
        "With an object, say the verb twice: 他学华语学了两年 (he studied Chinese for two years).",
        "他学了华语两年 ✗ — or put the time before the object: 他学了两年华语."),
    "bi_quantity": (
        "A 比 B + adjective + amount = more … by: 他比我大三岁 (he's three years older), 贵十块.",
        "The amount goes last: 他比我三岁大 ✗."),
    "double_subject": (
        "Topic + part + adjective: 她个子很高 (she's tall), 我头疼 (I have a headache), 这家店"
        "菜很好吃.",
        "No 的 needed between them, and no 是."),
    "you_reach": (
        "有 + amount = reach, be as much as: 他有三十岁吗？ (is he thirty?). A 有 B (那么) + "
        "adjective = as … as: 你有他高吗？",
        "Mostly in questions; the negative is 没有 … 那么."),
    "zhe_scene": (
        "Place + verb + 着 + thing = there is … (in that position): 门口站着一个人 (someone is "
        "standing at the door), 墙上挂着照片.",
        "The place comes first, no 在 in front."),
    "meiyou_name": (
        "A 没有 B (那么) + adjective = A isn't as … as B: 我没有他那么高 (I'm not as tall as "
        "him).",
        "Not 不比 for this — 不比 means 'no more … than'."),
    "bi_vs_meiyou": (
        "他比我高 (he's taller) ↔ 我没有他那么高 (I'm not as tall). 比 says more; 没有 … 那么 "
        "says less.",
        "The negative of 比 is usually 没有, not 不比."),
    "bi_verb": (
        "A 比 B + verb + 得 + adjective, or A + verb + 得 + 比 B + adjective: 她比我说得好 / 她说"
        "得比我好 (she speaks better than me).",
        "Both orders are fine; 比 never comes after the adjective."),
    "shi_de": (
        "是 … 的 points at a detail of something that already happened — when, where, how "
        "or who: 我是昨天到的 (it was yesterday that I arrived).",
        "Only for the past, and the event is already known."),
    "shi_de_time": (
        "是 + time + verb + 的: 我是上个星期到的 (I arrived last week).",
        "Not 了 in its place: 我是上个星期到了 ✗."),
    "shi_de_place": (
        "是 + 在 place + verb + 的: 这个是在巴刹买的 (I bought this at the market).",
        "The place goes right after 是."),
    "shi_de_manner": (
        "是 + how + verb + 的: 我是坐巴士来的 (I came by bus).",
        "The point is 'how' — the coming is already known."),
    "shi_de_agent": (
        "是 + who + verb + 的: 这个菜是我妈做的 (my mum made this dish).",
        "Stresses who did it."),
    "shi_de_question": (
        "Ask about a detail: 你是什么时候到的？ (when did you get here?), 是不是你拿的？",
        "Use it when the event itself is known."),
    "shi_de_neg": (
        "不是 … 的: 我不是坐飞机来的，是坐巴士来的 (I didn't fly, I came by bus).",
        "The 不 goes before 是, not before the verb."),
    "shi_de_vs_le": (
        "他来了 (he's come — news) ↔ 他是昨天来的 (it was yesterday he came — a detail of "
        "known news).",
        "First mention with 了, details with 是 … 的."),
    "v_gei": (
        "Verb + 给 + person (+ thing) = to someone: 送给你 (give to you), 还给他 (return to him), "
        "卖给我一本书.",
        "给 comes right after the verb here."),
    "le_vs_guo": (
        "我去了槟城 (I went to Penang — that trip) ↔ 我去过槟城 (I've been to Penang — at some "
        "point).",
        "过 is experience; 了 is a specific completed event."),
    "zai_vs_zhe": (
        "他在穿衣服 (he's getting dressed — action) ↔ 他穿着新衣服 (he's wearing new clothes — "
        "state).",
        "在 is the doing; 着 is the result that stays."),
    "jige": (
        "几 + measure word in a statement = a few: 买几个 (buy a few), 几个朋友 (a few "
        "friends), 几百个 (several hundred).",
        "Only a question if you ask it as one."),
}
