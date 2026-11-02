# scripts/ — script di utilità

> Nota di progettazione iniziale. Alcune parti descrivono moduli previsti ma non ancora scritti (`courses.py`, `synth.py`, `interactive.py`, la REPL): sono lavoro futuro, vedi il README.

Script lanciabili a mano per operazioni "batch" o di manutenzione. Come la CLI,
contengono solo orchestrazione: la logica sta in `core/`.

---

## `run_ingest.py`

**Scopo:** eseguire la pipeline completa di indicizzazione di uno o più export di chat, dall'inizio alla fine.

- Prendere uno o più percorsi (file o cartella, es. tutto `data/raw/`) e la sorgente (`telegram` per ora).
- Eseguire in ordine: `ingest` → `question_detect` → `chunking` → `embeddings.embed_passages` (a batch) → `vectorstore.upsert` → (se previsto) costruzione/salvataggio dell'indice lessicale BM25.
- Essere **idempotente**: rilanciarlo sulla stessa chat non deve creare duplicati (id deterministici dei chunk). Opzione `--reset` per svuotare e ricostruire la collection (necessaria se cambi modello di embedding).
- Mostrare avanzamento e statistiche finali (messaggi letti/scartati, domande trovate, di cui senza risposta, chunk creati, tempo impiegato): su CPU l'embedding è la fase lenta, la barra di avanzamento aiuta.

**Input:** percorsi degli export + opzioni (sorgente, reset, batch size).
**Output:** collection ChromaDB popolata in `data/chroma_db/` (+ eventuale indice lessicale) e un riepilogo a terminale.

**Librerie:**
- `argparse` (stdlib) per gli argomenti. Doc: https://docs.python.org/3/library/argparse.html
- `tqdm` o `rich.progress` per la barra di avanzamento. Doc: https://tqdm.github.io/ — https://rich.readthedocs.io/en/stable/progress.html
- `pathlib` (stdlib) per gestire file/cartelle.

**Dipendenze:** `core/ingest/`, `core/question_detect.py`, `core/chunking.py`, `core/embeddings.py`, `core/vectorstore.py`, `core/courses.py`.

> Nota: la CLI avrà un sottocomando `ingest` che fa la stessa cosa. Per evitare
> di duplicare la pipeline, conviene che entrambi chiamino un'unica funzione in
> `core/` (es. `core/pipeline.py` — vedi proposte in `ARCHITECTURE.md`).
> Quando esisterà `pyproject.toml`, questo script potrebbe diventare superfluo.
