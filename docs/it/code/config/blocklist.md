# config/blocklist.yaml

Account i cui messaggi vengono **esclusi** da finestre, annotazione e script di taratura. Ora contiene i due account di PoliNetwork Bot (`user386048772` "PoliNetwork Bot 🤖" e `user768169879` "PoliNetwork Bot 3"), che sono di gran lunga i più presenti in CSGeneral (circa 1.770 messaggi) e t2i (140).

Si gestisce da CLI (`blocklist list | add | remove`, vedi `COMANDI.md`), ma si può anche modificare a mano.

Effetti:
- i messaggi bloccati sono esclusi come quelli di servizio e contati in `excluded.blocked` nelle statistiche;
- l'elenco entra nell'hash della configurazione, quindi cambiare la blocklist produce una cartella nuova in `data/windows/`;
- un reply a un messaggio bloccato è contato in `replies_to_excluded` e il messaggio prosegue con le regole successive;
- all'avvio di `annotate`, le etichette che riguardano un account bloccato (come messaggio o come precedente) vengono tolte dal file delle etichette.

Gli export in `data/exports/` non vengono toccati. Ricerca e `ingest` non usano la blocklist.
