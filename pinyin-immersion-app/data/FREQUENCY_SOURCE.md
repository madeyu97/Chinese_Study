# Frequency list source

`frequency_words.csv` (top 10,000 study words) and `frequency_ranks.csv`
(rank lookup for ~44,000 words) are derived from **SUBTLEX-CH**, a word
frequency database built from 33.5 million words of Chinese film and TV
subtitles:

> Cai, Q., & Brysbaert, M. (2010). SUBTLEX-CH: Chinese Word and Character
> Frequencies Based on Film Subtitles. *PLoS ONE*, 5(6), e10729.
> https://doi.org/10.1371/journal.pone.0010729

SUBTLEX-CH is freely available data; derived work must credit its authors.

Ranking is by contextual diversity (the number of films a word appears in),
which the authors recommend and which keeps character names from single
films out. Person names, bare numbers, number + measure-word pairs and
non-dictionary fragments were removed. Pinyin and meanings come from
CC-CEDICT (CC BY-SA 4.0), with the most frequent words checked by hand.
