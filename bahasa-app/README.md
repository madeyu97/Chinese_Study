# Bahasa Study

A Malaysian Malay study app, forked from the Chinese study app. It uses the same engine: a two-skill SRS (recognising and producing), the Today plan, checked AI-generated content, and two users who can see each other's progress. Character writing is gone. In its place is a Malay core that analyses words (root, affixes, clitics), treats colloquial and standard forms as equal, and marks Indonesian forms.

It lives in the Chinese app's repo, in its own folder, and runs as a separate Streamlit app. It uses the repo's root `requirements.txt` and can share the Chinese app's database and Groq key (see Deploy). Nothing in `pinyin-immersion-app/` is touched.

Built in phases. The phase plan is the "Malay Study App — Phased Build Plan" doc.

| Phase | Status | What it adds |
|---|---|---|
| 0 Fork and strip | done | Chinese-only code removed; engine, plan, Together page and Settings kept |
| 1 Malay core and word list | done | `src/malay/` (morphology, normalise, checker, known), 5,000 glossed words, 258 clinic lesson items |
| 2 Words loop | done | Words page in Today; word content written per learner and gated (known words, no Indonesian); diagnosis and remedies in Malay terms |
| 3 Listen & speak, Play | done | Listen & speak in Today (Tatoeba sentences first, then checked model sentences); speech graded in either register; picture games in Malay with a clinic topic |
| 4 Grammar | done | 120 structures in Today and the Library; drills written from your own words, checked, reused |
| 5 Affixes | done | Affixes in Today and the Library: root families from your own words, four drills, spaced per family |
| 6 Reading, role-play, northern Malay | done | Reading (95% known words, tap for parts), Clinic role-play (model as patient, graded turns), Penang Malay (recognition) |

All phases in the plan are built. The plan's optional extra, pointing the YouTube echo trainer at Malay videos, belongs to the separate immersion app, not this one.

Today runs Words · Affixes · Grammar · Listen & speak. Reading, Clinic role-play and Penang Malay sit in the Library.

## Layout

```
bahasa-app/
  src/main_app.py          entry point (app2.py = the same app, second deployment)
  src/malay/               Malay core and its data (lexicon, colloquial, Indonesian, overrides)
  src/run_tests.py         regression tests
  data/malay_words.csv     the 5,000-word list, ranked and glossed
  data/lessons.csv         your own lists (clinic Malay, northern Malay); lesson rows win on meaning
  data/tatoeba_ms_en.tsv   2,274 human-written Malay sentences with English (Tatoeba)
  src/seed_from_tatoeba.py fill the sentence bank from Tatoeba in bulk (optional)
  src/build_sentence_bank.py  write checked sentences for words Tatoeba lacks (optional)
  tools/                   rebuild the word list and the Tatoeba file; measure the analyser
```

## Run locally

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://..."      # any Postgres; Supabase in production
export GROQ_API_KEY="..."
cd bahasa-app/src && streamlit run main_app.py
```

The first start creates the tables and loads both word lists.

## Deploy (Streamlit Community Cloud + Supabase)

The app can share the Chinese app's Supabase database and Groq key. It keeps all its tables in its own Postgres schema, `bahasa` (set `DB_SCHEMA` to change it), so tables with the same names in the Chinese app's `public` schema are never touched.

1. On Streamlit Cloud, create an app with main file `bahasa-app/src/main_app.py`.
2. Secrets:
   ```toml
   DATABASE_URL = "postgresql://..."   # the Chinese app's, or a new project's
   GROQ_API_KEY = "..."
   APP_USER = "matt"          # optional: binds this deployment to one person
   ```
   Use Supabase's **Session pooler** string (port 5432). The Transaction pooler (port 6543) is refused, because the schema setting doesn't stick there.
3. For a second person's own deployment, use main file `bahasa-app/src/app2.py` with `APP_USER = "selina"` and the same database.

Both apps share one Groq daily allowance when they use the same key.

## Reading

Short passages in standard Malay where at least 95% of the running words are ones you know. Forms of a known root count, and Malaysian place names are free. Tap any word for its root, affixes and meaning. Words you haven't met are highlighted; tick them and they become your next new words on the Words page. A word not on the list is added for checking in Settings. Two or three questions in English check understanding.

Passages are shared: one written for either of you is shown to the other once it fits their vocabulary. A new passage is written from your words, then checked in code for coverage, Indonesian forms, colloquial forms, digits, undeclared words and question keys. A reviewer reads it before it's stored. When nothing fits and the model can't be reached, the page offers short Tatoeba sentences you can read instead.

## Clinic role-play

You're the practitioner; the model plays one of six patients (back, neck and shoulders, headache, knee, numb hand, sleep). The patients' facts and opening lines are hand-written. Speak or type each line. One model call per line grades your Malay (correct / close / wrong, with a better version), ticks off the parts of the consultation you covered, and writes the patient's reply. A reply with an Indonesian form is rewritten. The ten parts run from greeting and history-taking to positioning, comfort checks and advice. "Stuck?" shows hand-written phrases for the next one.

## Penang Malay

Northern Malay (loghat utara) for recognition only. There are 34 northern words with their standard partners, the sound rules behind most of them (besar → besaq, kenal → kenai, panas → panaih), and 32 hand-written Penang lines, some from the clinic. Hear a line and pick its meaning, or read it and pick the standard Malay; each line is spaced. The northern words are also on the lesson list, tagged Utara, so they reach the Words page after 300 words, recognition only. The app's voices are standard Malaysian, so the audio has northern words in a standard accent.

## Sentence bank

Listen & speak takes each sentence from the bank, then from Tatoeba, and only then asks the model to write one. A sentence written by the model must contain the target word and no Indonesian forms. Its numbers must match the English, it may use at most one word from outside the list, and it must pass a reviewer model. Each listening sentence is stored in the bank, so it's written only once. A sentence you flag is retired everywhere.

The bank fills as you study, so the two scripts are optional. To fill it ahead of time, run `seed_from_tatoeba.py` (two model calls per sentence), then `build_sentence_bank.py` (two to four calls). Both continue where they stopped when they hit Groq's daily limit.

## Tests

```bash
cd bahasa-app/src
python run_tests.py                          # no database: core, engine, plan
DATABASE_URL="postgresql://..." python run_tests.py   # adds database and page tests
```

Point `DATABASE_URL` at a throwaway database for tests: they write test rows.

## Word list

`data/malay_words.csv` is built by `tools/build_wordlist.py` from subtitle frequencies, with hand-written glosses from `tools/glosses/`. Sources, method and licences are in `data/WORDLIST_SOURCE.md`. To change a gloss, edit it in **Settings → Word list**. Edited words are never overwritten by a later import.

The Phase 1 gate needs a check of 200 random glosses. Open **Settings → Review queue → Draw 200 random words to audit**, then mark each one right or fix it. The page tracks the accuracy against the 97% gate.

## Licences

Word frequencies: [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), CC BY-SA 4.0, so `data/malay_words.csv` is shared under CC BY-SA 4.0. Lexicon: [Malaya](https://github.com/huseinzol05/malaya), MIT (`src/malay/data/LICENSE-malaya.txt`). Sentences: [Tatoeba](https://tatoeba.org), CC BY 2.0 FR; each sentence keeps its Tatoeba id and author, and the app credits them under the sentence. Pictures: Twemoji (CC BY 4.0) and Wikimedia Commons, credited on the Play page.
