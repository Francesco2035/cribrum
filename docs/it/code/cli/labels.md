# cli/labels.py

Sotto-comando `labels` (registrato in `cli/main.py` con `app.add_typer`) per le etichette proposte dall'assistente.

## Comandi
- `labels export [--size 100] [--batches N] [--calibration]`: scrive N blocchi di coppie non ancora etichettate dall'assistente in `data/labels/batches/batch_NNN_pairs.md`. Con `--calibration` esporta invece le coppie che hai già fatto tu (`batch_NNN_calibration.md`). Coppie esportate ma non ancora importate vengono riesportate al giro dopo: per lavorare in parallelo si usa `--batches N`, che produce N file con coppie diverse.
- `labels import FILE...`: legge le risposte (`<chat>:<id> <etichetta> <high|low>`) e le aggiunge a `data/labels/claude_pairs.jsonl`, segnalando righe malformate e coppie sconosciute.
- `labels review`: mostra una alla volta le coppie su cui l'assistente era incerto, con la sua proposta. Invio = accetta; `y`/`n`/`e`/`?` = cambia etichetta; `k` = salta; `q` = esci. Ogni decisione è salvata subito, quindi si può interrompere in qualsiasi momento.
- `labels status`: tabella delle tue etichette, tabella di quelle dell'assistente (per etichetta, a bassa sicurezza, riviste, da rivedere) e accordo tra voi due.

## Logica
`load_setup` fa la preparazione comune anche ad `annotate`:
- legge le date da `config.yaml` e la blocklist;
- carica gli export;
- toglie da entrambi i file le etichette degli account bloccati;
- costruisce le coppie candidate e la coda umana.

Le costanti in cima al file fissano percorsi e code: umana 300 coppie con seed 42, assistente 3000 coppie con seed 7.

## Costrutti
- `LabelSetup.params`: i `WindowParams` effettivi (date, blocklist), usati da `merge evaluate` per le soglie del gap per tipo di chat.
- `LabelSetup.by_key()` / `by_stem_id()`: indici delle candidate per `(chat_id, message_id)` e per `(nome export, message_id)`. Il secondo serve perché le risposte usano il nome dell'export, più leggibile dell'ID numerico della chat.
