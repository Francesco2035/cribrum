# cli/vault.py

Comando `export`, registrato in `cli/main.py` come comando di primo livello.

## `export [--by facets|topics] [--facets-dir DIR] [TOPICS_DIR ...] [--vault vault] [--vault-config config/vault.yaml]`
Genera il vault Obsidian in due modi:
- **`--by facets`** (default se `facets` è stato eseguito almeno una volta): il vault è organizzato per facet (`docs/it/code/core/facet_vault.md`). Usa il risultato di `facets` più recente, oppure quello passato con `--facets-dir`, e le cartelle di `discover` registrate nel suo `meta.json`. Così argomenti, finestre e facet sono sempre coerenti tra loro.
- **`--by topics`**: la prima versione, una nota per argomento di ogni chat (`docs/it/code/core/vault.md`). Usa le cartelle passate oppure il risultato più recente di `discover` per ogni chat. I collegamenti tra argomenti di chat diverse si calcolano nello spazio comune (`shared_space` di `core/facets.py`).

In entrambi i casi a ogni export si riscrivono solo le cartelle generate (`chats/`, `facets/`, `notes/`, `concepts/`, `topics/`, `index.md`). `.obsidian/` e le note scritte a mano restano. Alla fine il comando stampa quante note ha scritto.

## Aprire il vault
In Obsidian: *Open folder as vault* → la cartella `vault/` del progetto. Dopo un nuovo export Obsidian aggiorna le note da solo. Le impostazioni che cambi (per esempio i colori del grafo) stanno in `vault/.obsidian/` e non vengono toccate. I colori di default, scritti solo se `graph.json` non esiste, sono: chat arancioni, facet verdi, note (chat, facet) e argomenti blu, concetti grigi.
