# core/vault.py

Funzioni comuni del vault Obsidian (passo B6 di `docs/it/plans/graph_workflow.md`) e vault **per argomenti** (`export --by topics`). Il vault **per facet**, il default, usa queste funzioni ed è descritto in `docs/it/code/core/facet_vault.md`. Contiene solo funzioni che trasformano dati in testo e scrivono file; la lettura dei risultati è in `cli/vault.py`.

## Librerie
- `numpy`: similarità coseno tra centroidi.
- `yaml`: frontmatter delle note e `config/vault.yaml`.
- `shutil`, `json`: pulizia delle cartelle generate e `graph.json`.

## Struttura del vault per argomenti
```
vault/
  index.md                       elenco delle chat
  chats/<titolo chat>.md         una nota per chat: i suoi argomenti
  topics/<chat>/<chat> - <parole chiave>.md   una nota per argomento
  .obsidian/graph.json           colori della vista a grafo (scritto solo la prima volta)
```

## Logica
- **Nomi delle note** (`safe_name`, `topic_label`, `assign_names`): `<chat> - <prime 3 parole chiave>`.
  - Si saltano le parole chiave già contenute in una precedente, così "coalition" non è seguita da "grand coalition".
  - Si tolgono i caratteri che Obsidian non accetta nei link (`/ : * ? " < > | # ^ [ ]`).
  - Se due note avrebbero lo stesso nome, alla seconda si aggiunge l'id dell'argomento.
- **Collegamenti tra argomenti** (`link_similar`): ogni nota collega le `top_k` note più simili, di qualunque chat, con coseno tra centroidi ≥ `min_similarity`. Il numero tra parentesi è la similarità. Si limita a pochi vicini sopra soglia per evitare il "blob" di un grafo in cui tutto è collegato a tutto.
- **Note argomento** (`render_topic_note`):
  - frontmatter con `type`, chat, id, numero di finestre, periodo, parole chiave e tag `topic` e `chat/<chat>`;
  - link alla nota della chat;
  - argomenti collegati;
  - le finestre come citazioni, una riga per messaggio con autore e ora.

  Si mostrano al massimo `max_windows` finestre: le più centrali dell'argomento, poi in ordine di data.
- **Testo dei messaggi** (`clean_text`): una riga sola, troncata a `max_message_chars`. `#` e `[[ ]]` vengono neutralizzati con `\`, altrimenti un "#esame" in un messaggio diventerebbe un tag e un `[[` un link nel grafo.
- **Note chat** e **indice**: l'elenco degli argomenti della chat (con il numero di finestre) e l'elenco delle chat.
- `topic_windows`: le finestre di ogni argomento, dalla più vicina al centroide. Gli outlier (`-1`) non hanno una nota; il loro numero compare nella nota della chat.
- **Rigenerazione** (`reset_generated`): a ogni export si cancellano solo le cartelle che `export` possiede (`GENERATED`: `chats/`, `topics/`, `facets/`, `notes/`, `concepts/`, `index.md`). `.obsidian/`, che contiene le impostazioni che cambi in Obsidian, e le note scritte a mano in altre cartelle restano. `write_graph_settings` scrive i colori del grafo per cartella (chat arancioni, facet verdi, note e argomenti blu, concetti grigi) solo se `graph.json` non esiste ancora.

## Attenzione
Il vault contiene il testo e i nomi degli autori delle chat: è in `.gitignore` e non va condiviso.
