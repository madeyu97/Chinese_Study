# src/hsk_grammar_3.py
"""HSK 3's grammar points: which structures teach them, and the cards for
structures first met at HSK 3. Merged into hsk_grammar's MAP / LEXICAL /
LEARN (see there)."""

MAP = {
    "g3-01": (),                                                # 老—
    "g3-02": (),                                                # —家、—子、—员
    "g3-03": (),                                                # 东 南 西 北 …
    "g3-04": ("xuyao", "yinggai", "yuanyi", "dei_must"),        # 需要 该 应该 愿意 得
    "g3-05": ("lihe_verbs",),                                   # 放假 见面 结婚 洗澡
    "g3-06": ("res_kai", "res_jian", "pot_bu"),                 # 打开 看见 离开 …
    "g3-07": ("zenme", "zenmeyang"),                            # 怎样
    "g3-08": ("qword_dou", "shenme_dou_bu", "shei_dou_bu", "nali_dou_bu"),
    "g3-09": ("qword_indefinite",),                             # 在哪里见过她
    "g3-10": (),                                                # 别人、咱们
    "g3-11": (),                                                # 别的、其他
    "g3-12": ("mw_common",),                                    # 把 双 张 种 …
    "g3-13": ("mw_common",),                                    # 碗、盘
    "g3-14": ("bian_times", "ci_times", "ci_vs_bian"),          # 口 回 遍 声
    "g3-15": ("mw_redup",),                                     # 个个、张张
    "g3-16": ("bijiao_adj", "bi_hai", "geng", "tebie", "ting_adj", "youdian",
              "yuelaiyue", "jile"),
    "g3-17": ("zhi_only", "yigong", "jiu_emphatic"),            # 就 一块儿 一共 只 …
    "g3-18": ("cai_late", "mashang", "xian", "v_yihui", "gang", "gangcai", "yizhi",
              "gang_vs_gangcai"),
    "g3-19": ("zongshi", "you_again"),                          # 总 总是 又 常常
    "g3-20": ("yibian",),                                       # 一边
    "g3-21": ("dayue", "bixu", "chabuduo", "yiding", "haoxiang", "jihu"),
    "g3-22": ("dangran", "qishi", "zhongyu", "cai_only", "cai_vs_jiu", "jiu_early"),
    "g3-23": ("buyong",),                                       # 不必、不用
    "g3-24": ("wei_for", "xiang_toward", "guanyu"),             # 为 向 关于
    "g3-25": ("xiang_toward",),                                 # 向 (direction)
    "g3-26": ("weile",),                                        # 为了、为
    "g3-27": ("ba_basic", "bei_basic"),                         # 把、被
    "g3-28": ("genju",),                                        # 根据
    "g3-29": ("huozhe",),                                       # 或、或者
    "g3-30": ("zhiyou_cai", "zhiyao_jiu", "budan_erqie", "ruguo_jiu", "suiran_danshi",
              "ranhou", "ruguo_vs_zhiyao"),
    "g3-31": ("dehua",),                                        # 的话
    "g3-32": (),                                                # 首都北京
    "g3-33": ("jile", "pot_de", "pot_bu"),                      # 漂亮极了 看不懂 写得完
    "g3-34": ("mw_redup",),                                     # 一步一步
    "g3-35": ("bu_a_bu_b",),                                    # 不大不小
    "g3-36": (),                                                # 不一会儿
    "g3-37": ("kanlai",),                                       # 看来
    "g3-38": ("kanlai", "dui_laishuo"),                         # 在……看来
    "g3-39": ("yuelaiyue",),                                    # 越来越
    "g3-40": ("kan_ting_qilai",),                               # 看起来
    "g3-41": ("kan_ting_qilai",),                               # 看上去
    "g3-42": (),                                                # 一般来说
    "g3-43": (),                                                # 不怎么样
    "g3-44": ("chule_hai", "chule_dou"),                        # 除了……还/也/都
    "g3-45": ("cong_kaishi",),                                  # 从……起
    "g3-46": ("dui_laishuo",),                                  # 对……来说
    "g3-47": ("yi_mw_ye_bu",),                                  # 一……也/都+不/没
    "g3-48": ("yidian_bu",),                                    # 一点也不
    "g3-49": ("yue_yue", "yue_v_yue"),                          # 越……越……
    "g3-50": ("yiqian", "yihou"),                               # ……以前 / 以后
    "g3-51": ("x_shenme_a",),                                   # X什么(啊)
    "g3-52": ("gai_le",),                                       # 该……了
    "g3-53": ("zai_shang_xia",),                                # 在……上/下/中
    "g3-54": ("verb_subject",),                                 # 哭没有用
    "g3-55": ("verb_subject",),                                 # 你来也可以
    "g3-56": ("rel_multi",),                                    # several descriptions
    "g3-57": ("res_dao", "res_zhu", "res_zou"),                 # 到 住 走 上
    "g3-58": ("v_chulai", "v_qilai", "v_xialai"),               # 想出 想起 写下
    "g3-59": ("v_qilai",),                                      # 玩上了、笑起来
    "g3-60": ("v_xiaqu", "v_xialai"),                           # 坚持下去
    "g3-61": ("pot_de", "pot_bu", "pot_question", "pot_ting_dong", "pot_kan_jian"),
    "g3-62": ("deg_dehen",),                                    # 好得很
    "g3-63": ("jile",),                                         # 极了 / 坏了
    "g3-64": ("time_since",),                                   # 开学已经两个星期了
    "g3-65": ("zenme",),                                        # 怎样 + verb
    "g3-66": ("rhetorical_q",),                                 # 不是……吗？
    "g3-67": ("ba_location",),
    "g3-68": ("ba_basic", "v_gei"),
    "g3-69": ("ba_result", "ba_direction", "ba_le", "ba_vs_active"),
    "g3-70": ("bei_basic", "bei_result", "bei_le", "bei_vs_active"),
    "g3-71": ("bei_no_agent",),
    "g3-72": ("zhe_manner",),                                   # 笑着回答
    "g3-73": ("bi_geng", "bi_hai"),
    "g3-74": ("gen_yiyang", "gen_bu_yiyang"),
    "g3-75": ("gen_yiyang",),
    "g3-76": ("bu_bi",),
    "g3-77": ("bi_zao_wan", "bi_duo_shao"),
    "g3-78": ("appear_disappear",),
    "g3-79": ("appear_disappear",),
    "g3-80": ("de_final",),                                     # 是很简单的
    "g3-81": ("dur_verb_obj",),                                 # 打篮球打了一个下午
    "g3-82": ("xian_zai", "ranhou"),
    "g3-83": ("huozhe",),
    "g3-84": ("yihui_yihui",),
    "g3-85": ("you_you",),
    "g3-86": ("yibian",),
    "g3-87": ("budan_erqie",),
    "g3-88": ("suiran_danshi",),
    "g3-89": ("ruguo_jiu",),
    "g3-90": ("dehua",),
    "g3-91": ("zhiyou_cai",),
    "g3-92": ("zhiyao_jiu",),
    "g3-93": ("weile",),
    "g3-94": ("le_jiu",),
    "g3-95": ("dayue",),
    "g3-96": ("approx_adjacent",),
}

