# 华语 Study — Malaysian Mandarin

A Streamlit app on Supabase Postgres, with Groq for the AI-written drills
and Edge TTS for audio. One codebase, two deployments, two ways of studying:

| | who | entry point | how it studies |
|---|---|---|---|
| HSK track | Matt (`config.HSK_TRACK_USERS`) | `src/main_app.py` | HSK 1–4 (2025 syllabus): writing, grammar, reading, games. Vocabulary is done in Anki, not here. |
| original | Selina | `src/app2.py` | the original app: own word list, tones, sentences, handwriting, reading. |

Each deployment is bound to one person by its `APP_USER` secret. Both share
one database. Anything that changes behaviour for the HSK track is guarded by
`auth.on_hsk_track(user)`, so Selina's app stays as it was.

## The HSK track

**Level test** (Settings → HSK level test, `placement.py`). This sets three
levels. *Listening* (hear a word, pick its meaning) and *reading* (see it in
characters, pick its meaning) go level by level from HSK 1 and stop as soon
as the result is clear. *Grammar* asks you to put an official HSK example
sentence back in order. Each level is the one to study (1–4). You can also
set them by hand. The same page asks roughly how many HSK words you've
learnt in Anki. Grammar drills are then built from those words, and Today
shows how many of the 1,096 recognition characters they cover.

**Today** (`today_plan.py`) has two sessions a day:
- 🌅 Morning: about 25 minutes of grammar. Short reviews come first, then up
  to 2 new structures. Structures below your tested grammar level get a
  2-minute quick check instead of a full lesson. At this pace all 344
  structures take about nine months (`hsk_grammar.plan_lessons`).
- 🌙 Evening: one picture-word game (about 3 minutes, a different kind each
  day), writing (5 new characters a day plus reviews), then one graded passage.

**✍️ Write** (`views/2_Handwriting.py`). The 400 characters HSK 1–4 asks
you to write by hand, in `data/hsk/write_order.csv` order: HSK 1–2, then 3,
then 4. Within each band, a character's parts come before the characters
built from them (女 nǚ "woman" before 好 hǎo "good"). The cue is an HSK word
with the character blanked: ＿字 míng zi "name". Herb names are a separate
mode, opened from Play.

**🧩 Grammar** (`views/7_Grammar.py`, `hsk_grammar*.py`). All 339 HSK 1–4
grammar points are mapped onto the app's structures, plus some structures
only the HSK track has (`grammar_data_hsk.py`). Each one opens with a learn
card (how it works, the usual trap). Then come the stages: identify → build
(word tiles) → transform → produce → contrast → rapid → conversation.
Reviews use only a few items, mostly said aloud (`hg.LESSON_ITEMS`).

**📖 Read** (`reading_hsk.py`, `reading_hsk_page.py`). AI-written passages
at your reading level: at least 93% known words, at most 3 new ones. By
default you listen first and answer the question by ear (HSK 4's listening
paper is a third of the exam), then read. Tap a word to see its pinyin and
meaning. Each passage has a question and a
translation, and you can download the new words as an Anki CSV. Mandarin
Bean is linked for more (linked only, not copied: its content is All
Rights Reserved).

**🎮 Play** (`games_hsk.py`, `games_hsk_page.py`):
- 🖼️ Picture words, first on the page: picture → word, word → picture,
  hear it → picture, picture memory. 623 HSK 1–4 words (a third of the list)
  have a picture, each checked by eye (`data/hsk/pictures.csv`). Abstract
  words, and ones a picture can't tell apart from another word, are left
  out. Each game adds at most 3 new words, next in the syllabus.
- Hear it, find it
- Read it
- Look-alikes (请 qǐng / 清 qīng / 情 qíng)
- Measure words (一＿书 → 本): 299 nouns, 248 with a measure word other than 个
- Sentence scramble: official example sentences, two-clause ones too (HSK 4: 167)
- Memory match

Every answer is saved per word (table `game_seen`). A game starts with the
words you missed last time, then the ones due again (after 1, 3, 7, 21, 60
days), then words you haven't met yet (ones learnt in Anki first). After
that it takes the words played longest ago (`games_hsk.prioritise`).

🌿 Herbs is a separate section: name the herb, find the herb, write herb
names.

### No waiting for the AI

Grammar drill sets and reading passages are written ahead and stored, so a
lesson opens straight away:
- In the app: opening Today queues the drills for today's and the next few
  days' structures (`ahead.py`, `drill_bank.py`).
- Nightly: `.github/workflows/fill-drill-bank.yml` runs `tools/fill_bank.py`
  at 02:00 Malaysia time, before Groq's daily allowance resets: up to 12
  drill sets for the coming mornings, then reading passages. It waits for
  the strong models (gpt-oss-120b, Qwen) rather than use the small one. It
  needs the repository secrets `DATABASE_URL` and `GROQ_API_KEY`, the same
  values the app uses. Its log (Actions tab) says what it wrote and why
  anything was rejected.

## Configuration

Streamlit secrets (or environment variables):

| name | what |
|---|---|
| `DATABASE_URL` | Postgres URL (Supabase). The schema is created and migrated on start. |
| `GROQ_API_KEY` | Groq key, one per deployment (separate rate limits) |
| `APP_USER` | `matt` or `selina`. Skips the sign-in screen. |
| `APP_TZ` | optional time zone for the study day (default Asia/Kuala_Lumpur) |

Daily amounts (new grammar, new characters, session times) are in
`src/config.py`.

## Data

- `data/hsk/`: the HSK 1–4 syllabus (words, characters to recognise and
  write, grammar points with official examples, writing order, look-alike
  characters). Built by `tools/build_hsk_data.py`. Sources and licences are
  in `data/hsk/SOURCES.md`.
- `data/herbs.csv`: the Herb Dojo herb list (`src/extract_herbs.py` makes it
  from a Herb Dojo export).
- `data/frequency_words.csv`, `data/frequency_ranks.csv`: the original
  app's frequency list and glosses (`data/FREQUENCY_SOURCE.md`).
- `data/game_images/`: pictures for the picture games, with credits. The HSK
  pictures are mostly ARASAAC pictograms (`arasaac/`, CC BY-NC-SA 4.0:
  non-commercial use only); `tools/build_hsk_pictures.py` fetches any missing.

## Running and testing

```bash
pip install -r requirements.txt               # from the repository root
cd pinyin-immersion-app
streamlit run src/main_app.py

python src/run_tests.py                       # Python tests; the database ones run
                                              # when DATABASE_URL is set (a throwaway
                                              # local Postgres is fine)
cd src && for t in choice_board/test_board.js memory_board/test_board.js \
                   hw_component/test_*.js; do node "$t"; done   # needs jsdom
```

`src/build_sentence_bank.py` and `src/seed_from_tatoeba.py` fill the
original app's sentence bank from the command line.
