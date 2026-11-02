# rank-bm25

Implementazione in puro Python di **BM25**, l'algoritmo classico di ricerca per
parole chiave (quello dei motori di ricerca "tradizionali"). In Cribrum è il
ramo **lessicale** della ricerca ibrida: forte proprio dove gli embedding sono
deboli, cioè nomi di professori, sigle di corso e codici.

Doc: https://github.com/dorianbrown/rank_bm25

## Come funziona BM25, in breve

Per ogni documento somma, su ogni parola della query:
- **quanto è rara** la parola nel corpus (IDF): "Bianchi" pesa molto più di "esame";
- **quante volte compare** nel documento, con saturazione: 10 ripetizioni non valgono 10 volte una;
- una **normalizzazione per lunghezza**, così i documenti lunghi non vincono solo perché sono lunghi.

Non capisce i sinonimi: "tosto" e "difficile" sono parole diverse. Per quello
c'è il ramo denso (embedding).

## Uso

```python
from rank_bm25 import BM25Okapi

def tokenize(text: str) -> list[str]:
    return text.lower().split()     # in pratica: togliere punteggiatura/accenti

corpus = ["l'esame di AM1 con Rossi è tosto",
          "fisica 1 si passa con gli esercizi vecchi"]
bm25 = BM25Okapi([tokenize(d) for d in corpus])

scores = bm25.get_scores(tokenize("rossi am1"))   # numpy array, uno score per documento
top = bm25.get_top_n(tokenize("rossi am1"), corpus, n=5)
```

## Da sapere

- **La tokenizzazione è compito tuo**, e conta tantissimo: minuscole, punteggiatura, accenti (`unicodedata`), apostrofi italiani (`l'esame` → `l`, `esame`). Usa la **stessa** funzione per corpus e query.
- **Gli score non sono normalizzati** (0–15, 0–40… dipende dal corpus): non si possono confrontare direttamente con le similarità coseno. Per questo si fonde per *rank* con RRF, non per score.
- **Niente persistenza**: l'indice vive in memoria. Si può ricostruire all'avvio dai testi (con qualche decina di migliaia di chunk ci vuole poco) oppure salvarlo con `pickle`.
- Nessun aggiornamento incrementale: se aggiungi documenti, ricostruisci l'indice.

## Reciprocal Rank Fusion (RRF), per unire i due rami

```
score_rrf(doc) = Σ  1 / (k + rank_del_doc_nel_ramo)      con k ≈ 60
```

Un documento primo in entrambi i rami batte uno primo in un ramo solo e assente
nell'altro. Paper: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

## Alternative

- `bm25s`: molto più veloce, con salvataggio su disco. https://github.com/xhluca/bm25s
- SQLite FTS5 (stdlib, ha BM25 integrato): https://www.sqlite.org/fts5.html
