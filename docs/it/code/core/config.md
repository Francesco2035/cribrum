# core/config.py

## Librerie
- `pyyaml`: `safe_load` per leggere, `safe_dump(allow_unicode=True)` per scrivere la blocklist. Con `allow_unicode` le emoji nei nomi, come "PoliNetwork Bot 🤖", restano leggibili invece di diventare sequenze `\U0001F916`.

## Logica
- `load_config`: legge `config.yaml` (invariata).
- **Blocklist**: account i cui messaggi vengono tolti prima di costruire finestre e coppie da annotare. Sta in un file a parte, `config/blocklist.yaml` (il percorso è in `config.yaml`, `paths.blocklist`), perché la modifica la CLI: riscrivere `config.yaml` da codice ne cancellerebbe i commenti.
  - `load_blocklist(path)` restituisce `{from_id: nome}`. Se il file non c'è, la blocklist è vuota.
  - `save_blocklist(path, accounts)` riscrive il file, ordinato per `from_id`, con un commento in testa.
  - `match_accounts(authors, query)`: se `query` è un `from_id` esatto restituisce quell'account; altrimenti tutti quelli il cui nome contiene `query`, senza distinguere maiuscole e minuscole.
- `blocklist_path(cfg)`, `blocked_ids(cfg)`, `export_paths(cfg)`: ricavano dalla configurazione il percorso della blocklist, gli ID bloccati e l'elenco degli export. Le usano sia `cli/main.py` sia `cli/labels.py`.
- Si blocca per **`from_id`**, non per nome: il nome visualizzato può cambiare nel tempo o coincidere con quello di un'altra persona, mentre l'ID è stabile. Il nome nel file serve solo a chi lo legge.

## Liste del modello delle unioni
- `load_merge_cues(path)`: legge `config/merge_cues.yaml` e restituisce `{nome lista: tupla di frasi}` per le tre liste di `CUE_LISTS`. Un file o una lista mancante equivale a una lista vuota, mentre una chiave sconosciuta dà errore.
- `merge_cues_path(cfg)`: percorso da `config.yaml` → `paths.merge_cues`, default `config/merge_cues.yaml`.
