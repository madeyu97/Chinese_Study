# src/hsk_grammar.py
"""
The HSK track's grammar: which drill structures teach each official HSK
grammar point, the order they're learnt in, and the "how it works" card
shown before a structure's first drill.

  MAP[point_id]   structure ids that teach an official point (data/hsk/
                  grammar.csv), or () for points that are vocabulary, not
                  grammar to drill - those are learnt in Anki and reading
  LEXICAL         why each () point isn't drilled
  LEARN[sid]      (how it works, the usual mistake) - learner-facing,
                  unlike Structure.notes, which guide the drill writer

A structure's HSK level is the lowest level of the points it teaches.
On the HSK track the drills come in HSK order (1 before 2 ...), and within
a level in the curriculum's own teaching order (core first; a contrast
pair waits for both halves).

HSK 1 is mapped here; HSK 2, 3 and 4 in hsk_grammar_2.py, _3.py and _4.py.
"""

import functools
import re

import grammar_curriculum as gc
import hsk
from dictionary_engine import has_erhua

MAP = {
    # morphemes and word classes
    "g1-01": ("di_ordinal",),                                   # 小—、第—
    "g1-02": (),                                                # —们、—边
    "g1-03": ("loc_words_1", "place_you"),                      # 上 下 里 外 前 后
    "g1-04": ("hui_can", "neng", "hui_neng_keyi"),              # 会、能
    "g1-05": ("xiang_want", "yao_want"),                        # 想、要
    "g1-06": ("keyi",),                                         # 可以
    "g1-07": ("lihe_verbs",),                                   # 睡觉、上班 …
    "g1-08": ("shei", "shenme", "nage", "nali", "zenme", "zenmeyang", "ji_howmany",
              "duoshao", "duo_adj", "qword_position"),          # question words
    "g1-09": (),                                                # 我 你 他 …
    "g1-10": ("zhe_na_mw",),                                    # 这 那 这些 …
    "g1-11": ("numbers",),                                      # 一 二/两 … 百 千
    "g1-12": ("num_mw_noun", "mw_ge", "mw_common"),             # 本 个 家 口 块 件 只 元
    "g1-13": ("num_mw_noun",),                                  # 杯
    "g1-14": ("date_time", "noun_predicate"),                   # 日 号 岁 点 分 年 天
    "g1-15": ("hen_adj", "feichang", "tai_le", "zhen_adj", "youdian"),
    "g1-16": ("dou_all",),                                      # 都
    "g1-17": ("zai_v", "zhengzai_v"),                           # 在、正在
    "g1-18": ("zai_again",),                                    # 再
    "g1-19": ("ye_also", "hai_also"),                           # 还、也
    "g1-20": ("bu_neg", "mei_neg", "bu_vs_mei", "buyao"),       # 不、没（有）、不要
    "g1-21": ("place_before_verb", "zai_place"),                # 在 + place
    "g1-22": ("gen_with", "dui_toward"),                        # 和 (with)、对
    "g1-23": ("he_and",),                                       # 和 (and)
    "g1-24": ("de_possessive", "adj_de_noun"),                  # 的
    "g1-25": ("le_verb",),                                      # 了1
    "g1-26": ("ba_particle", "le_final", "ma_question", "ne_followup", "ne_ongoing"),
    "g1-27": (),                                                # 喂
    # phrases and sentence parts
    "g1-28": ("he_and",),
    "g1-29": ("adj_de_noun", "de_possessive"),
    "g1-30": ("word_order",),
    "g1-31": ("word_order", "adj_predicate"),
    "g1-32": ("num_mw_noun",),
    "g1-33": ("place_before_verb", "gen_with", "dui_toward"),
    "g1-34": ("loc_words_1",),
    "g1-35": ("word_order",),
    "g1-36": ("noun_predicate",),
    "g1-37": ("word_order", "adj_predicate"),
    "g1-38": ("word_order",),
    "g1-39": ("adj_de_noun", "de_possessive", "num_mw_noun"),
    "g1-40": ("adverb_verb", "time_before_verb", "place_before_verb", "time_place_order"),
    "g1-41": ("v_yixia",),
    # sentence types
    "g1-42": ("word_order",),
    "g1-43": ("adj_predicate", "hen_adj"),
    "g1-44": ("noun_predicate",),
    "g1-45": (),
    "g1-46": (),
    "g1-47": ("ma_question", "short_answers"),
    "g1-48": ("qword_position",),
    "g1-49": ("a_not_a", "you_mei_you"),
    "g1-50": ("ba_particle", "buyao"),
    "g1-51": ("zhen_a", "tai_le"),
    "g1-52": ("shi_identity",),
    "g1-53": ("you_exist", "meiyou_absence"),
    "g1-54": ("place_shi",),
    "g1-55": ("place_you",),
    "g1-56": ("qu_v", "serial_verbs"),
    "g1-57": ("serial_verbs",),
    "g1-58": ("double_object",),
    "g1-59": (),
    "g1-60": ("ye_also",),
    "g1-61": ("hai_also",),
    # aspect and special expressions
    "g1-62": ("le_verb",),
    "g1-63": ("le_final",),
    "g1-64": ("zai_v", "zhengzai_v"),
    "g1-65": ("zhengzai_v", "ne_ongoing"),
    "g1-66": ("ne_ongoing",),
    "g1-67": ("money",),
    "g1-68": ("di_ordinal",),
    "g1-69": ("date_time",),
    "g1-70": ("date_time", "jidian"),
}

