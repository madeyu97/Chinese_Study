# src/hsk_grammar_4.py
"""HSK 4's grammar points: which structures teach them, and the cards for
structures first met at HSK 4. Merged into hsk_grammar's MAP / LEXICAL /
LEARN (see there)."""

MAP = {
    "g4-01": ("gan",),                                          # 敢
    "g4-02": (),                                                # 各、任何、此
    "g4-03": ("mw_common",),                                    # 打 袋 棵 台 幅
    "g4-04": (),                                                # 一脸、满脸
    "g4-05": ("ci_times",),                                     # 场、顿、趟
    "g4-06": ("youqi", "duo_a", "shaowei"),                     # 十分 更加 稍微 尤其 多么
    "g4-07": ("dou_vs_quan", "guang_jiu", "zhishao_zuiduo", "zhi_only"),
    "g4-08": ("conglai_bu", "conglai_mei", "yuanlai"),          # 从来 本来 …
    "g4-09": ("zongshi",),                                      # 老 (always) …
    "g4-10": (),                                                # 故意、互相
    "g4-11": ("que_but",),                                      # 却
    "g4-12": ("keneng", "haoxiang"),                            # 也许、恐怕
    "g4-13": ("cai_ne", "bing_bu", "hai_surprise", "jingran", "daodi", "rhetorical_q",
              "zhihao", "chadian"),
    "g4-14": ("suizhe", "de_shihou"),                           # 自 当 由 随着
    "g4-15": ("bei_rang_jiao",),                                # 将 由 叫 让
    "g4-16": ("youyu",),                                        # 由于
    "g4-17": ("duiyu", "guanyu_vs_duiyu"),                      # 对于、与
    "g4-18": ("anzhao",),                                       # 作为 按 按照
    "g4-19": ("er_contrast",),                                  # 并 而 与
    "g4-20": ("er_contrast", "jiran_jiu", "shenzhi", "buguo"),  # 此外 而 既然 甚至 不过 并且
    "g4-21": ("bujin_hai", "yaoshi_jiu", "yinci", "youyu"),     # 不光 不仅 另外 要是 因此 …
    "g4-22": ("shenmede",),                                     # 等 者 之 就是
    "g4-23": (),                                                # 啊、嗯
    "g4-24": (),                                                # 一小盒
    "g4-25": (),                                                # 一A一B
    "g4-26": (),                                                # 无A无B
    "g4-27": (),                                                # 有A有B
    "g4-28": ("pot_de",),                                       # 来得及 / 来不及
    "g4-29": (),                                                # 有的是
    "g4-30": (),                                                # 说不定
    "g4-31": ("bu_zenme",),                                     # 不怎么
    "g4-32": (),                                                # 就是说
    "g4-33": ("yi_bi_yi",),                                     # 一天比一天
    "g4-34": ("zai_shang_xia",),                                # 在……方面
    "g4-35": ("gou_de",),                                       # 够……的
    "g4-36": (),                                                # 拿……来说
    "g4-37": ("zai_ye_bu",),                                    # 再也不/没
    "g4-38": ("zenme_ye_bu",),                                  # 怎么都/也不
    "g4-39": ("weile_er",),                                     # 为了……而……
    "g4-40": (),                                                # 过一天是一天
    "g4-41": ("you_shenme_hao",),                               # 有什么好X的
    "g4-42": (),                                                # X是X，Y是Y
    "g4-43": (),                                                # X也得X，不X也得X
    "g4-44": (),                                                # X就是了
    "g4-45": ("hai_surprise",),                                 # 还X呢
    "g4-46": (),                                                # 你X你的吧
    "g4-47": (),                                                # 让你X你就X
    "g4-48": (),                                                # 说什么也得X
    "g4-49": (),                                                # X就X吧
    "g4-50": ("x_shi_x",),                                      # X是X
    "g4-51": ("si_le",),                                        # 死了 / 厉害
    "g4-52": ("pot_liao",),                                     # 得了 / 不了
    "g4-53": ("rhetorical_q",),                                 # 难道……吗？
    "g4-54": ("rhetorical_q",),                                 # 谁不认识他？
    "g4-55": ("ba_basic",),                                     # 把 + V一V
    "g4-56": ("ba_le",),                                        # 把 + V了
    "g4-57": ("ba_quantity",),                                  # 把 + amount
    "g4-58": ("ba_basic", "ba_required"),                       # 把 + adverbial + V
    "g4-59": ("bei_rang_jiao",),                                # 叫/让 passive
    "g4-60": ("jianyu_causative",),                             # 表扬我取得了好成绩
    "g4-61": ("jianyu_causative",),                             # 选我做组长
    "g4-62": ("jianyu_causative",),                             # 使我改变
    "g4-63": ("buru",),                                         # A不如B
    "g4-64": ("gen_xiangbi",),                                  # 跟……相比
    "g4-65": ("double_neg",),
    "g4-66": ("bushi_ershi",),
    "g4-67": ("ji_you",),
    "g4-68": ("yifangmian",),
    "g4-69": ("shouxian_qici",),
    "g4-70": ("shouxian_qici",),
    "g4-71": ("yushi",),
    "g4-72": ("shenzhi",),
    "g4-73": ("bujin_hai", "budan_erqie"),
    "g4-74": ("budan_erqie",),
    "g4-75": ("lian_dou",),
    "g4-76": ("bushi_jiushi",),
    "g4-77": ("jinguan",),
    "g4-78": ("danshi",),                                       # 然而
    "g4-79": ("buguo",),
    "g4-80": ("x_shi_x",),
    "g4-81": ("fouze",),
    "g4-82": ("yaoshi_jiu",),
    "g4-83": ("yaoshi_jiu", "fouze"),
    "g4-84": ("buguan_dou",),
    "g4-85": ("wulun_dou",),
    "g4-86": ("jiran_jiu",),
    "g4-87": ("youyu", "yinci"),
    "g4-88": ("hao_purpose",),
    "g4-89": ("jishi_ye",),
    "g4-90": ("jiusuan_ye",),                                   # 就是……也……
    "g4-91": (),                                                # 你着急你先走吧
    "g4-92": ("jishi_ye",),                                     # 不睡觉也要写完
    "g4-93": ("num_lai",),
    "g4-94": ("dayue", "zuoyou"),
    "g4-95": ("fractions",),
}

