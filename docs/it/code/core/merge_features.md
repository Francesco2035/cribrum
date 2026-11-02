# core/merge_features.py

Trasforma una coppia candidata (messaggio precedente P, messaggio da decidere T) in un dizionario di numeri che il modello delle unioni può usare. Non legge etichette e non decide nulla.

## Librerie
- `scikit-learn` (`TfidfVectorizer`): matrice TF-IDF per chat. Era già installato, nessuna nuova dipendenza.
- `numpy`: prodotti scalari tra embedding.
- Libreria standard: `re`, `math`, `statistics`.

## Logica
- **Stato per chat** (`ChatFeatures`, costruito da `prepare_chat(chat, general, vectors, cue_lists)`). Contiene:
  - il gap mediano tra messaggi consecutivi;
  - la matrice TF-IDF su tutti i messaggi inclusi, con righe allineate a `chat.included`;
  - gli embedding disponibili, da `core/message_embeddings.py`;
  - la coseno media tra messaggi consecutivi;
  - le liste di parole compilate e i timestamp.

  Si calcola una volta per chat, non per coppia.
- **Feature di base** (`BASE_FEATURES`):

  | gruppo | feature |
  |---|---|
  | gap | `log_gap`, `gap_rel` (gap / gap mediano della chat) |
  | autore | `same_author`, `author_in_recent` (l'autore di T compare negli ultimi 5 messaggi, P escluso) |
  | tipo di testo | domanda in P e in T, T inizia come un'apertura ("ciao", "qualcuno", "does anyone"...), T contiene un ringraziamento |
  | lunghezze | lunghezze in parole (log), messaggi solo media |
  | reply | T o P è un reply: i reply validi sono già decisi dalla regola, quindi qui il reply va a un messaggio assente o troppo vecchio |
  | somiglianza del testo | TF-IDF con P e massimo sugli ultimi 5 |
  | chat | tipo di chat |
- **Gruppi aggiuntivi** (`FEATURE_GROUPS`), provati con l'ablazione:

  | gruppo | feature |
  |---|---|
  | `density` | messaggi nei 30 minuti prima di T, autori diversi nell'ultima ora (log) |
  | `author` | quante volte l'autore di T ha scritto nei 30 minuti prima (log); P è un reply a un messaggio dell'autore di T; negli ultimi 30 minuti qualcun altro ha risposto all'autore di T |
  | `group_request` | T si rivolge al gruppo, ovunque nel testo |
  | `continuity` | T inizia come una risposta, oppure riferendosi a qualcosa già detto |

  Le ultime due usano le liste di `config/merge_cues.yaml` (vedi `docs/it/code/config/merge_cues.md`). `ALL_FEATURES` è base + tutti i gruppi.
- **Liste di parole** (`compile_cues`): una regex per lista, sul testo normalizzato con `normalize_phrase` (lo stesso usato per le frasi dipendenti delle finestre) e per parole intere. `CUE_MODES` dice se la frase deve stare all'inizio o può stare ovunque. Le frasi sono ordinate dalla più lunga, così "i think" viene provata prima di "i".
- **Finestre di tempo**: `prepare_chat` salva i timestamp dei messaggi in ordine, e `bisect_left` trova in tempo logaritmico il primo messaggio degli ultimi 30 o 60 minuti.
- **Feature di embedding** (`EMBEDDING_FEATURES`):
  - `emb_prev`: coseno con P.
  - `emb_prev_shrunk`: la stessa coseno corretta per la lunghezza.
  - `emb_max_recent`: massimo sugli ultimi 5.
  - `emb_recent_mean`: coseno con il centroide degli ultimi 5.

  Senza vettore (messaggio solo media) valgono `NaN`, non 0. Lo 0 vorrebbe dire "molto diversi", mentre `NaN` dice "non si sa", e gli alberi di scikit-learn gestiscono i valori mancanti.
- **Shrinkage** (`shrink`): `w = parole / (parole + 5)` e `w·cos + (1−w)·media_chat`. Si usano le parole del più corto dei due messaggi. Una coseno su testi corti viene così tirata verso il valore tipico della chat invece che verso 0, che spingerebbe a separare.
- `needed_ids`: gli ID dei messaggi di cui servono gli embedding, cioè ogni T con i suoi 5 precedenti. Si calcolano solo quelli, non l'intera chat.

## Costrutti
- La matrice TF-IDF ha righe già normalizzate (L2), quindi la coseno è un semplice prodotto `righe_recenti @ riga_T.T`, fatto su matrici sparse.