LEXICAL = {
    "g1-02": "们 and 边 are endings on words (我们 we, 旁边 beside) — learnt with the words.",
    "g1-09": "Pronouns (我 I, 你 you, 他 he …) — vocabulary.",
    "g1-27": "喂 (hello? on the phone) — vocabulary.",
    "g1-45": "One-word sentences (对不起 sorry, 下雨了 it's raining) — set phrases.",
    "g1-46": "Plain statements — every drill is one.",
    "g1-59": "Two clauses side by side with no linking word — met in every drill.",
}

# (how it works, the usual mistake). Chinese always with its English.
LEARN = {
    "word_order": (
        "Subject, verb, object — the same order as English: 我喝茶 (I drink tea). Chinese "
        "never changes the verb's form for person or tense; words around it do that job.",
        "Questions keep this order too: 你喝什么？ (what do you drink?), not 什么你喝？"),
    "time_before_verb": (
        "When something happens goes before the verb — at the very start or right after "
        "the subject: 我今天上班 / 今天我上班 (I'm working today).",
        "Never at the end the English way: 我上班今天 ✗."),
    "place_before_verb": (
        "Where you do something comes before the verb, as 在 + place: 我在家吃饭 (I eat at "
        "home).",
        "English puts the place last; Chinese doesn't: 我吃饭在家 ✗."),
    "time_place_order": (
        "Who → when → where → what: 我明天在家看书 (I'll read at home tomorrow). Big "
        "frame first, action last.",
        "Swapping where before when sounds off: 我在家明天看书 ✗."),
    "shi_identity": (
        "是 links two nouns: 我是老师 (I am a teacher). It's 'am / is / are' only between "
        "things or people.",
        "Never before an adjective: 我是很忙 ✗ — just 我很忙 (I'm busy)."),
    "you_exist": (
        "有 means both 'have' and 'there is': 我有哥哥 (I have an older brother), 楼下有"
        "银行 (there's a bank downstairs).",
        "The negative is 没有, never 不有."),
    "meiyou_absence": (
        "没有 + thing: don't have / there isn't: 我没有车 (I don't have a car).",
        "不有 doesn't exist — 有 always takes 没."),
    "de_possessive": (
        "的 links an owner or a description to a noun, like English 's: 我的手机 (my "
        "phone), 老师的书 (the teacher's book).",
        "Close family and groups usually drop it: 我妈妈 (my mum), 我们公司 (our "
        "company)."),
    "adj_predicate": (
        "An adjective is the whole predicate — no verb, no 是: 天气很热 (the weather is "
        "hot).",
        "Adding 是 is the classic mistake: 天气是热 ✗."),
    "hen_adj": (
        "很 fills the gap before an adjective: 他很高 (he's tall). It's barely 'very' — "
        "without stress it just says 'is'.",
        "A bare adjective (他高) sounds like a comparison: he's the tall one."),
    "adj_de_noun": (
        "The description goes before the noun: 新衣服 (new clothes), 很好吃的菜 (really "
        "tasty food). Longer descriptions take 的.",
        "Never after the noun: 衣服新 is a sentence (the clothes are new), not a phrase."),
    "adverb_verb": (
        "Adverbs (也 also, 都 all, 常常 often) sit right before the verb: 我也去 (I'm "
        "going too).",
        "Not at the start or end: 也我去 ✗, 我去也 ✗."),
    "bu_neg": (
        "不 negates habits, states, wishes and the future: 我不喝酒 (I don't drink), 明天"
        "不去 (not going tomorrow).",
        "Not for something that didn't happen — that's 没: 昨天不去 ✗ → 昨天没去."),
    "mei_neg": (
        "没(有) + verb: it didn't happen, or hasn't yet: 我没吃 (I didn't eat / haven't "
        "eaten).",
        "No 了 after a 没 verb: 我没吃了 ✗ — except 'not for a long time': 我好久没吃了 (I haven't had it for ages)."),
    "bu_vs_mei": (
        "不 = don't / won't (choice, habit, future). 没 = didn't / haven't (what happened). "
        "不去 = not going; 没去 = didn't go.",
        "有 only takes 没; 是 and 知道 only take 不. Adjectives take 不, and 没 only for 'hasn't become': 天还没黑 (it isn't dark yet)."),
    "buyao": (
        "不要 + verb tells someone not to do something: 不要走 (don't go). It also means "
        "'don't want': 我不要 (I don't want it).",
        "To say you don't want TO do something, 不想 is softer and usual: 我不想去."),
    "ma_question": (
        "Put 吗 on the end of a statement and it's a yes/no question: 你忙吗？ (are you "
        "busy?). Nothing else moves.",
        "Not with a question word: 你去哪里吗？ ✗ — 哪里 is already the question."),
    "short_answers": (
        "Answer yes/no by repeating the verb or adjective: 你去吗？——去。/ 不去。 Chinese "
        "has no all-purpose 'yes'.",
        "是 isn't 'yes' unless the question used 是."),
    "ne_followup": (
        "Noun + 呢 bounces the question: 我很好，你呢？ (I'm fine, and you?). Alone, "
        "我的手机呢？ means 'where's my phone?'",
        "It doesn't make a yes/no question: 你忙呢？ ✗ → 你忙吗？"),
    "ne_ongoing": (
        "呢 at the end says it's still going on: 他睡觉呢 (he's asleep). It often joins "
        "在: 他在睡觉呢.",
        "Not for finished actions: 他睡了呢 ✗."),
    "a_not_a": (
        "Say the yes and the no together to ask: 你去不去？ (are you going?), 好不好？ "
        "(OK?). Two-syllable words can shorten: 喜不喜欢？",
        "Never add 吗 as well: 你去不去吗？ ✗."),
    "you_mei_you": (
        "有没有 asks 'is there / do you have?': 有没有水？ It also asks if something "
        "happened: 你有没有吃？ (did you eat?).",
        "Not 有不有 — 有 pairs with 没."),
    "shei": (
        "谁 (who) goes where the person would go in the answer: 谁来了？ (who came?) / 你找"
        "谁？ (who are you looking for?).",
        "Don't move it to the front: 谁你找？ ✗."),
    "shenme": (
        "什么 = what; before a noun, what kind of: 你吃什么？ / 什么菜？ (what dish?).",
        "It stays where the answer goes: 你吃什么, not 什么你吃."),
    "nage": (
        "哪 + measure word asks 'which': 哪个？ 哪本书？ (which book?) 哪天？ (which day?).",
        "哪 needs its measure word: 哪书 ✗ → 哪本书."),
    "nali": (
        "哪里 = where: 你在哪里？ (where are you?), 去哪里？ (where to?). Malaysians say 哪里, "
        "not 哪儿.",
        "With 去 and 在, 哪里 comes after the verb, like the place would."),
    "zenme": (
        "怎么 + verb asks how to do something: 怎么去？ (how do I get there?). In a "
        "complaint it means 'how come': 你怎么不来？",
        "For 'what's it like?' use 怎么样, not 怎么."),
    "zenmeyang": (
        "……怎么样？ asks what something is like (这个菜怎么样？ how's this dish?) or "
        "suggests (明天怎么样？ how about tomorrow?).",
        "It goes at the end, never before a verb — that's 怎么."),
    "ji_howmany": (
        "几 + measure word asks how many when you expect a small number (under ten): 几个"
        "人？ For ages of children: 你几岁？",
        "几 needs a measure word: 几人 ✗ → 几个人."),
    "duoshao": (
        "多少 asks how many / how much with no limit: 多少人？ 多少钱？ (how much?). The "
        "measure word is optional.",
        "For small expected numbers 几 is more natural."),
    "duo_adj": (
        "多 + adjective asks 'how (tall / far / old)': 你多高？ 你多大？ (how old are you, "
        "adult).",
        "Use 几岁 only for children."),
    "jidian": (
        "几点 asks the time: 现在几点？ / 你几点上班？ (what time do you start work?).",
        "The time goes before the verb in the answer: 我八点上班."),
    "qword_position": (
        "Question words stay exactly where the answer would be: 你去哪里？ → 我去巴刹. To "
        "ask, swap the answer for 谁 / 什么 / 哪里.",
        "English moves 'where' to the front; Chinese never does."),
    "mw_ge": (
        "个 is the all-purpose measure word between a number and a noun: 一个人, 三个苹果.",
        "A number can't touch a noun directly: 三人 ✗ (except set phrases)."),
    "num_mw_noun": (
        "Number + measure word + noun, always: 两杯咖啡 (two cups of coffee), 三本书.",
        "两 before measure words, not 二: 两个, not 二个."),
    "mw_common": (
        "Each kind of thing has its measure word: 本 books, 张 flat things, 件 clothes, "
        "杯 cups, 只 animals, 家 shops and companies.",
        "When unsure 个 is safer than the wrong one."),
    "zhe_na_mw": (
        "这 (this) / 那 (that) + measure word + noun: 这本书, 那家店. Plural: 这些 (these).",
        "这书 ✗ — the measure word is needed."),
    "zai_v": (
        "在 + verb: happening right now (or at that moment): 他在吃饭 (he's eating).",
        "Not for states like 知道 or 是: 我在知道 ✗."),
    "zhengzai_v": (
        "正在 + verb: right in the middle of it, stronger than 在: 我正在开会 (I'm in a "
        "meeting). Often with 呢 at the end.",
        "No 了 with it: 正在吃了 ✗."),
    "v_yixia": (
        "Verb + 一下 = do it briefly or have a go — softens a request: 等一下 (wait a "
        "moment), 看一下 (take a look).",
        "Not with 了 in requests; 一下 already makes it short."),
    "xiang_want": (
        "想 + verb: would like to, feel like: 我想喝水 (I'd like some water). Softer than 要.",
        "想 alone + person = miss: 我想你 (I miss you)."),
    "yao_want": (
        "要 + thing = want (我要这个); 要 + verb = want to / need to / going to: 我要走了 "
        "(I'm off).",
        "Negative 'don't want to' is 不想; 不要 is 'don't!'"),
    "hui_can": (
        "会 = know how to (learnt skill): 我会游泳 (I can swim). Also 'will probably': 明天"
        "会下雨.",
        "Not for physical ability or permission — that's 能 / 可以."),
    "neng": (
        "能 = able to, circumstances allow: 我今天不能来 (I can't come today).",
        "For a learnt skill 会 is the natural word: 我会说中文 (I can speak Chinese). 能 there stresses being able right now."),
    "keyi": (
        "可以 = may, allowed: 我可以坐这里吗？ (may I sit here?). Answer 可以 / 不可以.",
        "'Can't' for rules is 不可以 or 不能; for skills it's 不会."),
    "hui_neng_keyi": (
        "会 = know how; 能 = able / circumstances; 可以 = allowed. 我会游泳 · 今天不能游 · "
        "这里可以游吗？",
        "Mixing them is the commonest modal mistake — ask what kind of 'can' it is."),
    "tai_le": (
        "太 + adjective + 了 = too …: 太贵了 (too expensive). Said happily it's 'so …!': 太好"
        "了! (great!).",
        "Keep the 了; 太贵 alone sounds cut off."),
    "feichang": (
        "非常 + adjective or feeling = extremely: 非常好, 非常喜欢.",
        "No 很 as well: 非常很好 ✗."),
    "zhen_adj": (
        "真 + adjective = really — an exclamation, not a description: 你真好! (you're so "
        "kind!).",
        "Not inside a description: 真好的菜 ✗ → 很好的菜."),
    "zhen_a": (
        "真 + adjective + 啊 = how …!: 真热啊! (it's so hot!).",
        "Use it for comments, not questions."),
    "youdian": (
        "有点 + adjective = a bit (too) — usually unwelcome: 有点贵 (a bit pricey), 有点累.",
        "Asking for 'a bit more X' is adjective + 一点: 便宜一点 (a bit cheaper)."),
    "ye_also": (
        "也 = also, too — before the verb: 我也去 (I'm going too). Joining clauses: 我喜欢，"
        "他也喜欢.",
        "Not at the end like English 'too': 我去也 ✗."),
    "hai_also": (
        "还 = in addition, as well: 我还要一杯 (I want another one). Adds more to what's "
        "already there.",
        "也 compares with someone else (he does too); 还 adds to the same person's list."),
    "zai_again": (
        "再 = again, for something that hasn't happened yet: 明天再来 (come again "
        "tomorrow), 再说一遍 (say it again).",
        "For a repeat that already happened use 又: 他又来了."),
    "dui_toward": (
        "对 + person / thing + adjective: towards, for: 他对我很好 (he's good to me), 对身体"
        "不好 (bad for your health).",
        "It goes before the description, not after: 他很好对我 ✗."),
    "zai_place": (
        "在 + place on its own = be at: 他在家 (he's at home), 锁匙在桌上 (the keys are "
        "on the table).",
        "No 是: 他是在家 ✗ (unless stressing)."),
    "gen_with": (
        "跟 / 和 + person + verb = (do) with: 我跟朋友吃饭 (I eat with friends). Malaysians "
        "use 跟 most.",
        "'With' comes before the verb, not after it: 我吃饭跟朋友 ✗."),
    "le_verb": (
        "Verb + 了 = it got done: 我买了三本书 (I bought three books). It marks completion, "
        "not past tense.",
        "Habits in the past take no 了: 我以前常常去 (I used to go often)."),
    "le_final": (
        "了 at the end of a sentence = now it's different: 下雨了 (it's started raining), "
        "我饿了 (I'm hungry now), 他不来了 (he's not coming after all).",
        "Not on a plain description: 他很高了 means he has grown tall."),
    "ba_particle": (
        "吧 at the end suggests (我们走吧 let's go), softens a request (你先吃吧), or checks a "
        "guess (你是老师吧？ you're a teacher, right?).",
        "It doesn't make a neutral question — that's 吗."),
    "double_object": (
        "Verb + person + thing: 他给我一本书 (he gave me a book), 我问你一个问题. Person "
        "always first.",
        "Thing first is wrong: 给一本书我 ✗."),
    "serial_verbs": (
        "Verbs line up in the order things happen, no 'and': 坐巴士去上班 (take the bus to "
        "work), 去巴刹买菜 (go to the market to buy food).",
        "The first verb is often how or where; the last is the purpose."),
    "qu_v": (
        "去 + verb = go and do: 我去买菜 (I'm going to buy food). Add the place in the "
        "middle: 去巴刹买菜.",
        "Purpose goes last: 我去为了买菜 ✗."),
    "place_shi": (
        "Place + 是 + thing tells what's there, as if pointing: 前边是银行 (in front is a "
        "bank).",
        "With an amount (一家, 很多) use 有: 前边有一家银行."),
    "place_you": (
        "Place + 有 + amount + thing = there is: 桌上有一本书 (there's a book on the table).",
        "The place comes first, with no 在 in front: 在桌上有书 is heard but plain 桌上有书 "
        "is standard."),
    "loc_words_1": (
        "Place words go after the noun: 桌子上 (on the table), 冰箱里 (in the fridge), 门外 "
        "(outside the door).",
        "English puts 'on / in' first; Chinese puts 上 / 里 after: 上桌子 ✗."),
    "noun_predicate": (
        "A date, day, age or price can stand with no verb: 今天星期一 (today's Monday), 他二十"
        "岁 (he's twenty), 这个十块 (this is ten ringgit).",
        "The negative needs 是: 今天不是星期一 (today isn't Monday). 他是二十岁 is only for correcting someone (he IS twenty)."),
    "numbers": (
        "Numbers are built in order: 三十五 (35), 一百二十 (120). 零 fills a gap: 一百零五 "
        "(105). 两 before a measure word or 百 / 千: 两个, 两千.",
        "二个 ✗ → 两个. But 十二, 二十 and 二月 (February) keep 二."),
    "di_ordinal": (
        "第 + number = first, second …: 第一次 (the first time), 第二天 (the next day).",
        "Without 第 it's how many: 三天 (three days) vs 第三天 (the third day)."),
    "date_time": (
        "Big to small: year → month → day → weekday → time: 十一月二十三号，星期一，早上九"
        "点. Times: 两点 (2:00), 九点半 (9:30), 三点十五分 (3:15).",
        "两点, not 二点. The time goes before the verb: 我八点上班."),
    "money": (
        "块 in speech, 元 in writing: 二十块(钱) (twenty ringgit), 两块五 (2.50). Ask 多少钱？",
        "两块, not 二块."),
    "lihe_verbs": (
        "睡觉 (sleep), 上班 (go to work), 看病 (see a doctor) are verb + object fused. They "
        "work as one verb with 了 / 没 / 在 around them: 他在上课, 我没上班.",
        "They can't take another object: 见面他 ✗ → 跟他见面."),
    "he_and": (
        "和 joins nouns: 我和你 (you and me), 茶和咖啡 (tea and coffee). Malaysians often "
        "say 跟.",
        "It never joins sentences or verbs: 'I ate and left' is 我吃了饭就走了, not 和."),
    "dou_all": (
        "都 goes after the group, before the verb: 我们都去 (we're all going), 这些都很贵 "
        "(these are all expensive).",
        "Not before the group: 都我们去 ✗. 都不 = none; 不都 = not all."),
}


