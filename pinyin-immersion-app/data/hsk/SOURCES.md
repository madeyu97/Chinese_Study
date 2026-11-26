# HSK 1–4 data (2025 syllabus)

Built by `tools/build_hsk_data.py` from the **HSK examination syllabus**
(中文水平考试 HSK 考试大纲), published November 2025, the basis of the
HSK 3.0 exams from 13 December 2026. Levels 1–4 only.

| file | what | from |
|---|---|---|
| `words.csv` | 300 / 200 / 500 / 1,000 words (a word listed at two levels is kept at the lower) | [Punpuf/hsk-syllabus-vocabulary-parser](https://github.com/Punpuf/hsk-syllabus-vocabulary-parser), via [RyanGibb/anki-hsk3](https://github.com/RyanGibb/anki-hsk3) |
| `recognise.csv` | 246 / 125 / 284 / 441 characters to recognise | [krmanik/HSK-3.0](https://github.com/krmanik/HSK-3.0) |
| `write.csv` | 100 (HSK 1–2) / 150 / 150 characters to write by hand | [chelsea6502/hsk-2025-data](https://github.com/chelsea6502/hsk-2025-data), via anki-hsk3 |
| `grammar.csv`, `grammar_examples.csv` | 70 / 78 / 96 / 95 grammar points and their official example sentences | [chinesetest.cn](https://www.chinesetest.cn/), via anki-hsk3 (with its corrections); English by DeepL and hand-checked pinyin, both from anki-hsk3 |

`words.csv`'s `measure` column is the noun's measure words from
CC-CEDICT's `CL:` notes (书: 本、册、部). `lookalike.csv` lists recognition
characters easily taken for one another, from their components
([hanzipy](https://github.com/Synkied/hanzipy)) and stroke counts
([hanzi-writer-data](https://github.com/chanind/hanzi-writer-data)), plus a
hand-made list of shapes the components can't show (己 已, 土 士).

Pinyin for other sentences (AI-written drills and passages) comes from
`src/pinyin_hsk.py`, which matches anki-hsk3's hand-checked pinyin on 97% of
the HSK 1–4 example sentences; `tools/check_pinyin.py` measures it.
English meanings that misled (CC-CEDICT slang and old senses) are replaced
in `tools/build_hsk_data.py` (`GLOSS_FIX`).

English meanings: the app's own hand-checked list (`frequency_words.csv`)
where it has the word, otherwise the first senses of
[CC-CEDICT](https://cc-cedict.org/) (CC BY-SA 4.0).

`erhua = 1` marks Beijing 儿 words (哪儿, 一会儿…). The app teaches
Malaysian Mandarin, so drills and tests leave them out — the 儿-less word
is on the list too (哪里).

`pictures.csv` gives the picture for each of the 623 HSK words the picture
games use. 500 are [ARASAAC](https://arasaac.org) pictograms (Sergio Palao,
Government of Aragón, CC BY-NC-SA 4.0). The rest are Twemoji (CC BY 4.0) and
the Commons photos already in `data/game_images`. Candidates were matched on
ARASAAC's Chinese and English keywords, then each one was looked at. One that
could fairly stand for another word in the same game, or needs the word
already known to make sense, was left out.
