# core/topic_results.py

Caricamento dei risultati di `discover` di una chat, insieme a tutto quello che serve dopo: finestre, testo dei messaggi ed embedding. Lo usano sia `facets` sia `export`, così le due fasi leggono gli stessi dati allo stesso modo.

## Librerie
`numpy`, `json`; il parser dell'export e le funzioni di `core/window_embeddings.py`.

## Logica
- `ChatResult` raccoglie:
  - la chat (nome dell'export) e il suo titolo;
  - la cartella dei risultati e il suo `meta.json`;
  - gli argomenti (`topics.json`) e le assegnazioni finestra → argomento;
  - **tutte** le finestre della cartella di finestre, anche quelle escluse dal fit;
  - i messaggi per id e il testo di ogni finestra;
  - i vettori E5 grezzi di ogni finestra con embedding.

  `min_words` è la soglia di parole usata da `discover`. `facets` la riusa per decidere quali finestre possono ricevere un facet.
- `load_chat_result` ricostruisce tutto a partire dalla cartella dei risultati: `meta.json` indica la cartella delle finestre, da lì si trovano gli embedding (`data/embeddings/<chat>/<hash>`) e l'export (`data/exports/<chat>.json`).
- `latest_topics_dirs`: per ogni chat, il risultato di `discover` scritto per ultimo, in base alla data di `meta.json`.
