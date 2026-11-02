# cli/merge.py

Sotto-comando `merge`, registrato in `cli/main.py`. Tre comandi: valutare, addestrare e confrontare.

## `merge evaluate [--no-embeddings] [--test-on human|assistant] [--errors] [--csv FILE] [--tree-depth 3] [--always-merge-below 120]`
1. Carica chat ed etichette (`load_setup` di `cli/labels.py`) e calcola le feature di ogni coppia etichettata, con le liste di `config/merge_cues.yaml`. Gli embedding passano dalla cache, quindi solo il primo giro è lento (2–3 minuti su CPU, poi circa 1,5 minuti).
2. **Ablazione**: ogni modello (alberi di profondità 3 e 5, foresta, boosting, logistica) viene provato su ogni insieme di feature:
   - `base`;
   - `base+density`, `base+author`, `base+group_request`, `base+continuity`;
   - `all`;
   - `all+emb`, che si salta con `--no-embeddings`.

   Tutto in leave-one-chat-out. Ogni modello unisce sempre sotto `--always-merge-below` secondi (0 = mai), come farà in `windows`. La tabella riporta l'accuratezza bilanciata, con quella della regola del gap nel titolo.
3. Per la combinazione migliore stampa:
   - accuratezza e F1 a confronto con la regola del gap;
   - l'accuratezza per fascia di gap;
   - le regole di un albero poco profondo.

Opzioni:
- `--test-on assistant`: misura sulle etichette dell'assistente invece che sulle tue. Sono circa 500 invece di 100, quindi i numeri sono più stabili, ma misurano quanto il modello imita l'assistente, non te. Serve come secondo parere, per esempio per un'ablazione con differenze piccole.
- `--errors`: elenca le coppie di test su cui il modello migliore sbaglia, con il testo di P e T. Stampa testo delle chat, quindi non va incollato fuori.
- `--csv`: scrive la tabella delle feature. Contiene identificativi, etichette e numeri, nessun testo.

### Risultato dell'ablazione (novembre 2026, 100 coppie tue e 495 dell'assistente)
| insieme | albero d5, test sulle tue | albero d5, test sulle mie |
|---|---|---|
| base | **0.89** | **0.85** |
| + density | 0.88 | 0.84 |
| + author | 0.89 | 0.84 |
| + group_request | 0.88 | 0.84 |
| + continuity | 0.89 | 0.85 |
| all | 0.88 | 0.82 |
| all + emb | 0.88 | 0.82 |

La regola del gap fa 0.69 sulle tue coppie e 0.65 sulle mie. Nessun gruppo aggiuntivo migliora, e tutti insieme peggiorano un po' l'albero, che con più feature si adatta di più al rumore. Il motivo si vede con `--errors`: delle 10 coppie sbagliate,
- circa 5 richiedono di capire il **contenuto**, per esempio un'affermazione che apre un argomento nuovo senza punto di domanda;
- circa 3 sono **risposte a un filone più vecchio** (`earlier`) o etichette ambigue;
- una è un **annuncio parallelo** che inizia con "Hi everyone";
- una è un cambio di argomento **sotto i 120 s**, che l'unione automatica impone.

Nessuno di questi casi dipende da parole che si possono elencare.

## `merge train [--model tree_d5] [--features base] [--always-merge-below 120] [--out data/models/merge_model.pkl]`
Addestra il modello scelto su **tutte** le etichette: le tue, più quelle dell'assistente per le coppie che non hai fatto tu. Lo salva con i metadati e con le liste di parole (`docs/it/code/core/merge_decider.md`), poi stampa l'id del modello e, per gli alberi, le regole.

`--features` accetta `base`, `all` oppure una lista di gruppi separati da virgola, per esempio `author,continuity`. Le feature di base ci sono sempre. Gli embedding non sono ammessi, perché in `windows` servirebbero per tutti i messaggi.

I default (`tree_d5`, `base`, 120 s) vengono dalla valutazione qui sopra. Per provare una variante senza sovrascrivere il modello di default si usa `--out`, per esempio `--features all --out data/models/merge_model_all.pkl`, e poi `merge compare --merge-model ...`.

## `merge compare [--chat NOME ...] [--merge-model FILE]`
Costruisce le finestre di ogni chat due volte, con la regola del gap e con il modello, e stampa una tabella con:
- numero di finestre;
- % di finestre da un solo messaggio;
- lunghezza media e p90 in messaggi;
- finestre chiuse dal tetto;
- unioni fatte dal gap rispetto a quelle fatte dal modello.

Non scrive nulla su disco. Per leggere le finestre si usa `windows <chat> --merge-model FILE`. Su tutte le chat impiega circa 2 minuti.

## Costrutti
- `rich.markup.escape` sui nomi dei modelli: rich leggerebbe `[base]` come markup e lo farebbe sparire.
- I log di parser, finestre ed embedding sono silenziati se non si passa `-v`.
