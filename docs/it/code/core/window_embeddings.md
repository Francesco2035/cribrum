# core/window_embeddings.py

Un vettore E5 per ogni **finestra** (passo A2 di `docs/it/plans/graph_workflow.md`), salvato in `data/embeddings/<chat>/<config_hash>/`, cioè con lo stesso hash della cartella delle finestre da cui viene. È separato dal vectorstore della ricerca, che non viene toccato.

## Librerie
- `numpy`: `vectors.npy`, la matrice delle finestre × 768.
- Il calcolo riusa `encode_passages` di `core/embeddings.py`, con il modello di `config.yaml`, offline.

## Logica
- `load_windows` legge `windows.jsonl`. `chat_and_hash` ricava chat e hash dal percorso `data/windows/<chat>/<hash>`, ed è così che si trova l'export da cui rileggere i testi.
- `window_text`: il testo di una finestra è il corpo dei suoi messaggi, uno per riga, **senza i nomi degli autori**. I nomi finirebbero nelle parole chiave degli argomenti e avvicinerebbero finestre solo perché scrive la stessa persona. Le righe vuote (media senza didascalia) sono saltate, e i messaggi di `overlap_ids` sono esclusi perché appartengono alla finestra precedente.
- `embed_texts` usa il prefisso `query: `: il clustering è un compito simmetrico, ed E5 per questi casi raccomanda lo stesso prefisso su tutti i testi.
- `save_embeddings` scrive `vectors.npy` e `meta.json`, che contiene il modello, il prefisso, gli id delle finestre nello stesso ordine delle righe, la dimensione e la data. `is_current` dice se la cache è riutilizzabile, cioè se modello e finestre sono gli stessi.
