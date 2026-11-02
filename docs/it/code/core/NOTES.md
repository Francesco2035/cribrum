# core/ — logica di dominio

> Nota di progettazione iniziale. Alcune parti descrivono moduli previsti ma non ancora scritti (`courses.py`, `synth.py`, `interactive.py`, la REPL): sono lavoro futuro, vedi il README.

Tutto ciò che sta qui **non deve sapere** se viene chiamato da CLI, GUI o script.
Niente `print`, niente `input()`, niente `st.*`: solo funzioni/classi che ricevono
dati e restituiscono dati. Errori comunicati con eccezioni, non con messaggi a video.

Flusso di riferimento (dettagli in `../ARCHITECTURE.md`):

```
ingest/  →  models  →  question_detect  →  chunking  →  embeddings  →  vectorstore
                                                                         ↑
                              courses  →  search  ───────────────────────┘  →  synth (opzionale)
```

---

## `__init__.py`

**Scopo:** rendere `core` un package importabile ed eventualmente esporre l'API pubblica.

- Inizialmente può restare vuoto.
- Più avanti può ri-esportare i punti d'ingresso principali (es. la funzione di ricerca e quella di ingest) così CLI e GUI importano da un solo posto.
- **Input/Output:** nessuno.
- **Librerie:** nessuna.
- **Dipendenze:** nessuna (eventualmente importa da `search.py`, `models.py`).

---

## `models.py`

**Scopo:** definire le strutture dati condivise da tutto il progetto, indipendenti dalla sorgente (Telegram, WhatsApp, Discord…).

- Definire `Message`: id, chat/sorgente, autore (anche anonimizzato), timestamp, testo normalizzato, id del messaggio a cui risponde (`reply_to`), eventuali flag (è una domanda? è un inoltro?).
- Definire `Chunk`: l'unità che finisce nel vector DB (testo da indicizzare + lista degli id dei messaggi che lo compongono + metadati: chat, intervallo temporale, corsi/professori menzionati, tipo di chunk).
- Definire `QAThread` (o simile): una domanda + le eventuali risposte collegate, con uno stato esplicito `answered` / `unanswered`.
- Definire `SearchResult`: chunk trovato + punteggio (denso, lessicale, fuso) + provenienza, così i livelli superiori possono mostrare "perché" un risultato è uscito.

**Input/Output (concettuale):** nessuna logica; sono "contenitori" che tutti gli altri moduli si passano.

**Librerie:**
- `dataclasses` (stdlib) — sufficiente e zero dipendenze. Doc: https://docs.python.org/3/library/dataclasses.html
- In alternativa `pydantic` se vorrai validazione/serializzazione automatica (utile per la GUI o per salvare su JSON). Doc: https://docs.pydantic.dev/
- `enum` (stdlib) per stati tipo `AnswerStatus.ANSWERED / UNANSWERED` e `ChunkKind`. Doc: https://docs.python.org/3/library/enum.html
- `datetime` con timezone esplicita (Telegram esporta ora locale + `date_unixtime`).

**Dipendenze:** nessuna — è il modulo "foglia" da cui dipendono tutti gli altri. Evita import circolari: `models.py` non importa niente dal progetto.

---

## `ingest/` (sottopackage)

Vedi `ingest/NOTES.md`. In sintesi: converte export grezzi di ciascuna piattaforma in una lista di `Message` normalizzati.

---

## `question_detect.py`

**Scopo:** riconoscere quali messaggi sono domande e collegarle alle loro risposte, marcando esplicitamente quelle senza risposta.

- Classificare un messaggio come domanda con euristiche leggere: `?` finale, pattern tipici italiani ("qualcuno sa", "com'è", "chi ha fatto", "conviene", "che domande ha fatto"), lunghezza minima. Più avanti eventualmente un classificatore leggero.
- Costruire i thread domanda→risposte usando prima il campo `reply_to` (segnale forte) e poi, come fallback, i messaggi immediatamente successivi in una finestra temporale breve (segnale debole, da marcare con confidenza più bassa).
- Assegnare a ogni domanda lo stato `answered` / `unanswered` (e magari `weakly_answered` per il fallback temporale). **Mai** inventare risposte: se non c'è un collegamento, è `unanswered`.
- Scartare "risposte" non informative ("+1", "anche io", "up", emoji sole).

**Input:** lista di `Message` ordinata cronologicamente (di una chat).
**Output:** lista di `QAThread` + i `Message` annotati con flag `is_question`.

**Librerie:**
- `re` (stdlib) per le euristiche.
- Niente modelli pesanti qui all'inizio: su un T480 conviene che l'ingest resti veloce. Se servirà più precisione si può usare lo stesso modello di embedding (similarità domanda↔candidata risposta) invece di un LLM.

**Dipendenze:** `core/models.py` (`Message`, `QAThread`, stato risposta).

---

## `chunking.py`

**Scopo:** trasformare messaggi e thread in `Chunk` di dimensione adatta all'embedding, preservando il contesto conversazionale.

