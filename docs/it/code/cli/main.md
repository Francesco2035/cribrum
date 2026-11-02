# cli/main.py

## Librerie
- `typer`: definisce i comandi a partire dalle funzioni. `Annotated[int | None, typer.Option(help=...)] = None` crea l'opzione `--nome-parametro`: gli underscore diventano trattini e `None` significa "non passata".
- `rich`: `Console.print` con markup, `Table` per le tabelle, `escape` per i testi della chat che contengono `[...]`, che rich interpreterebbe come markup.

## Logica
La CLI è uno strato sottile: legge le opzioni, chiama `core/`, stampa. I comandi esistenti (`ingest`, `search`, ...) non sono cambiati.

### Comando `windows`
```
uv run python -m cli.main windows <chat> [opzioni]
```
- `<chat>`: percorso dell'export oppure il suo nome in `data/exports` (`datamining` → `data/exports/datamining.json`).
- `--windows-config`: file dei parametri (default `config/windows.yaml`). Per confrontare due configurazioni si possono usare due file diversi, oppure gli override.
- Date: `--min-date`, `--max-date` (default dalla sezione `dates` di `config.yaml`).
- Override: `--gap-course`, `--gap-general`, `--reply-max-gap`, `--burst-gap`, `--dependent-gap`, `--mention-gap`, `--max-messages`, `--max-tokens`, `--overlap`, `--chat-type course|general`.
- Ispezione: `--sample N`, `--seed S`, `--top K` (default nella sezione `inspect` della config). Il campione serve **solo per la verifica a occhio** delle soglie: leggere 20 finestre prese a caso (e non le prime del file, tutte dello stesso periodo, o le più lunghe, che sono casi estremi) dà un'idea rappresentativa di come la configurazione taglia le conversazioni. Non è un dato usato dalla pipeline e non influisce sulle finestre: `windows.md` le contiene sempre tutte. Il seed rende il campione ripetibile (stessa configurazione + stesso seed = stesse finestre), così si può tornare sulle stesse finestre dopo averle annotate; con una configurazione diversa le finestre cambiano e quindi cambia anche il campione.
- `--merge-model FILE`: usa il modello delle unioni addestrato con `merge train` al posto della regola del gap. L'id del modello entra nell'hash, quindi l'output va in una cartella diversa da quella della regola del gap. Le soglie `--gap-course` e `--gap-general` in questo caso non hanno effetto.
- Output in `data/windows/<chat>/<config_hash>/`: `windows.jsonl`, `windows.md`, `sample.md`, `meta.json`. La cartella dipende dall'hash, quindi configurazioni diverse non si sovrascrivono.

Esempio di confronto:
```
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --gap-course 300
diff <(head -50 data/windows/datamining/<hash1>/sample.md) <(head -50 data/windows/datamining/<hash2>/sample.md)
```

### Comando `annotate`
```
uv run python -m cli.main annotate [--target 300] [--seed 42] [--chat anndl --chat UAI] [--before 5] [--after 2]
```
Etichettatura a mano delle coppie di messaggi (stessa conversazione sì/no) per allenare il modello delle unioni. Legge tutti gli export di `data/exports` (oppure solo quelli indicati con `--chat`), con le date di `config.yaml`, e accoda le risposte in `data/labels/merge_pairs.jsonl` (`--labels` per cambiare file). La sessione si può interrompere e riprendere: con lo stesso `--seed` e `--target` la coda è identica, quindi si riparte dalla prima coppia non fatta. `--status` stampa solo la tabella di avanzamento per chat. I log "Read N raw messages" del parser sono silenziati in `annotate` e `blocklist add`, salvo con `-v` (`_quiet_parser`). Dettagli: `docs/it/code/core/annotation.md` e `docs/it/code/cli/annotate.md`.

### Comando `labels`
Etichette proposte dall'assistente: `labels export | import | review | status`. Dettagli in `docs/it/code/cli/labels.md`. `annotate` usa la stessa preparazione (`load_setup`), e `annotate --status` stampa lo stesso riepilogo di `labels status`.

### Comando `blocklist`
Sotto-comando (`typer.Typer` aggiunto con `app.add_typer`) con tre azioni:
- `blocklist list`: elenca gli account bloccati;
- `blocklist add QUERY [--all]`: cerca `QUERY` tra gli autori di tutti gli export, come `from_id` esatto o come parte del nome. Se trova più account si ferma e li elenca, a meno di `--all`;
- `blocklist remove QUERY`: sblocca un account, purché `QUERY` ne indichi uno solo.

I comandi `windows` e `annotate` passano la blocklist a `load_window_params` come override `blocked_ids` (`_blocked_ids`). Dettagli: `docs/it/code/core/config.md` e `docs/it/code/config/blocklist.md`.

## Costrutti
- Gli override vengono raccolti in un dizionario e passati a `load_window_params`; quelli `None` vengono ignorati, così i default restano nel file di configurazione e non nel codice.
- `--chat-type` diventa un override di `chat_types` per il solo `chat_id` dell'export, e quindi cambia anche l'hash.

### Comando `merge`
Modello delle unioni: `merge evaluate` (confronto con la regola del gap sulle tue etichette), `merge train` (salva il modello) e `merge compare` (finestre con la regola o con il modello, a confronto). Dettagli in `docs/it/code/cli/merge.md`.

### Comandi `embed` e `discover`
Embedding delle finestre e scoperta degli argomenti con BERTopic, su una cartella di finestre (`data/windows/<chat>/<hash>`). Sono definiti in `cli/topics.py` e registrati con `app.command()(embed)`. Dettagli in `docs/it/code/cli/topics.md`.

### Comando `facets`
Raggruppa gli argomenti di tutte le chat in facet (temi condivisi tra chat e concetti locali) e assegna ogni finestra al suo facet. È definito in `cli/facets.py`. Dettagli in `docs/it/code/cli/facets.md` e `docs/it/code/core/facets.md`.

### Comando `export`
Genera il vault Obsidian in `vault/`, per facet (default) o per argomenti (`--by topics`). È definito in `cli/vault.py`. Dettagli in `docs/it/code/cli/vault.md`, `docs/it/code/core/facet_vault.md` e `docs/it/code/core/vault.md`.
