# Where the word list comes from

## Sources

- **Frequencies:** [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), 2018 OpenSubtitles counts: `ms_50k`, plus `id_50k` and `en_50k` for comparison. Licence CC BY-SA 4.0. `malay_words.csv` is derived from it and is shared under the same licence.
- **Lexicon:** the union of four word sets from [Malaya](https://github.com/huseinzol05/malaya) (kamus_dewan, dbp, words, cambridge_words), 64,575 forms in `src/malay/data/lexicon.txt`. Licence MIT, in `src/malay/data/LICENSE-malaya.txt`.
- **Glosses:** written by hand for all 5,000 words in `tools/glosses/g01.txt` to `g10.txt`. Each line has the meaning, root, affixes, part of speech, register, and an Indonesian (`I`) or unsure (`?`) mark.

## Method (`tools/build_wordlist.py`)

1. **Clean.** Every rule in `tools/wordlist_rules.py` was checked against the top 8,000 raw ranks.
   - Drop English words, names and noise.
   - Merge spelling variants and split run-together words.
   - Keep real words that look like noise.
2. **Fold clitics.** Counts for `rumahnya`, `bukulah` and `kubawa` are added to `rumah`, `buku` and `bawa`. The `KEEP_WHOLE` list stops false folds such as `masalah`, `sekolah`, `menikah` and `adalah`.
3. **Take the top 5,000.** The lowest count kept is 79.
4. **Flag Indonesian forms.** Each form in `INDO` names its Malaysian word (`bisa` → `boleh`). Words much more frequent in Indonesian than in Malay subtitles are reported for a decision. Of the 5,000, 252 are Indonesian forms. In the app they are recognition-only and wait until their Malaysian partner is known.
5. **Join the glosses.** `tools/glosses_to_csv.py` turns the gloss files into `data/glosses.csv`.

Rebuild:

```bash
cd bahasa-app
python3 -I tools/glosses_to_csv.py
python3 -I tools/build_wordlist.py      # downloads the 50k lists into tools/sources/ if missing
```

## Analyser accuracy (`tools/eval_morphology.py`)

The app looks up root and affixes in the glossed list first. Rules cover any word not on the list. To measure the rules alone, the model knows only the roots of ranks 1–2500 and is scored on random words from ranks 2501–5000. The hand-written roots are the answer key.

| Set | Roots right |
|---|---|
| Ranks 1–2500 (the rules were tuned here) | 99.3% |
| Held out A, 300 words (looked at during tuning) | 96.0% |
| Held out B, 300 words (never looked at) | 95.3% |

The gate is 95% on set B. Most misses are loanwords and plain roots that look affixed, such as `pelangi` read as peN- + langi. Those words are on the list, so the app gets them right. `src/malay/data/overrides.csv` fixes known traps outside the list.

## Known limits

- Subtitle Malay leans colloquial and conversational. Formal and written words rank lower than in a news corpus.
- Two glosses are marked unsure, `radi` and `malik`. They start in the review queue.
