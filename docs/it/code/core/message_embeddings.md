# core/message_embeddings.py

Embedding E5 dei singoli messaggi, salvati in una cache su disco per chat (`data/cache/message_embeddings/<chat>.npz`). Servono solo alle feature del modello delle unioni. Il vectorstore e la ricerca non vengono toccati.

## Librerie
- `numpy`: `savez_compressed` / `load` per la cache.
- Il calcolo riusa `encode_passages` di `core/embeddings.py`, con lo stesso modello di `config.yaml` (`intfloat/multilingual-e5-base`, già in cache, offline).

## Logica
- `message_vectors(chat, ids, emb_cfg)` carica la cache, calcola **solo** i messaggi mancanti, la riscrive e restituisce i vettori richiesti. Dalla seconda esecuzione non ricalcola nulla.
- I messaggi solo media o vuoti non ricevono un vettore: le feature corrispondenti restano mancanti.
- **Prefisso**: si usa `query: ` invece di `passage: `. Confrontare due messaggi è un confronto simmetrico, ed E5 per questi casi raccomanda lo stesso prefisso su entrambi i lati.
- La cartella `data/cache/` è in `.gitignore`: è rigenerabile.
