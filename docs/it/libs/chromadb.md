# ChromaDB

Database vettoriale: salva vettori, testi e metadati, e trova rapidamente i
vettori più vicini a una query (con un indice HNSW). In modalità
`PersistentClient` è una cartella su disco (`data/chroma_db/`), senza server.

Doc: https://docs.trychroma.com/

## Concetti chiave

- **Client**: la connessione al DB. `PersistentClient(path=...)` salva su disco.
- **Collection**: l'equivalente di una tabella. Ogni elemento ha:
  - `id` (stringa, univoca, scelta da te)
  - `embedding` (il vettore)
  - `document` (il testo, opzionale ma comodo)
  - `metadata` (dict di valori **scalari**: str, int, float, bool)
- **Distanza**: con la metrica coseno, `distance = 1 - similarità` (quindi più bassa è, meglio è). Il default è `l2`: va impostato esplicitamente.

## Uso

```python
import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="data/chroma_db",
    settings=Settings(anonymized_telemetry=False),   # niente dati in uscita
)

col = client.get_or_create_collection(
    name="chunks",
    metadata={"hnsw:space": "cosine"},   # vedi nota sulle versioni sotto
)

# Scrittura: upsert = inserisci o aggiorna se l'id esiste già (idempotente)
col.upsert(
    ids=["tg-123-456"],
    embeddings=[[0.01, -0.2, ...]],               # calcolati da noi
    documents=["l'esame di AM1 è tosto"],
    metadatas=[{"chat": "ing-inf-2024", "kind": "qa", "courses": "am1", "ts": 1705000000}],
)

# Lettura
res = col.query(
    query_embeddings=[q_vec],
    n_results=10,
    where={"$and": [{"kind": "qa"}, {"ts": {"$gte": 1672531200}}]},
    include=["documents", "metadatas", "distances"],
)
res["documents"][0]   # liste di liste: [0] = risultati della prima query
res["distances"][0]

col.count()                        # quanti elementi ci sono
col.get(ids=["tg-123-456"])        # lettura per id
client.delete_collection("chunks") # reset completo
```

## Filtri (`where`)

Operatori: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, combinabili con `$and` / `$or`.
C'è anche `where_document={"$contains": "AM1"}` per filtrare sul testo.
Doc: https://docs.trychroma.com/docs/querying-collections/metadata-filtering

## Trappole

- **Versioni**: l'API è cambiata tra 0.4, 0.5 e 1.x. Ad esempio, nelle versioni recenti la metrica si imposta anche con `configuration={"hnsw": {"space": "cosine"}}`. Fissa la versione e segui la doc di quella.
- **Metadati solo scalari** (almeno storicamente): una lista di corsi va salvata come stringa (`"am1|fis1"`) o come più campi bool (`course_am1: True`).
- **Non usare l'embedding function interna** di Chroma: passa sempre `embeddings=` calcolati da `core/embeddings.py`, altrimenti Chroma usa un suo modello (non multilingua) e perdi il controllo sui prefissi e5.
- **Metrica fissata alla creazione**: non si cambia dopo, serve ricreare la collection.
- I risultati sono **liste di liste** (una per query): è facile dimenticare lo `[0]`.