- I singoli messaggi di chat sono spesso troppo corti ("sì è tosto") per avere un embedding utile: raggrupparli.
- Strategie da combinare:
  - **chunk Q&A**: una domanda + le sue risposte → ottimo per il caso d'uso "esami".
  - **chunk a finestra**: N messaggi consecutivi o messaggi entro X minuti, con piccola sovrapposizione → ottimo per le opinioni su corsi/prof.
  - (opz.) **chunk singolo** per messaggi lunghi che stanno in piedi da soli.
- Rispettare il limite di token del modello di embedding (e5/bge: 512 token; restare ben sotto, es. 200-350 parole).
- Arricchire i metadati del chunk con corsi/professori riconosciuti (via `courses.py`) per poter filtrare dopo.

**Input:** `Message` + `QAThread` di una chat.
**Output:** lista di `Chunk` con testo pronto per l'embedding e metadati.

**Librerie:**
- Solo stdlib all'inizio. Per contare i token in modo esatto si può usare il tokenizer del modello (`transformers.AutoTokenizer`, già installato come dipendenza di sentence-transformers). Doc: https://huggingface.co/docs/transformers/main_classes/tokenizer
- Non serve LangChain/LlamaIndex: i loro splitter sono pensati per documenti, non per chat.

**Dipendenze:** `core/models.py`, `core/question_detect.py` (per i thread), `core/courses.py` (per i metadati).

---

## `embeddings.py`

**Scopo:** incapsulare il modello di embedding locale e l'unica cosa che sa fare: trasformare testo in vettori.

- Caricare il modello una sola volta (lazy loading) e riusarlo.
- Distinguere esplicitamente `embed_query(testo)` da `embed_passages(lista_testi)`: i modelli e5 **richiedono** i prefissi `"query: "` e `"passage: "`, altrimenti la qualità crolla. bge-m3 non li richiede, ma tenere due funzioni separate rende il cambio modello indolore.
- Encoding a batch, vettori normalizzati (`normalize_embeddings=True`) così la cosine similarity coincide col prodotto scalare.
- Forzare esecuzione su CPU e funzionamento offline dopo il primo download (`HF_HUB_OFFLINE=1`, oppure percorso locale del modello in `config.yaml`).

