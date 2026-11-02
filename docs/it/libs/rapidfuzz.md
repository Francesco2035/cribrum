# rapidfuzz

Confronto "approssimato" tra stringhe (fuzzy matching), molto veloce perché
scritto in C++. In Cribrum serve a riconoscere corsi e professori anche con
refusi o varianti: "anals 1", "prof rosi", "Analisi I".

Doc: https://rapidfuzz.github.io/RapidFuzz/

## Concetti chiave

Tutti gli score vanno da **0 a 100**.

| Funzione                  | Cosa misura                                                   | Esempio                                          |
|---------------------------|---------------------------------------------------------------|--------------------------------------------------|
| `fuzz.ratio`              | somiglianza tra le stringhe intere                            | "rossi" vs "rosi" → alto                          |
| `fuzz.partial_ratio`      | la stringa corta dentro quella lunga                          | "am1" dentro "com'è am1 quest'anno" → alto       |
| `fuzz.token_sort_ratio`   | ignora l'ordine delle parole                                  | "analisi matematica" vs "matematica analisi"      |
| `fuzz.token_set_ratio`    | ignora ordine e parole in più                                 | "analisi 1" vs "corso di analisi 1 prof rossi"   |
| `fuzz.WRatio`             | combinazione pesata delle precedenti, un buon default         |                                                  |

## Uso

```python
from rapidfuzz import fuzz, process, utils

aliases = {"analisi 1": "am1", "am1": "am1", "fisica 1": "fis1", "rossi": "prof_rossi"}

# miglior match sopra una soglia (None se non c'è)
m = process.extractOne("anlisi 1", aliases.keys(),
                       scorer=fuzz.WRatio,
                       processor=utils.default_process,   # minuscole + via punteggiatura
                       score_cutoff=85)
# -> ("analisi 1", 94.1, 0)   cioè (scelta, score, indice)
if m:
    course_id = aliases[m[0]]

# più candidati
process.extract("rosi", aliases.keys(), scorer=fuzz.ratio, limit=3)
```

## Strategia consigliata per `courses.py`

1. Prima il **match esatto** sugli alias normalizzati: veloce e senza falsi positivi.
2. Poi il **fuzzy** solo sugli n-grammi del testo (parole singole e coppie di parole), con una soglia alta (85-90).
3. **Alias corti** (sigle come "AM1", "FI", cognomi di 4 lettere) → solo match esatto: col fuzzy producono tanti falsi positivi.

## Trappole

- `partial_ratio` con alias molto corti trova match ovunque ("fi" dentro "fisica", "finito"…).
- Senza `processor=utils.default_process` il confronto è sensibile alle maiuscole.
- La soglia va tarata sui dati reali: prova su qualche centinaio di messaggi e guarda i falsi positivi.
