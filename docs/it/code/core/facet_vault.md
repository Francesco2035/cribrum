# core/facet_vault.py

Note del vault organizzato per facet. Usa le funzioni comuni di `core/vault.py`: nomi sicuri, etichette, citazioni delle finestre, frontmatter.

## Struttura
```
vault/
  index.md                          chat + facet condivisi (dal più diffuso)
  chats/<titolo chat>.md            facet condivisi presenti nella chat e concetti propri
  facets/<parole chiave>.md         facet condiviso: il nodo che collega le chat
  notes/<chat>/<chat> · <facet>.md  le finestre di una chat su un facet condiviso
  concepts/<chat>/<chat> - <parole chiave>.md   facet locale: un concetto di una sola chat
```
Nel grafo, le chat sono collegate tra loro attraverso i facet condivisi: chat → nota (chat, facet) → facet → nota (altra chat, facet) → altra chat.

## Logica
- `facet_views` legge `facets.json`, i prototipi e le assegnazioni. Per ogni facet raccoglie, chat per chat, le finestre con la loro similarità, dalla più centrale. I facet senza finestre non producono note.
- `name_facets`: un facet condiviso si chiama con le sue parole chiave (`topic_label`); un facet locale porta anche il nome della chat, perché è un concetto di quella chat. In caso di nomi uguali si aggiunge l'id.
- `link_facets`: i facet più simili per prototipo (`top_k`, `min_similarity` di `config/vault.yaml`), nella sezione "Related facets".
- Le finestre entrate nel facet per vicinanza (`source: nearest`) sono marcate con ↳, per distinguerle da quelle che ci sono arrivate attraverso un argomento.
- Ogni nota mostra al massimo `max_windows` finestre, le più centrali, poi in ordine di data.
