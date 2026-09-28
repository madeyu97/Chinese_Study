# src/grammar_data_1.py
"""Grammar curriculum, groups 1-3: sentence architecture, negation, questions."""

from grammar_schema import Structure

SECTIONS = {
    1: "Basic Sentence Architecture",
    2: "Basic Negation",
    3: "Questions",
}

_S = Structure
STRUCTURES = [
    # ------------------------------------------------------------------
    # 1. Basic sentence architecture
    # ------------------------------------------------------------------
    _S("word_order", 1, "Basic word order", "主语 + 动词 + 宾语",
       "Say who does what: the subject, then the action, then what it acts on.",
       notes="Drill that meaning comes from order, not endings: 我找你 vs 你找我. "
             "Swap subject and object to change who does what. Keep sentences very "
             "short. No tense words needed.",
       level=1, core=True),
    _S("time_before_verb", 1, "Time before the verb", "今天我…… / 我今天……",
       "Time words go before the action, never after it.",
       notes="Point-in-time words (今天, 八点, 上个礼拜, 拜六) sit before the verb, "
             "either before or after the subject. Do not confuse with duration, which "
             "follows the verb (等了十分钟) - that belongs to a later structure, so "
             "only use points in time here.",
       level=1, core=True),
    _S("place_before_verb", 1, "Place before the verb", "在 + 地方 + 动词",
       "Where an activity happens goes before the action.",
       notes="在 + place + verb: 我在巴刹买菜. English order is the reverse, which is "
             "the error to train out. Keep to where an activity takes place (not "
             "where something ends up, which is V + 在 + place, a later structure).",
       markers=("在",), level=1, core=True),
    _S("time_place_order", 1, "Subject + time + place + verb + object",
       "我 + 明天 + 在家 + 看书",
       "Put when first, then where, then the action.",
       notes="Order is: subject, time, place (在 + place), verb, object. Time may also "
             "come before the subject (明天我在家看书). Place never goes at the end "
             "for the location of an activity (NOT 我看书在家).",
       contrast=("time_before_verb", "place_before_verb"), markers=("在",),
       level=1, core=True),
    _S("topic_comment", 1, "Topic + comment", "这本书，我看过。",
       "Name what you are talking about first, then say something about it.",
       notes="Front the topic, then comment: 这个菜，我不吃. / 榴莲，我很喜欢. / 那家店，"
             "东西很便宜. Very common in speech. The topic can be an object moved to "
             "the front. Identify tasks: what is the sentence about?",
       level=2, core=True, also_in=(28, 35)),
    _S("subject_omission", 1, "Leaving out the subject", "（我）吃饱了。",
       "Drop the subject when it is obvious who you mean.",
       notes="In replies and continuing talk the subject disappears: A: 你吃了吗？ B: "
             "吃了。 Drill hearing who is meant from context, and answering without "
             "repeating the subject. Natural short exchanges.",
       level=2, core=True, also_in=(35,)),
    _S("object_omission", 1, "Leaving out the object", "你买了没有？——买了。",
       "Drop the object when both people know what it is.",
       notes="Chinese drops a known object where English needs 'it': 你看了那部戏吗？"
             "——看了。 (not 看了它). Drill replies that omit the object; never add 它 "
             "for things in these replies.",
       level=2, core=True, also_in=(35,)),
    _S("shi_identity", 1, "是 — this is that", "A 是 B",
       "Link two nouns: say what or who something is.",
       notes="是 joins noun to noun (他是老师, 这是我的锁匙). It is NOT used before "
             "adjectives (NOT 他是高). Negative is 不是.",
       contrast=("adj_predicate",), markers=("是",), level=1),
    _S("you_exist", 1, "有 — there is / have", "（地方 / 人）+ 有 + 东西",
       "Say what someone has, or what is somewhere.",
       notes="Possession (我有两个孩子) and existence (巴刹有很多菜). Negative is always "
             "没有, never 不有.",
       contrast=("meiyou_absence", "shi_identity"), markers=("有",), level=1),
    _S("meiyou_absence", 1, "没有 — don't have / there isn't", "没有 + 东西",
       "Say someone doesn't have something, or it isn't there.",
       notes="没有 negates 有 (我没有钱 / 冰厨里没有水). Never 不有. Keep separate from "
             "没(有) + verb (didn't do), which belongs to negation.",
       contrast=("you_exist",), markers=("没有", "没"), level=1),
    _S("shibushi", 1, "是不是 — checking a guess", "……，是不是？ / 是不是……？",
       "Check whether what you think is true.",
       notes="Used when you already suspect the answer: 你累了，是不是？ / 是不是要下雨了？"
             " Contrast with a neutral 吗 question.",
       contrast=("ma_question",), markers=("是不是",), level=2, core=True,
       also_in=(3, 29, 35)),
    _S("de_possessive", 1, "的 — possession and description", "我的朋友 / 马来西亚的菜",
       "Link an owner or description to a noun.",
       notes="的 marks 'of / 's' (我的手机, 老师的车). With close family and relations "
             "的 is usually dropped (我妈妈, 我们公司). Drill both.",
       markers=("的",), level=1, core=True),
    _S("de_nominal", 1, "的 — 'the one that…'", "红的 / 我买的 / 他说的",
       "Turn a description into a noun: the red one, the one I bought.",
       notes="Noun left out after 的: 我要大的. / 这是我买的. / 他说的不对. Identify "
             "tasks: what does 的 stand for here?",
       markers=("的",), level=2, core=True, also_in=(20,)),
    _S("de_final", 1, "Sentence-final 的 — certainty / explanation", "我知道的。 / 他会来的。",
       "A final 的 makes a statement sound certain or matter-of-fact.",
       notes="会……的 = 'will surely' (放心，他会来的). 我知道的 = 'I do know'. Keep "
             "apart from 是……的 (focus on how/when/where), a later structure.",
       markers=("的",), level=3, also_in=(28,)),
    _S("de_de_de", 1, "的 / 得 / 地", "我的书 · 跑得快 · 慢慢地走",
       "Tell the three 'de' apart by what they do.",
       notes="All three sound the same, so identification must be done from the "
             "written sentence (mark those items read: true). 的 before a noun, 得 "
             "after a verb introducing how well/how much, 地 before a verb describing "
             "how it is done. Focus on function, not terminology.",
       contrast=("de_possessive", "deg_de", "de_manner"),
       markers=("的", "得", "地"), level=2, core=True, kind="contrast",
       also_in=(14, 30)),
    _S("adj_predicate", 1, "Adjective as the predicate", "天气很热。",
       "Describe something with an adjective — no 是 needed.",
       notes="Adjectives act as verbs: 这个很贵 (NOT 这个是贵). Negate with 不 "
             "(不贵). Contrast with 是 + noun.",
       contrast=("shi_identity", "hen_adj"), level=1),
    _S("hen_adj", 1, "很 + adjective", "很 + 形容词",
       "Use 很 to state a quality plainly — it is weaker than English 'very'.",
       notes="很 is often just the link: 我很好 = I'm fine. A bare adjective sounds "
             "like a comparison (这个贵，那个便宜). Stressed 很 does mean 'very'. "
             "Malaysian 蛮 (quite) is also common.",
       markers=("很",), level=1, also_in=(14,)),
    _S("adj_de_noun", 1, "Adjective + (的) + noun", "好吃的菜 / 新衣服",
       "Describe a noun by putting the adjective in front.",
       notes="Two-syllable or modified adjectives take 的 (漂亮的衣服, 很大的房子); "
             "common one-syllable ones usually don't (新车, 好人, 大房子).",
       level=1, also_in=(20,)),
    _S("adverb_verb", 1, "Adverb + verb", "也 / 都 / 常常 / 已经 + 动词",
       "Adverbs go before the verb they describe.",
       notes="也, 都, 常常, 还, 已经, 马上 all come before the verb (我也去, 我们都喜欢). "
             "Common error: putting them at the start or end like English.",
       level=1),
    _S("modal_verb", 1, "Modal verb + verb", "想 / 会 / 能 / 可以 / 要 + 动词",
       "Add want, can, may or will in front of the action.",
       notes="Modal directly before the main verb (我想去, 你可以坐). Negate the modal "
             "(不想去, 不能来). Detailed differences between modals come later; here "
             "drill the word order.",
       level=1, core=True, also_in=(8,)),
    _S("double_object", 1, "Give someone something", "给 / 送 / 教 / 问 + 人 + 东西",
       "Say who receives something, then what.",
       notes="Verb + person + thing: 他给我一本书 / 老师教我们华语 / 我问你一个问题. "
             "Person always before the thing.",
       level=2, also_in=(24,)),
    _S("v_person_place", 1, "Take someone somewhere", "送 / 载 / 带 + 人 + 去 / 到 + 地方",
       "Say you are taking, sending or driving someone somewhere.",
       notes="The syllabus lists 'verb + object + location'. The natural pattern is "
             "verb + person + 去/到 + place: 我载你去银行 (Malaysian 载 = give a ride), "
             "送他到机场, 带孩子去公园. Do NOT produce 放书在桌子上 - putting a thing "
             "somewhere needs 把 or 书放在桌子上 (later structures).",
       markers=("去", "到"), level=2),
    _S("v_obj_quantity", 1, "Verb + object + how many times / how long",
       "我找了你三次。 / 我等了他一个钟头。",
       "Say how many times or how long you did something to someone.",
       notes="With a pronoun or person object, the amount follows the object "
             "(找了你三次, 等了他半个钟头). With an ordinary thing it usually comes "
             "before (看了两次戏). Drill mainly the pronoun case.",
       level=3, also_in=(7,)),

    # ------------------------------------------------------------------
    # 2. Basic negation
    # ------------------------------------------------------------------
    _S("bu_neg", 2, "不 — not (habits, states, intentions)", "不 + 动词 / 形容词",
       "Say you don't do something, won't do it, or something isn't so.",
       notes="不 for habits (我不喝咖啡), states and adjectives (不贵), and "
             "intentions/future (明天我不去). Also with 是, 会, 想, 要.",
       contrast=("mei_neg",), markers=("不",), level=1, core=True),
    _S("mei_neg", 2, "没 / 没有 — didn't / hasn't", "没(有) + 动词",
       "Say something didn't happen or hasn't happened yet.",
       notes="没 for events that did not occur (我昨天没去) and have not occurred yet "
             "(他还没来). No 了 after the verb (NOT 我没去了) - except after a length of time: 我三天没睡了 (haven't slept for three days) is correct. Not 'past tense 不'.",
       contrast=("bu_neg",), markers=("没",), level=1, core=True),
    _S("bu_vs_mei", 2, "不 vs 没", "不去 ↔ 没去",
       "Choose between 'don't / won't' and 'didn't / haven't'.",
       notes="Pair drill. 不去 = won't go / don't go; 没去 = didn't go. 不是 always "
             "(never 没是); 没有 always (never 不有). Minimal pairs heard aloud, and "
             "meaning-choice tasks.",
       contrast=("bu_neg", "mei_neg"), markers=("不", "没"), level=1, core=True,
       kind="contrast", also_in=(30,)),
    _S("bie", 2, "别 — don't!", "别 + 动词",
       "Tell someone not to do something.",
       notes="Direct negative command: 别走! / 别担心. Softer with 啦 in Malaysia "
             "(别担心啦). Contrast with 不要 (similar as a command, but 不要 can also "
             "mean 'don't want').",
       contrast=("buyao",), markers=("别",), level=1),
    _S("buyao", 2, "不要 — don't / shouldn't / don't want", "不要 + 动词",
       "Tell someone not to do something, or say you don't want it.",
       notes="As a command = 别 (不要跑!). With a noun or plain verb it can be "
             "'don't want' (我不要辣). Drill hearing which meaning is intended.",
       contrast=("bie",), markers=("不要",), level=1),
    _S("conglai_bu", 2, "从来不 — never (as a habit or rule)", "从来不 + 动词",
       "Say you never do something as a habit.",
       notes="从来不 = never, as a rule (我从来不抽烟). Contrast with 从来没……过 "
             "= have never once (我从来没去过怡保).",
       contrast=("conglai_mei",), markers=("从来不",), level=2),
    _S("conglai_mei", 2, "从来没(有)……过 — have never", "从来没 + 动词 + 过",
       "Say you have never once done something.",
       notes="Experience never had: 我从来没吃过榴莲. Usually with 过. Contrast with "
             "从来不 (habit).",
       contrast=("conglai_bu",), markers=("从来没",), level=2),
    _S("yidian_bu", 2, "一点也不 / 一点都不 — not at all", "一点也不 + 形容词",
       "Say something is not the case at all.",
       notes="Strong negation of an adjective or verb: 一点也不累 / 一点都不贵. Also "
             "with 没: 一点也没变. Never write 一点儿. Contrast with 有点 (a bit) is a "
             "later pair.",
       markers=("一点也不", "一点都不", "一点也没", "一点都没"), level=2, also_in=(14, 17)),
    _S("shenme_dou_bu", 2, "什么都不 / 什么都没 — nothing", "什么都不 + 动词",
       "Say you don't (or didn't) do anything at all.",
       notes="Question word + 都/也 + negative = none at all: 我什么都不想吃 / 他什么都"
             "没说. 都 and 也 both fine.",
       markers=("什么都", "什么也"), level=2, also_in=(17,)),
    _S("shei_dou_bu", 2, "谁都不 — nobody", "谁都不 + 动词",
       "Say nobody does something.",
       notes="谁都不知道 / 谁也没来. Can also be positive (谁都知道 = everybody knows); "
             "keep the negative focus here.",
       markers=("谁都", "谁也"), level=2, also_in=(17,)),
    _S("nali_dou_bu", 2, "哪里都不 — nowhere", "哪里都不 + 去",
       "Say you are going (or went) nowhere.",
       notes="我今天哪里都不去 / 他哪里都没去过. Malaysian 哪里, never 哪儿.",
       markers=("哪里都", "哪里也"), level=2, also_in=(17,)),
    _S("zenme_ye_bu", 2, "怎么也不 — no matter how (it just won't)", "怎么也 + 不 / 没 + 动词",
       "Say something won't happen however hard you try.",
       notes="Usually with a result: 怎么也睡不着 / 怎么也找不到锁匙 / 他怎么也不肯说. "
             "Stress the effort that fails.",
       markers=("怎么也", "怎么都"), level=3, also_in=(17,)),

    # ------------------------------------------------------------------
    # 3. Questions
    # ------------------------------------------------------------------
    _S("ma_question", 3, "吗 — yes/no questions", "…… 吗？",
       "Turn a statement into a yes/no question.",
       notes="Add 吗 to a statement (你饿吗？). Answer by repeating the verb or "
             "adjective (饿 / 不饿), not 'yes/no'. No 吗 on A-not-A or question-word "
             "questions.",
       contrast=("a_not_a", "shibushi"), markers=("吗",), level=1, core=True,
       also_in=(28,)),
    _S("ne_followup", 3, "呢 — 'and you?' / 'where's…?'", "你呢？ / 我的手机呢？",
       "Bounce a question back, or ask where something has got to.",
       notes="我很好，你呢？ = and you? / 锁匙呢？ = where are the keys? Also softens "
             "a question-word question (你去哪里呢？). The ongoing-state 呢 belongs to "
             "a later structure.",
       markers=("呢",), level=1, also_in=(28, 29)),
    _S("a_not_a", 3, "A-not-A questions", "去不去？ / 好不好吃？ / 喜不喜欢？",
       "Ask yes-or-no by saying both options.",
       notes="Verb/adjective + 不 + verb/adjective, no 吗. Two-syllable words often "
             "shorten the first half (喜不喜欢). 有 takes 没 (有没有). Very common in "
             "speech.",
       contrast=("ma_question",), level=1, core=True, also_in=(29, 35)),
    _S("you_mei_you", 3, "有没有 — is there? / have you?", "有没有 + 东西 / 动词",
       "Ask whether something exists, or whether something happened.",
       notes="有没有锁匙？ = have you got the keys? / 你有没有去过槟城？ = have you ever "
             "been. No 吗.",
       markers=("有没有",), level=1, also_in=(29,)),
    _S("shei", 3, "谁 — who", "谁 + 动词？",
       "Ask who.",
       notes="In the position of the answer (谁来了？ / 你找谁？). Also 谁的 = whose.",
       markers=("谁",), level=1, core=True),
    _S("shenme", 3, "什么 — what", "什么 / 什么 + 名词",
       "Ask what, or what kind of thing.",
       notes="Object position (你吃什么？) or before a noun (什么菜？). No 吗.",
       markers=("什么",), level=1, core=True),
    _S("nage", 3, "哪个 / 哪 + measure — which", "哪个 / 哪本 / 哪天",
       "Ask which one.",
       notes="哪 + measure word + noun: 哪个人, 哪家店, 哪天. Pinyin nǎ; 哪里 is "
             "'where'.",
       markers=("哪",), level=1, core=True),
    _S("nali", 3, "哪里 — where", "在哪里？ / 去哪里？",
       "Ask where.",
       notes="Malaysian 哪里, never 哪儿. 在哪里 for location, 去哪里 for "
             "destination.",
       markers=("哪里",), level=1, core=True),
    _S("shenme_shihou", 3, "什么时候 / 几时 — when", "什么时候 + 动词？",
       "Ask when something happens.",
       notes="Before the verb (你什么时候来？). Malaysian colloquial 几时 means the "
             "same (你几时回来？); drill both.",
       markers=("什么时候", "几时"), level=1, core=True),
    _S("weishenme", 3, "为什么 — why", "为什么 + 动词？",
       "Ask why.",
       notes="Before the verb (你为什么不来？). Malaysian colloquial 做么 (zomok) also "
             "means why / how come.",
       markers=("为什么", "做么"), level=1, core=True),
    _S("zenme", 3, "怎么 — how / how come", "怎么 + 动词？",
       "Ask how to do something, or how come something happened.",
       notes="怎么走？ = how do I get there? / 你怎么没来？ = how come you didn't come? "
             "(surprise). Drill hearing which meaning is intended.",
       contrast=("zenmeyang",), markers=("怎么",), level=1, core=True),
    _S("zenmeyang", 3, "怎么样 — how is it? / how about…?", "……怎么样？",
       "Ask what something is like, or suggest something.",
       notes="At the end: 这家店怎么样？ = what's it like? / 我们去吃饭，怎么样？ = how "
             "about it? Contrast with 怎么 + verb (how to).",
       contrast=("zenme",), markers=("怎么样",), level=1, also_in=(29,)),
    _S("ji_howmany", 3, "几 — how many (a few)", "几 + 量词 + 名词？",
       "Ask how many when you expect a small number.",
       notes="Needs a measure word (几个人？ / 几天？). Expected answer under about ten. "
             "Contrast with 多少.",
       contrast=("duoshao",), markers=("几",), level=1, core=True, also_in=(4,)),
    _S("duoshao", 3, "多少 — how much / how many", "多少 + (量词) + 名词？ / 多少钱？",
       "Ask how much or how many, with no limit on the number.",
       notes="Any number, measure word optional (多少人？). 多少钱 for prices. "
             "Contrast with 几.",
       contrast=("ji_howmany",), markers=("多少",), level=1, core=True, also_in=(4,)),
    _S("duo_adj", 3, "多 + adjective — how (tall / far / old)?", "多高？ / 多远？ / 多大？",
       "Ask how big, far, tall or old something is.",
       notes="多 + adjective (你家离这里多远？). 多大 asks age or size (你孩子多大了？). "
             "Answers give the measurement.",
       markers=("多",), level=2),
    _S("duojiu", 3, "多久 / 几久 — how long", "多久 / 多长时间",
       "Ask how long something takes or lasts.",
       notes="Duration questions: 你学华语多久了？ / 要多长时间？ Malaysian 几久 is very "
             "common (要几久？). Covers 多长时间.",
       markers=("多久", "几久", "多长时间"), level=2),
    _S("jidian", 3, "几点 — what time", "几点 + 动词？",
       "Ask what time something happens.",
       notes="现在几点？ / 你几点放工？ Time before the verb. Malaysian clock talk "
             "(八点三个字 = 8:15) is fine in answers.",
       markers=("几点",), level=1),
    _S("what_kind", 3, "什么样的 / 哪种 — what kind of", "什么样的 + 名词？ / 哪一种？",
       "Ask what kind or sort of thing.",
       notes="你喜欢什么样的菜？ / 你要哪一种？",
       markers=("什么样", "哪种", "哪一种"), level=2),
    _S("qword_position", 3, "Question words stay in place", "你去哪里？ (不是：哪里你去？)",
       "Ask by putting the question word where the answer would be.",
       notes="No fronting: 你找谁？ ↔ 我找老板. Drill building questions from answers "
             "and answers from questions.",
       level=1, core=True),
    _S("qword_indefinite", 3, "Question words meaning some- / any-", "想吃点什么 / 有谁来吗？",
       "Use 什么, 谁 and 哪 to mean something, someone or somewhere.",
       notes="Not a question: 我想买点什么 = I'd like to buy something / 有没有谁知道？ "
             "/ 哪天有空来玩. Identify tasks: is it a real question or 'some-'?",
       markers=("什么", "谁", "哪"), level=3),
]

