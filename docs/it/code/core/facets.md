# core/facets.py

Facet: temi ottenuti raggruppando gli argomenti di **tutte** le chat presenti (passi A4 e B1 di `docs/it/plans/graph_workflow.md`). Tutto è calcolato dai dati: nel codice non ci sono nomi, temi o soglie legati al dominio. Si ricalcola uguale con qualunque insieme di chat.

## Librerie
- `scikit-learn`:
  - `AgglomerativeClustering` per raggruppare gli argomenti;
  - `CountVectorizer` per le parole chiave dei facet.
- `numpy`, `yaml`, `hashlib`, `json`.

## Logica
1. **Spazio comune** (`shared_space`). Tutte le finestre con embedding di tutte le chat vengono centrate per lingua **insieme** (`center_by_language` di `core/topics.py`). Così ogni chat sta nello stesso spazio. `discover` centra chat per chat, e quegli spazi non sono confrontabili tra chat diverse.
2. **Argomenti** (`topic_refs`). Ogni argomento di ogni chat, outlier esclusi, con il centroide delle sue finestre nello spazio comune.
3. **Raggruppamento** (`cluster_topics`). Clustering agglomerativo con legame medio sulla distanza coseno.
   - Due gruppi si uniscono se la similarità media tra i loro argomenti è almeno `merge_similarity`.
   - Il **numero di facet non è fissato**: dipende da quanti temi distinti ci sono.
   - Il legame medio è stato scelto perché il legame singolo crea catene (A simile a B, B simile a C, quindi A insieme a C anche se diversi).
4. **Facet** (`build_facets`). Ogni gruppo di argomenti è un facet. Contiene:
   - **le finestre** dei suoi argomenti;
   - **il prototipo**: il centroide di quelle finestre, normalizzato;
   - **il tipo**:
     - `shared` se i suoi argomenti vengono da almeno `min_chats` chat diverse;
     - `local` altrimenti, cioè un concetto di una sola chat;
   - **la soglia di assegnazione**: il percentile `member_percentile` della similarità dei suoi membri con il prototipo. È ricavata dai dati e diversa per ogni facet: un facet compatto ha una soglia alta, uno disperso una più bassa;
   - **gli esempi**: le finestre più vicine al prototipo.

   Gli id (`F000`, `F001`, …) seguono la dimensione, con un ordine deterministico.
5. **Parole chiave** (`facet_keywords`). c-TF-IDF tra facet, con la stessa formula che BERTopic usa per gli argomenti:
   - ogni facet è un documento (il testo di tutte le sue finestre);
   - punteggio = frequenza della parola nel facet × `log(1 + parole medie per facet / frequenza totale della parola)`.

   Una parola conta se è frequente nel facet e rara negli altri. I nomi dei facet si ricavano da queste parole.
6. **Assegnazione** (`assign_windows`, `eligible_windows`). Possono ricevere un facet le finestre con embedding e con almeno `min_words` parole, la stessa soglia di `discover`.
   - Una finestra che appartiene a un argomento prende il facet del suo argomento (`source: topic`).
   - Le altre, cioè quelle rimaste fuori dagli argomenti, vanno al facet più vicino **tra quelli che la loro chat ha già tramite i propri argomenti**, se la similarità supera la soglia del facet (`source: nearest`). Altrimenti restano senza facet (`none`).
   - Per questo le chat che condividono un facet sono decise solo dagli argomenti. Questa fase recupera le finestre fuori argomento dentro i temi della loro chat.
7. **Salvataggio** (`save_facets`) in `data/facets/<hash>/`:
   - `facets.json`: per ogni facet id, tipo, parole chiave, chat, argomenti, finestre per chat, soglia, esempi;
   - `prototypes.npy`;
   - `assignments.jsonl`: chat, finestra, facet, similarità, fonte;
   - `meta.json`: parametri, cartelle di `discover` usate, conteggi.

   `facets_hash` dipende dai parametri, dalle parole escluse e dalle cartelle in ingresso. `latest_facets_dir` restituisce il risultato più recente.

## Aggiungere una chat
`windows` → `embed` → `discover` sulla chat nuova, poi `facets` e `export`. Il calcolo è deterministico: a parità di chat e parametri, stessi facet. I facet vengono ricalcolati da capo, quindi id e nomi possono cambiare quando cambiano le chat. Se servirà stabilità tra un aggiornamento e l'altro, il passo successivo è congelare i prototipi e assegnare le chat nuove a quelli (vedi `docs/it/plans/graph_workflow.md`, sezione 6).
