# config/topics.yaml

Parametri di `discover` (BERTopic). Tutti si possono sovrascrivere dalla CLI per una prova; i risultati di ogni combinazione finiscono in una cartella diversa.

| chiave | default | significato |
|---|---|---|
| `min_words` | 5 | le finestre con meno parole restano fuori dal fit: sono saluti, "ok" e simili, che formerebbero argomenti fittizi |
| `min_topic_size` | 10 | il gruppo più piccolo che conta come argomento (`min_cluster_size` di HDBSCAN). Per chat piccole come MAS conviene 5 |
| `min_samples` | null | quanto HDBSCAN è prudente: più alto vuol dire più outlier. `null` = uguale a `min_topic_size` |
| `cluster_selection` | leaf | `eom` dà pochi argomenti grandi (in MAS: 2, "esame" e "teoria dei giochi"); `leaf` ne dà molti, più specifici (in MAS: 11 con dimensione minima 5) |
| `n_neighbors` | 15 | UMAP: piccolo = struttura locale (argomenti piccoli), grande = struttura globale |
| `n_components` | 5 | dimensioni a cui UMAP riduce i vettori prima di HDBSCAN |
| `random_state` | 42 | seme di UMAP: stessi input e parametri danno gli stessi argomenti |
| `center_languages` | true | toglie la componente "lingua" dagli embedding, perché l'italiano e l'inglese sullo stesso tema non finiscano in argomenti separati (vedi `docs/it/code/core/topics.md`) |
| `ngram_max` | 2 | le parole chiave possono essere coppie di parole ("grand coalition") |
| `min_df` | 2 | una parola chiave deve comparire in almeno 2 finestre |
| `top_n_words` | 10 | parole chiave salvate per argomento |
| `n_examples` | 3 | finestre di esempio per argomento nel report |
| `stop_words_file` | `config/topic_stopwords.yaml` | parole escluse dalle parole chiave |

## Come scegliere
- **Troppi outlier** (oltre il 40%): abbassare `min_samples` (per esempio 3), oppure passare a `eom`.
- **Argomenti troppo generici**: usare `leaf` e un `min_topic_size` più piccolo.
- **Argomenti doppi** in due lingue: controllare che `center_languages` sia attivo.
- **Parole chiave inutili** ("grazie", "raga"): aggiungerle a `config/topic_stopwords.yaml`.

Prime prove (finestre fatte con il modello delle unioni, `leaf`):
- MAS: 11 argomenti, con dimensione minima 5;
- datamining: 13 argomenti, con dimensione minima 10;
- t2i: 14 argomenti, con dimensione minima 10.

In tutte circa il 36–38% delle finestre resta senza argomento.
