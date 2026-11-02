# tests/test_facets.py

Test di `core/facets.py` e `core/facet_vault.py`, con chat finte (`ChatResult` costruiti a mano) e vettori sugli assi, così le similarità sono note.

- Parametri: override e rifiuto delle chiavi sconosciute.
- `shared_space`: contiene le finestre di tutte le chat, con norma 1.
- `topic_refs`: gli outlier sono esclusi e il centroide è quello dei membri.
- `cluster_topics`: due argomenti vicini finiscono insieme e uno lontano no; con una soglia più alta si separano; un solo argomento dà un solo gruppo.
- `build_facets`:
  - tipo `shared` o `local` secondo il numero di chat;
  - soglia uguale al percentile scelto (0 = il membro meno vicino);
  - id in ordine di dimensione;
  - l'esempio è il membro più centrale.
- `facet_keywords`: la parola comune a tutti i facet non è la prima; vincono le parole distintive.
- `assign_windows`:
  - un membro tiene il suo facet;
  - una finestra vicina entra per vicinanza;
  - una lontana resta senza facet;
  - un facet locale di un'altra chat non è assegnabile;
  - una chat senza facet non assegna nulla.
- `eligible_windows` rispetta `min_words`.
- Hash: non dipende dall'ordine degli ingressi e cambia con i parametri. Salvataggio e caricamento; `latest_facets_dir`.
- Vault per facet:
  - i facet senza finestre non hanno note;
  - nomi dei facet condivisi e locali;
  - ordine delle finestre;
  - link tra nota facet, nota (chat, facet), chat e indice;
  - marcatura ↳ delle finestre entrate per vicinanza;
  - i concetti locali non compaiono nell'indice.