def _merge(part):
    clash = set(part.LEARN) & set(LEARN)
    assert not clash, f"cards written twice: {clash}"
    MAP.update(part.MAP)
    LEXICAL.update(part.LEXICAL)
    LEARN.update(part.LEARN)


import hsk_grammar_2  # noqa: E402
import hsk_grammar_3  # noqa: E402
import hsk_grammar_4  # noqa: E402

_merge(hsk_grammar_2)
_merge(hsk_grammar_3)
_merge(hsk_grammar_4)


@functools.lru_cache(maxsize=1)
def _points():
    return {g["id"]: g for g in hsk.grammar_points()}


@functools.lru_cache(maxsize=1)
def structure_level():
    """{structure id: the lowest HSK level whose points it teaches}."""
    out = {}
    for pid, sids in MAP.items():
        lv = _points()[pid]["level"]
        for sid in sids:
            out[sid] = min(out.get(sid, 9), lv)
    return out


def points_for(sid):
    """The official points a structure teaches."""
    return [_points()[pid] for pid, sids in MAP.items() if sid in sids]


def learning_order(upto=4):
    """The HSK track's drill order: HSK 1's structures, then HSK 2's …, up to
    `upto`; within a level the curriculum's own order, with a contrast pair
    still waiting for both halves."""
    levels = structure_level()
    base = gc.learning_order(hsk=True)
    pos = {s.id: i for i, s in enumerate(base)}
    picked = [s for s in base if levels.get(s.id, 9) <= upto]
    ranked = sorted(picked, key=lambda s: (levels[s.id], pos[s.id]))
    placed, out, waiting = set(), [], []

    def ready(s):
        return all(c in placed or levels.get(c, 9) > upto for c in s.contrast)

    for s in ranked:
        if s.kind == "contrast" and not ready(s):
            waiting.append(s)
            continue
        out.append(s)
        placed.add(s.id)
        for w in [w for w in waiting if ready(w)]:
            waiting.remove(w)
            out.append(w)
            placed.add(w.id)
    return out + waiting


