# cli/facets.py

Comando `facets`, registrato in `cli/main.py` come comando di primo livello.

## `facets [TOPICS_DIR ...] [--facets-config config/facets.yaml] [--merge-similarity X] [--min-chats N] [--member-percentile P]`
1. Carica i risultati di `discover`: le cartelle passate oppure, di default, la più recente di ogni chat. Stampa quale ha usato per ogni chat.
2. Calcola i facet e le assegnazioni (`docs/it/code/core/facets.md`) e li salva in `data/facets/<hash>/`.
3. Stampa:
   - la tabella dei facet: prima i condivisi, poi per dimensione, con tipo, numero di chat, finestre assegnate ed etichetta;
   - un riepilogo: argomenti → facet, quanti condivisi, quante finestre hanno un facet tramite argomento o per vicinanza, quante ne restano senza.

Le opzioni sovrascrivono i valori del file. Ogni combinazione di parametri e di ingressi ha la sua cartella. `export` usa di default il risultato più recente.

Tempo: circa 20 s per 9 chat.
