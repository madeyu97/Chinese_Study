# HSK 1–4 data (2025 syllabus)

Built by `tools/build_hsk_data.py` from the **HSK examination syllabus**
(中文水平考试 HSK 考试大纲), published November 2025, the basis of the
HSK 3.0 exams from 13 December 2026. Levels 1–4 only.

| file | what | from |
|---|---|---|
| `words.csv` | 300 / 200 / 500 / 1,000 words (a word listed at two levels is kept at the lower) | [Punpuf/hsk-syllabus-vocabulary-parser](https://github.com/Punpuf/hsk-syllabus-vocabulary-parser), via [RyanGibb/anki-hsk3](https://github.com/RyanGibb/anki-hsk3) |
| `recognise.csv` | 246 / 125 / 284 / 441 characters to recognise | [krmanik/HSK-3.0](https://github.com/krmanik/HSK-3.0) |
| `write.csv` | 100 (HSK 1–2) / 150 / 150 characters to write by hand | [chelsea6502/hsk-2025-data](https://github.com/chelsea6502/hsk-2025-data), via anki-hsk3 |
| `grammar.csv`, `grammar_examples.csv` | 70 / 78 / 96 / 95 grammar points and their official example sentences | [chinesetest.cn](https://www.chinesetest.cn/), via anki-hsk3 (with its corrections); English by DeepL, from anki-hsk3 |

English meanings: the app's own hand-checked list (`frequency_words.csv`)
where it has the word, otherwise the first senses of
[CC-CEDICT](https://cc-cedict.org/) (CC BY-SA 4.0).

`erhua = 1` marks Beijing 儿 words (哪儿, 一会儿…). The app teaches
Malaysian Mandarin, so drills and tests leave them out — the 儿-less word
is on the list too (哪里).
