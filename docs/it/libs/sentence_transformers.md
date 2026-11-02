# sentence-transformers

Carica modelli di embedding (da Hugging Face o da una cartella locale) e
trasforma testi in vettori. Gira su CPU senza problemi, basandosi su PyTorch.

Doc: https://sbert.net/ — Semantic search: https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html

## Concetti chiave

- **Embedding**: un vettore di numeri (384 dim per e5-small, 768 per e5-base, 1024 per bge-m3) che rappresenta il *significato* di un testo. Testi con significato simile danno vettori vicini.
- **Similarità coseno**: misura quanto due vettori puntano nella stessa direzione (1 = identici, 0 = scorrelati). Se i vettori sono **normalizzati**, coincide col prodotto scalare.
- **Retrieval asimmetrico**: la query è corta ("prof severo?") e il passage è lungo (una conversazione). I modelli come e5 sono addestrati per questo e vogliono i **prefissi**:
  - `"query: "` davanti alle domande dell'utente
  - `"passage: "` davanti ai testi indicizzati
  Senza prefissi funzionano peggio in modo misurabile. bge-m3 invece non li richiede.

## Uso

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-small", device="cpu")

passages = ["passage: l'esame di AM1 è scritto + orale, orale tosto",
            "passage: fisica 1 si passa studiando gli esercizi vecchi"]
p_vecs = model.encode(passages, batch_size=32, normalize_embeddings=True,
                      show_progress_bar=True)       # numpy array (N, 384)

q_vec = model.encode("query: com'è l'orale di analisi?", normalize_embeddings=True)

scores = model.similarity(q_vec, p_vecs)            # tensore (1, N) di similarità coseno
```

## Download e funzionamento offline

- La prima volta il modello viene scaricato in `~/.cache/huggingface/` (centinaia di MB).
- Dopo, per garantire che non vada più in rete: `export HF_HUB_OFFLINE=1` (oppure passa un percorso locale al posto del nome del modello).
- Scaricare il modello a mano in una cartella: `model.save("models/e5-small")`, poi `SentenceTransformer("models/e5-small")`.

## Prestazioni su CPU (T480)

- `encode` a batch è molto più veloce che un testo alla volta.
- e5-small è l'opzione più veloce, bge-m3 è sensibilmente più lento: fai una prova su 1000 chunk prima di scegliere.
- Il limite è 512 token: il testo oltre viene **troncato in silenzio**. `model.max_seq_length` dice il limite.
- Carica il modello **una volta** e riusalo: il caricamento richiede secondi.

## Modelli

- https://huggingface.co/intfloat/multilingual-e5-small
- https://huggingface.co/intfloat/multilingual-e5-base
- https://huggingface.co/BAAI/bge-m3
- Classifica per confrontare i modelli (tab "Retrieval", filtra per lingua): https://huggingface.co/spaces/mteb/leaderboard

## Trappole

- Se cambi modello, i vettori vecchi non sono più confrontabili con quelli nuovi: bisogna reindicizzare tutto.
- Dimenticare i prefissi e5 non dà errori, solo risultati peggiori: è un bug difficile da notare.
- Le versioni recenti hanno anche `encode_query` / `encode_document`, che applicano i prefissi solo se il modello li dichiara nella sua config. Per e5 è più sicuro aggiungerli a mano.