# Every line of the syllabus, mapped to the structure that drills it.
LISTED = {
    1: [
        ("Basic S + V + O word order", "word_order"),
        ("Subject + Time + Place + Verb + Object", "time_place_order"),
        ("Time expressions before the verb", "time_before_verb"),
        ("Place expressions before the verb", "place_before_verb"),
        ("Topic + Comment sentences", "topic_comment"),
        ("Subject omission when context is clear", "subject_omission"),
        ("Object omission when context is clear", "object_omission"),
        ("是…… — identification / \"to be\"", "shi_identity"),
        ("有…… — existence / possession", "you_exist"),
        ("没有…… — non-existence / possession", "meiyou_absence"),
        ("是不是…… — confirmation", "shibushi"),
        ("的 — possession / attribution", "de_possessive"),
        ("的 — nominalisation", "de_nominal"),
        ("的 — emphasis / explanatory use", "de_final"),
        ("的 / 得 / 地 distinction", "de_de_de"),
        ("Adjective as predicate", "adj_predicate"),
        ("很 + adjective", "hen_adj"),
        ("Adjective + 的 + noun", "adj_de_noun"),
        ("Adverb + verb", "adverb_verb"),
        ("Modal verb + verb", "modal_verb"),
        ("Double-object constructions", "double_object"),
        ("Verb + object + location", "v_person_place"),
        ("Verb + object + quantity", "v_obj_quantity"),
    ],
    2: [
        ("不 — general/present/future negation", "bu_neg"),
        ("没 / 没有 — past/non-occurrence/absence", "mei_neg"),
        ("不 vs 没", "bu_vs_mei"),
        ("别 — negative imperative", "bie"),
        ("不要 — don't / should not", "buyao"),
        ("从来不…… — never", "conglai_bu"),
        ("从来没…… — have never", "conglai_mei"),
        ("一点也不…… — not at all", "yidian_bu"),
        ("什么都不…… — don't do/eat/etc. anything", "shenme_dou_bu"),
        ("谁都不…… — nobody…", "shei_dou_bu"),
        ("哪儿都不…… — nowhere…", "nali_dou_bu"),
        ("怎么也不…… — no matter how…not…", "zenme_ye_bu"),
    ],
    3: [
        ("吗 — yes/no questions", "ma_question"),
        ("呢 — follow-up / \"what about…?\" / ongoing question", "ne_followup"),
        ("A-not-A questions", "a_not_a"),
        ("是不是……？", "shibushi"),
        ("有没有……？", "you_mei_you"),
        ("V 不 V？", "a_not_a"),
        ("谁 — who", "shei"),
        ("什么 — what", "shenme"),
        ("哪个 — which", "nage"),
        ("哪儿 / 哪里 — where", "nali"),
        ("什么时候 — when", "shenme_shihou"),
        ("为什么 — why", "weishenme"),
        ("怎么 — how", "zenme"),
        ("怎么样 — how / what is it like", "zenmeyang"),
        ("几 — how many", "ji_howmany"),
        ("多少 — how much/many", "duoshao"),
        ("多 + adjective — how + adjective", "duo_adj"),
        ("多久 — how long", "duojiu"),
        ("多长时间 — how long", "duojiu"),
        ("多大 — how old/how big", "duo_adj"),
        ("几点 — what time", "jidian"),
        ("哪一种 / 什么样的 — what kind of", "what_kind"),
        ("Question-word position in Chinese", "qword_position"),
        ("Question words as indefinite words", "qword_indefinite"),
    ],
}
