# core/topics.py

Scoperta degli argomenti con BERTopic sulle finestre di una chat (passo A3 di `docs/it/plans/graph_workflow.md`). I risultati vanno in `data/topics/<chat>/<hash finestre>/<hash argomenti>/`.

## Librerie
- `bertopic` (nuova dipendenza, aggiunta con `uv add bertopic`). Porta con sé:
  - `umap-learn`: riduce i vettori a poche dimensioni;
  - `hdbscan`: raggruppa le finestre e lascia fuori quelle che non appartengono a nessun gruppo (gli outlier);
  - `numba` / `llvmlite` / `pynndescent`, usati da UMAP;
  - `pandas` e `plotly`, usati internamente da BERTopic.

  Tutto offline: gli embedding sono calcolati da noi e passati già pronti (`embedding_model=None`), quindi BERTopic non scarica né ricalcola nulla.
- `scikit-learn`: `CountVectorizer` per le parole chiave e la lista di parole inglesi da escludere.
- `yaml`, `hashlib`, `json`: configurazione e hash.

## Logica
- `TopicParams` / `load_topic_params`: parametri da `config/topics.yaml`, spiegati in `docs/it/code/config/topics.md`. Rifiuta le chiavi sconosciute e accetta gli override della CLI.
- `load_stop_words`: la lista inglese di scikit-learn più le liste italiane e specifiche delle chat di `config/topic_stopwords.yaml`. Valgono solo per le parole chiave, non per gli embedding.
- `params_hash`: hash dei parametri **e** delle parole escluse. Cambiare uno dei due produce una cartella nuova, così i risultati diversi si confrontano affiancati.
- **Centratura per lingua** (`guess_language`, `center_by_language`, attiva per default).
  - Gli embedding multilingue mettono vicine le finestre della stessa lingua. Senza correzione, in MAS "exam, course" ed "esame, lezione" uscivano come due argomenti distinti.
  - La lingua di ogni finestra si stima contando poche parole molto frequenti in italiano o in inglese. Poi si sottrae il vettore medio di ogni lingua e si rinormalizza: quello che resta descrive soprattutto l'argomento.
  - È una correzione approssimativa, perché le finestre miste vengono assegnate alla lingua prevalente.
  - Una lingua con meno di `MIN_LANGUAGE_GROUP` (10) finestre non viene centrata: la sua media non è affidabile, e con una sola finestra il vettore diventerebbe zero.
- `fit_topics`: UMAP (coseno, `random_state` fisso) → HDBSCAN → parole chiave c-TF-IDF.
  - `language="multilingual"` serve perché con l'impostazione inglese BERTopic toglie ogni carattere non ASCII prima di calcolare le parole chiave ("perché" diventava "perch", "più" diventava "pi").
  - `n_neighbors` e `min_df` vengono limitati alla dimensione della chat, così funziona anche con poche finestre.
- `summarize`: per ogni argomento, compresi gli outlier (`-1`), registra la dimensione, le parole chiave con il loro peso, il centroide normalizzato e le finestre più vicine al centroide (esempi). Il centroide servirà al consolidamento tra chat (passo A4).
- `save_topics` scrive `topics.json`, `assignments.jsonl` (finestra → argomento) e `meta.json`. `topics_markdown` produce un report leggibile: per ogni argomento le parole chiave e il testo delle finestre più centrali, con gli outlier in fondo.

## Costrutti
- Le librerie pesanti (`bertopic`, `umap`, `hdbscan`) sono importate dentro `fit_topics`: gli altri comandi della CLI non pagano il loro tempo di caricamento.
- `token_pattern=r"(?u)\b[^\W\d_]{2,}\b"`: come parole chiave contano solo sequenze di almeno 2 lettere, quindi niente numeri. Gli apostrofi spezzano le parole ("all'esame" diventa "all" + "esame"), e i resti come "all" e "dell" sono nella lista di esclusione.