**Input:** stringhe (query dell'utente o testi dei chunk).
**Output:** vettori float (lista di liste o array numpy) di dimensione fissa.

**Librerie:**
- `sentence-transformers` — Doc: https://sbert.net/ (vedi "Semantic Search" e "Computing Embeddings").
- Modelli candidati (tutti multilingua, ottimizzati per retrieval query/passage):
  - `intfloat/multilingual-e5-small` (~118M param, 384 dim) — il più leggero, buono per T480. https://huggingface.co/intfloat/multilingual-e5-small
  - `intfloat/multilingual-e5-base` (~278M, 768 dim) — compromesso qualità/velocità. https://huggingface.co/intfloat/multilingual-e5-base
  - `BAAI/bge-m3` (~568M, 1024 dim) — più preciso, ma lento su CPU per l'ingest iniziale. https://huggingface.co/BAAI/bge-m3
- Nessuna API esterna (OpenAI, Cohere, ecc.).

**Dipendenze:** nessuna del progetto (riceve e restituisce tipi base). Legge il nome del modello dalla config.

> ⚠️ Se cambi modello devi reindicizzare tutto: salva nome modello + dimensione nei metadati della collection e verificali all'avvio.

---

## `vectorstore.py`

**Scopo:** unico punto di contatto con ChromaDB (persistenza locale in `data/chroma_db/`).

- Aprire/creare un `PersistentClient` e la collection, con distanza coseno.
- Inserire/aggiornare chunk (`upsert`) usando id deterministici (es. hash di chat + id messaggi) così reingestire la stessa chat non crea duplicati.
- Interrogare per vettore con filtri sui metadati (`where`: chat, corso, tipo chunk, intervallo date) e restituire documenti + metadati + distanze.
- Passare **sempre** i vettori calcolati da `embeddings.py` (non usare la embedding function interna di Chroma, così il controllo su prefissi/modello resta a noi).

**Input:** `Chunk` + relativi vettori (in scrittura); vettore query + filtri (in lettura).
**Output:** lista di risultati grezzi (id, testo, metadati, distanza).

**Librerie:**
- `chromadb` — Doc: https://docs.trychroma.com/ (vedi "Persistent Client", "Metadata Filtering"). L'API è cambiata tra versioni (0.4 → 0.5 → 1.x): fissa la versione in `requirements.txt` e controlla la doc della versione installata.
- Nota: i metadati Chroma accettano valori scalari (str/int/float/bool); liste come "corsi menzionati" vanno serializzate (es. stringa separata da `|`) o esplose in più campi booleani.
- Telemetria: disattivarla (`anonymized_telemetry=False` nei Settings) per coerenza con il requisito "nessun dato esce dalla macchina".

**Dipendenze:** `core/models.py` (`Chunk`), `core/embeddings.py` (indirettamente, chi chiama passa i vettori).

---

## `courses.py`

**Scopo:** gestire l'anagrafica di corsi e professori (nomi, sigle, alias, soprannomi) e riconoscerli nel testo.

- Caricare da `config.yaml` (o da un file dedicato tipo `data/courses.yaml`) la lista corsi con alias: "Analisi 1", "AM1", "analisi uno"; professori con cognome e varianti.
- Riconoscere menzioni in un testo (match esatto su alias normalizzati + fuzzy matching per refusi) → usato in fase di chunking (metadati) e in fase di query (filtri/boost).
- Espandere la query: se l'utente scrive "AM1", aggiungere anche gli altri alias per la parte lessicale della ricerca.
- Questo modulo è la risposta principale alla debolezza degli embedding sui nomi propri.

**Input:** testo libero (messaggio o query).
**Output:** lista di entità riconosciute (id corso/prof canonico + span + confidenza); per la query anche la lista di alias per l'espansione.

**Librerie:**
- `rapidfuzz` per il fuzzy matching veloce. Doc: https://rapidfuzz.github.io/RapidFuzz/
- `PyYAML` per leggere l'anagrafica. Doc: https://pyyaml.org/wiki/PyYAMLDocumentation
- `unicodedata` (stdlib) per normalizzare accenti/maiuscole.

**Dipendenze:** `core/models.py` (eventuale dataclass `Course`/`Professor`). Non dipende da embedding né da Chroma.

---

## `search.py`

**Scopo:** orchestrare la ricerca ibrida (densa + lessicale) e restituire risultati ordinati con una valutazione esplicita di "trovato / non trovato".

- Analizzare la query con `courses.py` (entità → filtri o boost, alias → espansione lessicale).
- **Ramo denso:** `embeddings.embed_query` → `vectorstore.query` con i filtri.
- **Ramo lessicale:** BM25 sui testi dei chunk (indice costruito all'ingest e salvato su disco, oppure ricostruito all'avvio se il corpus è piccolo).
- Fondere i due ranking con **Reciprocal Rank Fusion** (RRF): semplice, non richiede di calibrare punteggi eterogenei.
- Applicare una soglia minima di rilevanza: sotto soglia → restituire esplicitamente "nessun risultato rilevante" invece di risultati spazzatura. Per le domande sugli esami, se il match migliore è un `QAThread` `unanswered`, dirlo chiaramente ("domanda trovata, nessuna risposta nel gruppo").
- (futuro) Re-ranking con cross-encoder multilingua sui primi 20-30 risultati, se la CPU lo regge.

**Input:** stringa di query + opzioni (top_k, filtri, modalità: opinioni / esami).
**Output:** lista di `SearchResult` + un esito complessivo (`found` / `question_found_no_answer` / `not_found`).

**Librerie:**
- `rank-bm25` per il ramo lessicale (semplice, puro Python). Doc: https://github.com/dorianbrown/rank_bm25
  - Alternativa più veloce e con persistenza: `bm25s`. Doc: https://github.com/xhluca/bm25s
  - Alternativa zero-dipendenze: tabella SQLite FTS5 (stdlib `sqlite3`). Doc: https://www.sqlite.org/fts5.html
- RRF: poche righe, nessuna libreria. Paper: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- (futuro) cross-encoder via `sentence-transformers` (`CrossEncoder`), es. `BAAI/bge-reranker-v2-m3`. Doc: https://sbert.net/docs/cross_encoder/usage/usage.html

**Dipendenze:** `core/models.py`, `core/embeddings.py`, `core/vectorstore.py`, `core/courses.py`.

---

## `synth.py`

**Scopo:** produrre, **solo su richiesta esplicita**, una sintesi in linguaggio naturale dei migliori risultati usando un LLM locale via Ollama.

- Prendere pochi risultati (es. 5-10 chunk) già selezionati da `search.py`, mai l'intero corpus.
- Costruire un prompt che imponga: rispondi solo con le informazioni presenti nei messaggi forniti, cita gli id dei messaggi, se l'informazione non c'è dì "non trovato nei messaggi". Temperatura bassa.
- Se `search.py` ha già stabilito `not_found` o `question_found_no_answer`, **non** chiamare l'LLM (o chiamarlo solo per riformulare l'esito): evita che inventi.
- Gestire con grazia Ollama non avviato / modello non scaricato (eccezione chiara, la CLI deciderà cosa mostrare). Supportare lo streaming dei token per non sembrare "bloccato" su CPU lenta.

**Input:** query originale + lista di `SearchResult` + esito della ricerca.
**Output:** testo della sintesi + riferimenti ai messaggi citati (o uno stream di token).

**Librerie:**
- `ollama` (client Python ufficiale) — Doc: https://github.com/ollama/ollama-python ; API REST: https://github.com/ollama/ollama/blob/main/docs/api.md
  - In alternativa `httpx`/`requests` direttamente verso `http://localhost:11434` (unico endpoint, locale).
- Modelli adatti a CPU senza GPU (quantizzati Q4, ~2-4 GB RAM): famiglia Qwen / Llama / Gemma di taglia 1-4B, es. `qwen2.5:3b`, `llama3.2:3b`, `gemma3:4b`. Libreria modelli: https://ollama.com/library
- Nessuna API cloud.

**Dipendenze:** `core/models.py` (`SearchResult`), consuma l'output di `core/search.py`.