LEXICAL = {
    "g3-01": "老 before a surname (老李, old Li) — a way of addressing people, learnt with words.",
    "g3-02": "Word endings (画家 painter, 桌子 table, 服务员 waiter) — learnt with the words.",
    "g3-03": "Compass points (东 east, 南 south …) — vocabulary.",
    "g3-10": "别人 (other people), 咱们 (we, including you) — vocabulary.",
    "g3-11": "别的 / 其他 (other) — vocabulary.",
    "g3-32": "Two nouns for the same thing side by side (首都北京, the capital Beijing) — met "
             "in reading.",
    "g3-36": "不一会 (before long) — a set phrase.",
    "g3-42": "一般来说 (generally speaking) — a set phrase.",
    "g3-43": "不怎么样 (not up to much) — a set phrase.",
}

LEARN = {
    "xuyao": (
        "需要 + thing or verb = need: 我需要休息 (I need a rest), 需要多少钱？",
        "'Don't need to' is 不用 / 不需要 — 不需要 is fine, 别需要 ✗."),
    "yinggai": (
        "应该 + verb = should: 你应该早点睡. It also means 'probably': 他应该到了 (he should be "
        "there by now).",
        "Negative is 不应该 (shouldn't); 'don't have to' is 不用."),
    "yuanyi": (
        "愿意 + verb = be willing to: 我愿意帮你 (I'm happy to help).",
        "It's about willingness, not wanting: 我愿意 sounds like agreeing to something."),
    "dei_must": (
        "得 (děi) + verb = have to, spoken: 我得走了 (I have to go).",
        "Its negative isn't 不得 — it's 不用 (don't have to)."),
    "res_kai": (
        "Verb + 开 = open / apart / away: 打开 (open), 走开 (go away), 分开 (separate).",
        "'Can't open it' is 打不开."),
    "res_jian": (
        "Verb + 见 = it registered: 看见 (saw), 听见 (heard), 遇见 (bumped into).",
        "看 is looking; 看见 is actually seeing."),
    "pot_bu": (
        "Verb + 不 + result = can't manage it: 吃不完 (can't finish it), 听不懂 (can't "
        "understand), 找不到 (can't find it).",
        "不能听懂 ✗ — the 不 goes inside."),
    "qword_dou": (
        "Question word + 都 = every / any: 什么都吃 (eat anything), 谁都认识他 (everyone knows "
        "him), 哪里都可以.",
        "The question word goes before 都 and the verb."),
    "shenme_dou_bu": (
        "什么都不 / 什么都没 + verb = nothing at all: 我什么都不想吃, 他什么都没说.",
        "Not 我不吃什么 for 'I eat nothing' — that means 'there's nothing much I don't eat'."),
    "shei_dou_bu": (
        "谁都不 + verb = nobody: 谁都不知道 (nobody knows).",
        "谁 goes first, before 都."),
    "nali_dou_bu": (
        "哪里都不 / 没 + 去 = nowhere: 我哪里都不想去 (I don't want to go anywhere).",
        "Not 我不去哪里 ✗."),
    "qword_indefinite": (
        "Question words can mean some- / any-: 想吃点什么 (want something to eat?), 我好像在"
        "哪里见过她 (I've seen her somewhere).",
        "Without a question tone they aren't questions."),
    "mw_redup": (
        "A doubled measure word + 都 = every single one: 个个都很大, 天天 (every day). 一步一步"
        "地 = step by step.",
        "The doubled measure word needs 都 after it."),
    "bian_times": (
        "遍 counts times through from start to finish: 再说一遍 (say it again), 看了两遍 (read it "
        "twice).",
        "次 just counts occasions; 遍 means the whole thing each time."),
    "ci_vs_bian": (
        "去过三次 (been three times — occasions) ↔ 看了两遍 (read it twice — all the way through).",
        "Use 遍 for reading, watching, saying something in full."),
    "bijiao_adj": (
        "比较 + adjective = fairly, relatively: 比较贵 (rather expensive).",
        "Not a comparison with 比 — just 'fairly'."),
    "bi_hai": (
        "A 比 B 还 + adjective = even more (surprisingly): 他比我还高 (he's even taller than me).",
        "还 adds surprise; 更 is plain 'even more'."),
    "geng": (
        "更 + adjective or verb = even more: 我更喜欢这个 (I like this one more).",
        "More than one 更 ✗; no 很 after it."),
    "tebie": (
        "特别 + adjective = especially: 今天特别热.",
        "It's stronger than 很 but not used with 比."),
    "ting_adj": (
        "蛮 / 挺 + adjective (+ 的) = quite: 蛮好的 (pretty good). Malaysians say 蛮; 挺 is "
        "mainland.",
        "Softer than 很 — it isn't 'very'."),
    "yuelaiyue": (
        "越来越 + adjective = more and more: 越来越热 (hotter and hotter).",
        "No 很 after it: 越来越很热 ✗."),
    "jile": (
        "Adjective + 极了 = extremely: 好吃极了, 累极了. 累坏了 = worn out.",
        "极了 goes after the adjective, never before."),
    "zhi_only": (
        "只 + verb = only: 我只喝水. 只有 + person / amount = only: 只有他知道.",
        "只 goes before the verb, not the noun: 我喝只水 ✗."),
    "yigong": (
        "一共 + amount = altogether: 一共多少钱？ (how much altogether?), 一共三个.",
        "It goes before the number or verb, not after."),
    "cai_late": (
        "Time + 才 + verb = not until, later than expected: 他十点才来 (he didn't come until "
        "ten).",
        "No 了 with 才: 他十点才来了 ✗."),
    "mashang": (
        "马上 + verb = right away: 我马上来 (I'm coming right now).",
        "It goes before the verb, often with 就."),
    "xian": (
        "先 + verb = first: 你先吃 (you eat first).",
        "Before the verb, not at the end like 'first' in English."),
    "v_yihui": (
        "Verb + 一会 = for a little while: 休息一会 (rest a bit), 等了一会.",
        "一下 is quick and casual; 一会 is a short stretch of time."),
    "gang": (
        "刚 / 刚刚 + verb = just did: 我刚到 (I've just arrived).",
        "No 了 needed: 我刚到了 is wrong for 'just arrived'."),
    "gangcai": (
        "刚才 = just now, a time word: 刚才你说什么？ (what did you say just now?).",
        "As a time word it can go before the subject; 刚 can't."),
    "gang_vs_gangcai": (
        "我刚到 (I've just arrived — adverb) ↔ 刚才我没听到 (just now I didn't hear — time).",
        "刚才 can take 不 / 没 after it; 刚 can't take 没."),
    "yizhi": (
        "一直 + verb = all along, continuously: 我一直在等你 (I've been waiting all along), 一直"
        "走 (go straight on).",
        "It's 'the whole time', not 'often'."),
    "zongshi": (
        "总是 / 总 + verb = always: 他总是迟到 (he's always late).",
        "常常 is often; 总是 is every time. Not always = 不总是."),
    "you_again": (
        "又 + verb = again (it already happened again): 他又迟到了 (he's late again).",
        "For a future 'again' use 再: 明天再来."),
    "yibian": (
        "一边 A 一边 B = do A while doing B: 一边吃饭一边看手机.",
        "Both verbs are actions you do at the same time."),
    "dayue": (
        "大概 / 大约 + amount = about: 大概五十块 (about fifty). 大概 also means 'probably': 他大"
        "概回家了.",
        "Don't stack it with 左右 every time — one is enough."),
    "bixu": (
        "必须 + verb = must: 你必须早点到 (you must be early).",
        "The negative is 不用 / 不必 (don't have to), not 不必须."),
    "chabuduo": (
        "差不多 = about (差不多十点), almost (差不多好了), or much the same (差不多).",
        "Context decides which meaning."),
    "yiding": (
        "一定 + verb = definitely / must: 我一定去 (I'll definitely go), 你一定要来!",
        "不一定 = not necessarily, not 'definitely not'."),
    "haoxiang": (
        "好像 = seems, as if: 好像要下雨 (looks like rain), 他好像不高兴.",
        "It softens a guess; not 'like' for comparisons."),
    "jihu": (
        "几乎 = almost: 几乎每天都去 (go almost every day), 几乎没有人 (hardly anyone).",
        "With 都 or 没有 after it, it means almost all / almost none."),
    "dangran": (
        "当然 = of course: 当然可以! (of course!), 当然是你.",
        "It goes before the verb or at the start."),
    "qishi": (
        "其实 = actually, reveals the truth: 其实我不喜欢 (actually I don't like it).",
        "It corrects an impression — not 'really' as an intensifier."),
    "zhongyu": (
        "终于 + verb (+ 了) = finally, after waiting: 他终于来了!",
        "It's relief; '最后' is just 'last / in the end'."),
    "cai_only": (
        "才 + amount = only (less than expected): 才十块! (only ten!), 他才三岁.",
        "Here 才 is about small amounts, not lateness."),
    "cai_vs_jiu": (
        "他十点才来 (didn't come until ten — late) ↔ 他八点就来了 (came as early as eight).",
        "就 takes 了; 才 doesn't."),
    "jiu_early": (
        "Time + 就 + verb + 了 = already, early: 他八点就来了 (he came at eight already).",
        "Keep the 了 — 就 means early, 才 means late."),
    "buyong": (
        "不用 / 不必 + verb = no need to: 你不用来 (you needn't come), 不用谢 (no need to thank "
        "me).",
        "It's relief, not a ban — 'don't!' is 别 / 不要."),
    "wei_for": (
        "为 + person + verb / feeling = for someone: 我为你高兴 (I'm happy for you).",
        "It's for someone's sake; to give something to someone is 给."),
    "xiang_toward": (
        "向 + direction / person = towards: 向前看 (look ahead), 向他学习 (learn from him).",
        "Like 往 for direction, but 向 also works with people."),
    "guanyu": (
        "关于 + topic = about: 关于这件事 (about this matter), 一本关于槟城的书.",
        "It usually starts the sentence or describes a noun with 的."),
    "weile": (
        "为了 + purpose = in order to, for: 为了省钱，他走路去 (to save money he walks).",
        "The purpose usually comes first, not at the end like English 'to …'."),
    "ba_basic": (
        "把 + thing + verb + something more: say what you do to a known thing: 把门关上 (shut the "
        "door), 把药吃了.",
        "The verb can't stand alone after 把: 把门关 ✗ — add a result or 了."),
    "bei_basic": (
        "被 + doer + verb + result = was done (usually unwelcome): 我的车被他撞坏了 (my car was "
        "smashed by him).",
        "The verb needs something after it: 被他撞 ✗."),
    "genju": (
        "根据 + source = based on: 根据天气预报，明天会下雨.",
        "It goes at the start, before the main clause."),
    "huozhe": (
        "或者 = or, in statements: 星期六或者星期天都可以.",
        "In questions 'or' is 还是."),
    "zhiyou_cai": (
        "只有 A，才 B = only if A, B: 只有多讲，才会进步 (only by speaking more will you improve).",
        "Pair 只有 with 才, not 就."),
    "zhiyao_jiu": (
        "只要 A，就 B = as long as A, B: 只要有时间，我就去.",
        "Pair 只要 with 就, not 才."),
    "budan_erqie": (
        "不但 A，而且 B = not only A but also B: 这家不但便宜，而且好吃.",
        "Same subject: 不但 goes after it. Different subjects: 不但 goes before the first."),
    "ruguo_jiu": (
        "如果 A (的话)，就 B = if A, then B: 如果下雨，我就不去.",
        "就 goes after the second subject: 我就不去, not 就我不去."),
    "ranhou": (
        "然后 = and then: 先吃饭，然后去看戏.",
        "It links steps in order; it's not 'and' for nouns."),
    "ruguo_vs_zhiyao": (
        "如果有时间，我就去 (if I have time I'll go) ↔ 只要有时间，我就去 (as long as I have "
        "time, I'll go — that's all it takes).",
        "只要 says the condition is enough; 如果 just says 'if'."),
    "dehua": (
        "……的话 = if, at the end of the condition: 你有空的话，来玩 (come over if you're free).",
        "It can join 如果: 如果下雨的话."),
    "pot_de": (
        "Verb + 得 + result = can manage it: 吃得完 (can finish), 听得懂 (can understand).",
        "Mostly in questions and answers to them."),
    "bu_a_bu_b": (
        "不 + adjective + 不 + its opposite = just right: 不大不小 (just the right size), 不冷不热.",
        "Only with opposite pairs."),
    "kanlai": (
        "看来 = it seems, judging from this: 看来他不来了 (looks like he isn't coming).",
        "A conclusion from evidence, usually at the start."),
    "dui_laishuo": (
        "对 + person + 来说 = for, as far as … is concerned: 对我来说，华语不难.",
        "It frames an opinion; it goes at the start."),
    "kan_ting_qilai": (
        "看起来 / 看上去 = it looks; 听起来 = it sounds: 看起来要下雨, 听起来不错.",
        "It's an impression from the senses, not a fact."),
    "chule_hai": (
        "除了 A (以外)，还 / 也 B = besides A, also B: 除了华语以外，他还会讲福建话.",
        "With 还 / 也 it adds; with 都 it excludes."),
    "chule_dou": (
        "除了 A (以外)，都 B = everyone / everything except A: 除了他以外，我们都去.",
        "With 都 it excludes A."),
    "cong_kaishi": (
        "从 + time + 开始 / 起 = starting from: 从明天开始 (from tomorrow), 从那天起.",
        "It goes at the start or before the verb."),
    "yi_mw_ye_bu": (
        "一 + measure word (+ noun) + 也 / 都 + 不 / 没 = not a single one: 我一个人也不认识, "
        "他一块钱都没有.",
        "The 'one' goes before the verb: 我不认识一个人 ✗ for this."),
    "yidian_bu": (
        "一点也不 / 一点都不 + adjective = not at all: 一点也不贵 (not expensive at all).",
        "Not 不一点 ✗."),
    "yue_yue": (
        "越 A 越 B = the more A, the more B: 天越热，人越少 (the hotter it is, the fewer people).",
        "No 很 after 越: 越很热 ✗."),
    "yue_v_yue": (
        "越 + verb + 越 + adjective = the more you do it, the more …: 越吃越想吃, 越说越快.",
        "Same subject for both; no 很."),
    "yiqian": (
        "Event + 以前 / 之前 = before: 吃饭以前 (before eating). Alone, 以前 = in the past: 我以前"
        "住槟城.",
        "Before goes after the event in Chinese: 以前吃饭 ✗."),
    "yihou": (
        "Event + 以后 / 之后 = after: 下班以后 (after work). Alone, 以后 = from now on.",
        "After goes after the event: 以后下班 ✗."),
    "x_shenme_a": (
        "Verb / adjective + 什么(啊) brushes it off: 贵什么啊，才十块! (expensive? it's only ten!), "
        "急什么? (what's the hurry?).",
        "Not a question about 'what' — it's disagreement."),
    "gai_le": (
        "该 + verb + 了 = it's time to: 该走了 (time to go). 该你了 = your turn.",
        "Keep the 了; 应该 is 'should', not 'time to'."),
    "zai_shang_xia": (
        "在 + topic + 上 = in terms of (在工作上); 在 + …的帮助 + 下 = with the help of; 在 + "
        "process + 中 = during.",
        "The frame goes at the start or before the verb."),
    "verb_subject": (
        "An action can be the subject, no 'to' or '-ing' needed: 哭没有用 (crying won't help), "
        "多运动对身体好.",
        "Don't add 是 to link it: 哭是没有用 is only for stress."),
    "rel_multi": (
        "Several descriptions before one noun: owner → this/that + number → description → "
        "noun: 我昨天买的那个大榴莲 (the big durian I bought yesterday).",
        "Put 的 after clause descriptions; short adjectives stay next to the noun."),
    "res_dao": (
        "Verb + 到 = manage to, reach: 找到 (found), 买到 (managed to buy), 走到 (walk to).",
        "找 is looking; 找到 is finding."),
    "res_zhu": (
        "Verb + 住 = hold firm: 记住 (remember), 抓住 (grab hold), 站住 (stop!).",
        "'Can't remember' is 记不住."),
    "res_zou": (
        "Verb + 走 = take away: 拿走 (take away), 偷走 (steal), 搬走 (move out).",
        "With 被: 被偷走了 (was stolen)."),
    "v_chulai": (
        "Verb + 出来 = out, or figure out: 拿出来 (take out), 想出来 (think up), 认出来 "
        "(recognise).",
        "'Can't figure it out' is 想不出来."),
    "v_qilai": (
        "Verb + 起来 = up, start, come to mind: 站起来 (stand up), 笑起来 (burst out laughing), "
        "想起来 (remember).",
        "An object goes between: 想起他的名字来, or after: 想起来了."),
    "v_xialai": (
        "Verb + 下来 = settle, stop, record, stay: 停下来 (stop), 写下来 (write it down), 留下来 "
        "(stay on).",
        "下来 is coming to rest; 下去 is carrying on."),
    "v_xiaqu": (
        "Verb + 下去 = keep going: 说下去 (go on), 坚持下去 (keep at it).",
        "这样下去 = if this goes on."),
    "pot_question": (
        "Ask with 得 / 不: 听得懂吗？ or 听不听得懂？ or 听得懂听不懂？",
        "Answer with the short form: 听得懂 / 听不懂."),
    "pot_ting_dong": (
        "听得懂 / 听不懂 = can / can't understand (what's said): 你听得懂吗？——听不懂.",
        "不会听 is 'can't listen' — not the same."),
    "pot_kan_jian": (
        "看得见 / 看不到 = can / can't see; 听不到 = can't hear.",
        "Not 不能看到 — that's 'not allowed to see'."),
    "deg_dehen": (
        "Adjective + 得很 = very (emphatic): 好得很, 贵得很.",
        "Stronger than 很 + adjective, and comes after."),
    "time_since": (
        "Event + (已经) + time + 了 = it's been … since: 他走了三天了 (he left three days ago), 我"
        "来马来西亚五年了.",
        "With a one-off verb (来, 走, 结婚) the time is since it happened, not how long it lasted."),
    "rhetorical_q": (
        "不是 … 吗？ makes a point: 你不是说不来吗？ (didn't you say you weren't coming?).",
        "It expects agreement, not an answer."),
    "ba_location": (
        "把 + thing + verb + 在 / 到 + place: 把书放在桌上 (put the book on the table).",
        "The place goes after the verb: 把书在桌上放 ✗."),
    "ba_result": (
        "把 + thing + verb + result: 把饭吃完 (finish the food), 把门关好.",
        "The result is what makes 把 needed."),
    "ba_direction": (
        "把 + thing + verb + direction: 把书拿出来 (take the book out), 把垃圾拿出去.",
        "The direction goes after the verb."),
    "ba_le": (
        "把 + thing + verb + 了 = dealt with / gone: 把药吃了 (take the medicine), 把旧衣服丢了.",
        "Usually for finishing or getting rid of something."),
    "ba_vs_active": (
        "我吃完了饭 (I finished eating) ↔ 我把饭吃完了 (I finished the food — that food).",
        "把 needs a specific, known thing."),
    "bei_result": (
        "被 + verb + result: 被偷走了 (was stolen), 被吃光了 (was eaten up).",
        "The verb needs a result or 了 after it."),
    "bei_le": (
        "被 + (doer) + verb + 了: 他被骂了 (he got told off).",
        "Keep the 了 — 被骂 alone sounds cut off."),
    "bei_vs_active": (
        "他打了我 (he hit me) ↔ 我被他打了 (I was hit by him — focus on me).",
        "被 is mostly for things you didn't want to happen."),
    "bei_no_agent": (
        "被 + verb with no doer: 我的钱包被偷了 (my wallet was stolen).",
        "When the doer is unknown, just leave it out."),
    "zhe_manner": (
        "Verb + 着 + second verb = do it in that state: 走着去 (go on foot), 站着吃, 笑着说.",
        "The 着 verb is the manner; the second is the action."),
    "bi_geng": (
        "A 比 B 更 + adjective = even more: 今天比昨天更热.",
        "更, not 很: 比昨天很热 ✗."),
    "gen_yiyang": (
        "A 跟 B 一样 (+ adjective) = the same (as): 我跟你一样高 (I'm as tall as you).",
        "The adjective follows 一样."),
    "gen_bu_yiyang": (
        "A 跟 B 不一样 = different from: 马来西亚的华语跟中国的不一样.",
        "不 goes before 一样, not before 跟."),
    "bu_bi": (
        "A 不比 B + adjective = A is no more … than B (about the same): 我不比他高.",
        "It's not 'less than' — that's 没有 … 那么."),
    "bi_zao_wan": (
        "A 比 B 早 / 晚 + verb + time: 他比我早到十分钟 (he arrived ten minutes before me).",
        "早 / 晚 go before the verb, the time after it."),
    "bi_duo_shao": (
        "A 比 B 多 / 少 + verb + amount: 他比我多吃了一碗 (he ate one more bowl than me).",
        "多 / 少 go before the verb."),
    "appear_disappear": (
        "Place + verb + 了 + amount + thing = appeared / left: 前面开过来一辆车 (a car drove up), "
        "楼上搬来了一家人.",
        "The new thing comes after the verb, with a number."),
    "you_you": (
        "又 A 又 B = both A and B: 又便宜又好吃 (cheap and tasty).",
        "Both qualities point the same way, both good or both bad."),
    "yihui_yihui": (
        "一会 A，一会 B = now A, now B: 他一会进来，一会出去 (he keeps going in and out).",
        "It's switching back and forth, often annoying."),
    "le_jiu": (
        "Verb + 了 + …，就 + … = once … then: 我下了班就去 (I'll go after work), 吃了药就好多了.",
        "The 了 marks 'once done', not the past."),
    "approx_adjacent": (
        "Two neighbouring numbers = roughly: 两三个 (two or three), 七八个人, 十五六岁.",
        "Smaller first, and only neighbours: 三五个 is a set phrase, 三六个 ✗."),
}