def sentence_pinyin(text):
    """Pinyin for a whole sentence (pinyin_hsk.sentence_pinyin)."""
    import pinyin_hsk
    return pinyin_hsk.sentence_pinyin(text)


def _markers(structure):
    return [m for m in structure.markers if m]


def examples(sid, limit=3):
    """Official HSK example sentences for a structure: from the points it
    teaches, ones that show one of its markers, no Beijing 儿. Each with
    pinyin and English."""
    s = gc.get(sid)
    marks = _markers(s) if s else []
    out, seen = [], set()
    for p in points_for(sid):
        for ex in p["examples"]:
            zh = re.sub(r"（[^）]*）", "", ex["chinese"]).strip()
            if (zh in seen or has_erhua(zh) or not ex["english"]
                    or not re.search(r"[。？！]$", zh)
                    or (marks and not any(m in zh for m in marks))):
                continue
            seen.add(zh)
            # the deck's hand-checked pinyin where the sentence is as printed
            py = ex.get("pinyin") if zh == ex["chinese"] else ""
            out.append({"chinese": zh, "pinyin": py or sentence_pinyin(zh),
                        "english": ex["english"]})
    return out[:limit]


def card(sid):
    """What the 'how it works' card shows, or None if there isn't one."""
    if sid not in LEARN:
        return None
    how, trap = LEARN[sid]
    return {"how": how, "trap": trap, "examples": examples(sid),
            "hsk": structure_level().get(sid),
            "points": [p["point"] for p in points_for(sid)]}