LEXICAL = {
    "g4-02": "各 (each), 任何 (any), 此 (this, written) — vocabulary; 任何 + noun + 都 works "
             "like 都.",
    "g4-04": "一脸 / 满脸 (a face full of: 满脸高兴) — set expressions.",
    "g4-10": "故意 (on purpose), 互相 (each other) — vocabulary.",
    "g4-23": "啊 / 嗯 as interjections (ah!, mm) — vocabulary.",
    "g4-24": "Number + 大 / 小 + measure word (一小盒, a small box) — met in reading.",
    "g4-25": "一A一B (一字一句, word by word) — four-character set phrases.",
    "g4-26": "无A无B (无日无夜, day and night) — four-character set phrases.",
    "g4-27": "有A有B (有说有笑, chatting and laughing) — four-character set phrases.",
    "g4-29": "有的是 (there's plenty of) — a set phrase.",
    "g4-30": "说不定 (maybe, can't say) — a set phrase.",
    "g4-32": "就是说 (that is to say) — a set phrase.",
    "g4-36": "拿……来说 (take … for example) — a set phrase.",
    "g4-40": "过一天是一天 (take each day as it comes) — a set saying.",
    "g4-42": "X是X，Y是Y (他是他，我是我 — he's him, I'm me) — a set saying.",
    "g4-43": "去也得去，不去也得去 (you have to go either way) — a set saying.",
    "g4-44": "X就是了 (just do X) — spoken set phrase.",
    "g4-46": "你忙你的吧 (carry on with what you're doing) — spoken set phrase.",
    "g4-47": "让你拿着你就拿着 (just take it when told) — spoken set phrase.",
    "g4-48": "说什么也得去 (have to go no matter what) — spoken set phrase.",
    "g4-49": "买就买吧 (buy it then, fine) — spoken set phrase.",
    "g4-91": "Two clauses run together with no linking word (站得高看得远) — met in reading.",
}

