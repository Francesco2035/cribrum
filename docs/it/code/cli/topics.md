# cli/topics.py

I comandi `embed` e `discover`, registrati in `cli/main.py` come comandi di primo livello. Entrambi prendono una **cartella di finestre** (`data/windows/<chat>/<hash>`, stampata da `windows` alla fine).

## `embed WINDOWS_DIR [--force]`
Calcola un vettore per finestra (`core/window_embeddings.py`) e lo salva in `data/embeddings/<chat>/<hash>/`. Se esistono già vettori per lo stesso modello e le stesse finestre non ricalcola nulla; `--force` forza il ricalcolo. Le finestre senza testo, cioè fatte solo di media, sono saltate.

Tempi su CPU: circa 30 s per MAS (216 finestre), qualche minuto per le chat grandi.

## `discover WINDOWS_DIR [--topics-config config/topics.yaml] [--min-topic-size N] [--min-samples N] [--n-neighbors N] [--min-words N] [--cluster-selection eom|leaf] [--center-languages/--no-center-languages]`
Applica BERTopic agli embedding salvati (`core/topics.py`) e scrive in `data/topics/<chat>/<hash finestre>/<hash argomenti>/`:
- `topics.md`: il report da leggere, con le parole chiave di ogni argomento e il testo delle finestre più centrali;
- `topics.json`: argomenti, parole chiave con peso, esempi, centroidi;
- `assignments.jsonl`: per ogni finestra, il suo argomento (`-1` = nessun argomento);
- `meta.json`: parametri, numero di finestre usate, outlier, conteggio per lingua.

Stampa la tabella degli argomenti, con numero di finestre e parole chiave, e la percentuale di outlier. Le finestre con meno di `min_words` parole (saluti, "ok") restano fuori dal fit. Le opzioni sovrascrivono i valori del file. Ogni combinazione di parametri ha la sua cartella, quindi più prove convivono.

Se gli embedding mancano, il comando si ferma e indica di lanciare prima `embed`.