# ----------------------------------------------------------------------
# how much of a drill set a session uses (HSK track)
# ----------------------------------------------------------------------
# new    met for the first time (or failed last time): the learn card, then
#        a trimmed full set
# check  new, but below your tested grammar level: a quick check; pass it
#        and it is treated as known (next seen in a week), fail it and it
#        becomes a full lesson next time
# quick  a review: a few items, mostly said aloud
LESSON_ITEMS = {
    "new": {"identify": 3, "build": 2, "transform": 2, "produce": 3, "contrast": 2,
            "rapid": 4, "conversation": 2},
    "check": {"build": 1, "rapid": 3, "produce": 2},
    "quick": {"build": 1, "rapid": 3, "produce": 2},
}
LESSON_MINUTES = {"new": 7, "check": 2, "quick": 2}


def lesson_mode(sid, progress, upto):
    """new / check / quick for a structure today (see LESSON_ITEMS)."""
    p = (progress or {}).get(sid)
    if p:
        return "quick" if (p.get("interval") or 0) > 0 else "new"
    return "check" if structure_level().get(sid, upto) < upto else "new"


def plan_lessons(due, fresh, progress, upto, minutes, new_max, checks_max):
    """The morning's structures: reviews first, then new ones in learning
    order, within the minutes. At least one if there is anything at all.
    due and fresh are structure ids, best first. Returns [(sid, mode)]."""
    picked, left, full, checks = [], minutes, 0, 0
    for sid in due:
        mode = lesson_mode(sid, progress, upto)
        cost = LESSON_MINUTES[mode]
        if cost > left and picked:
            break
        picked.append((sid, mode))
        left -= cost
    for sid in fresh:
        mode = lesson_mode(sid, progress, upto)
        if (mode == "new" and full >= new_max) or (mode == "check" and checks >= checks_max):
            break
        if LESSON_MINUTES[mode] > left and picked:
            break
        picked.append((sid, mode))
        left -= LESSON_MINUTES[mode]
        full += mode == "new"
        checks += mode == "check"
    return picked