LEARN = {
    "gan": (
        "敢 + verb = dare: 我不敢开快车 (I don't dare drive fast), 你敢不敢？",
        "It's about courage; 'can' for ability is 会 / 能."),
    "youqi": (
        "尤其(是) = especially, picking one out: 我喜欢水果，尤其是榴莲.",
        "It points at one item of a group mentioned first."),
    "shaowei": (
        "稍微 + verb + 一下 / adjective + 一点 = just slightly: 稍微等一下, 稍微便宜一点.",
        "It needs the small amount after it: 稍微便宜 ✗."),
    "dou_vs_quan": (
        "都 = all (adverb, before the verb); 全 = whole / entirely: 全家 (the whole family), 全都"
        "来了.",
        "全 can go before a noun; 都 can't."),
    "guang_jiu": (
        "光 A 就 B = just A alone is B: 光车票就要一百块 (the ticket alone costs a hundred).",
        "光 here means 'only / alone', not 'light'."),
    "zhishao_zuiduo": (
        "至少 = at least, 最多 / 至多 = at most: 至少要三天 (at least three days).",
        "They go before the amount or the verb."),
    "conglai_bu": (
        "从来不 + verb = never (as a habit): 他从来不喝酒.",
        "For past experience use 从来没 … 过."),
    "conglai_mei": (
        "从来没(有) + verb + 过 = have never ever: 我从来没去过日本.",
        "Keep the 过."),
    "yuanlai": (
        "原来 = it turns out (原来是你！) or originally (我原来住在怡保).",
        "As 'it turns out' it starts the sentence."),
    "que_but": (
        "Subject + 却 + verb = yet, but unexpectedly: 东西便宜，质量却不好.",
        "却 goes after the subject, never at the start like 但是."),
    "cai_ne": (
        "才 + … + 呢 insists: 我才不去呢! (I'm certainly not going!), 这里的菜才好吃呢!",
        "Emotional, spoken; keep the 呢."),
    "bing_bu": (
        "并不 / 并没 = actually not (correcting an assumption): 这并不难 (it isn't actually hard).",
        "Use it when someone thinks the opposite."),
    "hai_surprise": (
        "还 + X + 呢 mocks or stresses: 还大公司呢，服务这么差 (call that a big company?).",
        "Not 'still' here — it's sarcasm or surprise."),
    "jingran": (
        "竟然 / 居然 = unexpectedly, would you believe: 他竟然忘了 (he actually forgot!).",
        "It goes before the verb, showing surprise."),
    "daodi": (
        "到底 / 究竟 in a question = … on earth: 你到底去不去？ In a statement 到底 = in the end: "
        "他到底来了.",
        "No 吗 with it: 你到底去吗？ ✗ → 你到底去不去？"),
    "zhihao": (
        "只好 + verb = have no choice but: 没有巴士，我只好走路.",
        "It's a reluctant decision, not 'only'."),
    "chadian": (
        "差点 / 差一点 + verb = almost (but didn't): 我差点迟到 (I was nearly late).",
        "差点没迟到 also means 'nearly late' — the 没 doesn't flip it for bad things."),
    "suizhe": (
        "随着 + change = as … (changes): 随着天气变冷，生病的人多了.",
        "It goes at the start, with a change after it."),
    "de_shihou": (
        "Clause + 的时候 = when / while: 我吃饭的时候 (when I eat). 当 … 的时候 is the fuller form.",
        "The time clause goes first, before the main one."),
    "bei_rang_jiao": (
        "叫 / 让 + doer + verb + result = spoken passive: 我的自行车让朋友借走了.",
        "With 叫 / 让 the doer must be said: 让借走了 ✗."),
    "youyu": (
        "由于 … (所以 / 因此) … = owing to, because (more formal): 由于下雨，比赛取消了.",
        "Pair it with 因此 or 所以, not with 因为."),
    "duiyu": (
        "对于 + topic = regarding, as for: 对于这个问题，我有不同的看法.",
        "It goes at the start; 对 can do the same in speech."),
    "guanyu_vs_duiyu": (
        "关于 = about (the topic of: 一本关于槟城的书) ↔ 对于 = regarding, towards (an attitude: 对于"
        "他的意见，我同意).",
        "关于 can't go after the subject; 对于 can."),
    "anzhao": (
        "按照 / 按 + rule / plan = according to: 按照规定 (as the rules say), 按时 (on time).",
        "For a source of information use 根据."),
    "er_contrast": (
        "而 = while, whereas (formal): 南方人喜欢吃米饭，而北方人喜欢吃面.",
        "Written style; in speech 可是 / 但是."),
    "jiran_jiu": (
        "既然 A，就 B = since A (given that), then B: 既然你来了，就吃饭吧.",
        "A is already known; for a cause you're explaining use 因为."),
    "shenzhi": (
        "甚至 = even (going further): 他很忙，甚至没时间吃饭.",
        "It adds the most extreme point."),
    "buguo": (
        "不过 = but, however (softer than 但是): 好吃，不过有点贵.",
        "It starts the second clause."),
    "bujin_hai": (
        "不仅 / 不光 A，还 / 而且 B = not only A but also B: 他不仅会做菜，还会做面包.",
        "Like 不但 … 而且, a bit more formal."),
    "yaoshi_jiu": (
        "要是 A，就 B = if (spoken): 要是你有空，就来玩.",
        "Same as 如果 … 就, but more casual."),
    "yinci": (
        "因此 = therefore (formal): 他生病了，因此没来.",
        "It starts the result clause."),
    "bu_zenme": (
        "不怎么 + verb / adjective = not very, not much: 不怎么好吃, 我不怎么看电视.",
        "不怎么样 (at the end) = not up to much."),
    "yi_bi_yi": (
        "一天比一天 / 一次比一次 + adjective = more each day / time: 天气一天比一天热.",
        "No 很 or 更 after it."),
    "gou_de": (
        "(真)够 + adjective + 的 = really quite: 今天真够热的!",
        "Keep the 的 at the end."),
    "zai_ye_bu": (
        "再也不 + verb = never again (future): 我再也不迟到了. 再也没 + verb = never again since: "
        "我再也没见过他.",
        "Keep 再也 together before 不 / 没."),
    "zenme_ye_bu": (
        "怎么也 / 怎么都 + 不 / 没 = no matter how, it just won't: 怎么也睡不着 (just can't sleep).",
        "The 怎么 goes before 也 / 都."),
    "weile_er": (
        "为了 A 而 B = do B for A (written): 为了梦想而努力.",
        "而 links the purpose and the action; speech drops it."),
    "you_shenme_hao": (
        "有什么好 + verb + 的？ = what's there to …?: 有什么好怕的？ (what's there to be afraid of?).",
        "It means there's no reason — not a real question."),
    "x_shi_x": (
        "X 是 X，就是 / 不过 … = it is X, but …: 便宜是便宜，就是质量不好.",
        "Both sides of 是 are the same word."),
    "si_le": (
        "Adjective / feeling + 死了 = terribly (spoken): 累死了, 热死了. 疼得厉害 = hurts a lot.",
        "Only for states and feelings, not actions."),
    "pot_liao": (
        "Verb + 得了 / 不了 (liǎo) = can / can't manage at all: 吃不了 (can't eat all that), 我去不"
        "了 (I can't make it).",
        "This 了 is liǎo, not the le of completion."),
    "ba_quantity": (
        "把 + thing + verb + how much: 把课文读了两遍 (read the text twice), 把他批评了一顿.",
        "The amount goes after the verb."),
    "ba_required": (
        "Some sentences need 把: putting something somewhere (把书放在桌上), turning it into "
        "something (把美元换成马币).",
        "Without 把 they sound wrong: 放书在桌上 ✗."),
    "buru": (
        "A 不如 B (+ adjective) = A isn't as good as B: 打车不如坐地铁快.",
        "The better one is B, after 不如."),
    "gen_xiangbi": (
        "跟 / 和 B 相比，A … = compared with B: 跟去年相比，今年更热.",
        "The comparison goes first; then 更 / 多了."),
    "double_neg": (
        "Two negatives make a strong yes: 没有人不喜欢 (everyone likes it), 我不得不走 (I have to go).",
        "They cancel — don't read them as a no."),
    "bushi_ershi": (
        "不是 A，而是 B = not A, but B: 不是我不想去，而是没有时间.",
        "It corrects the reason; 不是 … 就是 is 'either … or'."),
    "ji_you": (
        "既 A 又 / 也 B = both A and B (more formal): 既好喝，又健康.",
        "Like 又 … 又, with 既 first."),
    "yifangmian": (
        "一方面 A，另一方面 B = on one hand … on the other: 一方面省钱，另一方面对身体好.",
        "Both sides usually support the same point."),
    "lian_dou": (
        "连 + extreme case + 都 / 也 = even: 连他都知道 (even he knows), 他连饭都没吃.",
        "The extreme case goes between 连 and 都."),
    "shouxian_qici": (
        "首先 … 其次 … = first …, second … (points); 首先 … 然后 … (steps).",
        "Used for explaining or listing, a bit formal."),
    "yushi": (
        "……，于是 … = so, and then (in a story): 下雨了，于是我们回家.",
        "For past events; for advice use 所以."),
    "bushi_jiushi": (
        "不是 A，就是 B = either A or B, always one: 他不是在家，就是在公司.",
        "Not 不是 … 而是 (not A but B)."),
    "jinguan": (
        "尽管 A，但是 / 还是 B = even though A, B: 尽管很累，他还是来了.",
        "A is a real fact; for 'even if' use 即使."),
    "fouze": (
        "……，否则 … = otherwise: 快点走，否则来不及了. Spoken: 不然.",
        "It introduces the bad result of not doing it."),
    "buguan_dou": (
        "不管 + question word …，都 / 也 … = no matter: 不管你说什么，我都不去.",
        "It needs a question word or A-not-A after 不管."),
    "wulun_dou": (
        "无论 + question word …，都 / 也 … = no matter (more formal): 无论多忙，他都来.",
        "Same as 不管, written style."),
    "hao_purpose": (
        "……，好 + verb = so that: 写下来，好记住 (write it down so you remember), 好让他放心.",
        "Here 好 isn't 'good'."),
    "jishi_ye": (
        "即使 A，也 B = even if A, B: 即使下雨，我也去.",
        "A is a hypothesis; for a real fact use 尽管 / 虽然."),
    "jiusuan_ye": (
        "就算 / 就是 A，也 B = even if (spoken): 你就是不同意，我也要去.",
        "Like 即使 … 也, more casual."),
    "num_lai": (
        "Round number + 来 + measure word = about: 二十来岁 (about twenty), 一百来块.",
        "Only after round numbers (十, 二十, 一百)."),
    "zuoyou": (
        "Amount + 左右 = or so: 三十岁左右, 八点左右.",
        "It goes after the amount; 大约 / 大概 go before."),
    "fractions": (
        "3.5 = 三点五; 1/3 = 三分之一 (bottom first); 20% = 百分之二十; twice = 两倍. 打八折 = 20% off.",
        "Fractions say the bottom number first."),
}
