# core/annotation.py

Prepara le coppie da etichettare a mano e gestisce il file delle etichette. Le etichette servono ad allenare e misurare il modello che deciderà le unioni al posto della regola del gap.

## Librerie
Solo libreria standard: `json`, `random` (estrazione ripetibile con `random.Random(seed)`), `math.sqrt`, `itertools.pairwise` (coppie consecutive). Nessuna dipendenza nuova.

## Logica
- **Cosa si etichetta.** Una coppia è (messaggio, messaggio immediatamente precedente) nella stessa chat, nell'intervallo di date di `config.yaml`. La domanda è: il messaggio continua la conversazione del precedente?
- **Quali coppie.** Solo quelle che oggi arrivano alla regola del gap (`candidate_pairs`). Si scartano le coppie già decise da reply (padre presente ed entro `reply_max_gap`), raffica (stesso autore entro `burst_gap`) e messaggio dipendente, perché quelle regole restano come sono. Un reply troppo vecchio invece è candidato, perché l'algoritmo lo tratta come un messaggio normale. Si scartano anche i gap oltre 3 ore: lì la risposta è quasi sempre "no".
- **Campione stratificato per gap** (`GAP_BANDS`): 0–2 min, 2–5, 5–10, 10–20, 20–40, 40–90 min, 1.5–3 h. Ogni fascia ha più o meno lo stesso numero di coppie, così anche i gap lunghi, più rari, sono rappresentati. Attenzione: per questo il campione non ha le proporzioni reali della chat. Quando si misura l'accuratezza complessiva bisogna pesare ogni fascia per la sua frequenza reale (il campo `band` è salvato apposta).
- **Quante coppie per chat** (`allocate`): proporzionali alla radice quadrata del numero di candidati, con un minimo di 15. Le chat grandi ne hanno di più, ma quelle piccole non spariscono. Con 300 coppie si va da 17 (MAS, computer_ethics) a 62 (CSGeneral).
- **Coda ripetibile** (`build_queue`): stessi export, `total` e `seed` danno la stessa coda. Per riprendere una sessione basta saltare le coppie già etichettate, senza salvare uno stato.

## Formato delle etichette: JSONL
File `data/labels/merge_pairs.jsonl`, una riga per decisione:
```json
{"chat": "anndl", "chat_id": 1354492730, "message_id": 27752, "prev_id": 27751, "gap_s": 318, "band": "300-600", "label": "same", "labelled_at": "2026-10-31T23:33:30"}
```
Ogni record ha anche `source`: `human` per quelle fatte con `annotate`. I record scritti prima che il campo esistesse sono umani. Le etichette dell'assistente stanno in un altro file (vedi `docs/it/code/core/assisted_labels.md`).

Etichette possibili: `same` (stessa conversazione), `new` (argomento nuovo), `earlier` (continua un messaggio del contesto, ma non l'ultimo, cioè conversazioni intrecciate), `unsure`.

Perché JSONL e non CSV:
- **Si scrive in append**, una riga alla volta: se il programma si chiude a metà, si perde al massimo l'ultima riga.
- **Annullare è facile**: si toglie l'ultima riga (`remove_last_label`).
- **Si possono aggiungere campi** in futuro senza rompere le righe vecchie.

Il file contiene **solo ID ed etichetta, niente feature né testo**. Le feature (gap, stesso autore, parole in comune...) si ricalcoleranno dagli export partendo dagli ID. Così si possono cambiare o aggiungere feature senza rifare l'annotazione. La tabella per l'addestramento (una riga per coppia, una colonna per feature) sarà un file derivato e rigenerabile, in CSV, che si apre ovunque, anche in un foglio di calcolo.

`data/labels/` non è in `.gitignore`: le etichette costano ore di lavoro manuale e non si possono rigenerare, quindi conviene versionarle. Non contengono testo dei messaggi, solo ID.

## Avanzamento
`progress(queue, records)` restituisce, per ogni chat, le coppie della coda, quante sono già etichettate e il conteggio per etichetta di tutti i record della chat. La stampa sta in `cli/annotate.py`.

## Pulizia per la blocklist
`drop_blocked_labels` toglie dal file le etichette in cui il messaggio o il precedente è di un account bloccato, e restituisce quelle tolte. `annotate` la chiama a ogni avvio, così il file resta coerente anche se la blocklist cresce dopo. Le etichette di chat non caricate (per esempio con `--chat`) restano.

## Costrutti
- `Candidate` è `frozen`: è confrontabile e hashable, così due code si confrontano con `==` (vedi i test).
- `ChatData.by_id` contiene anche i messaggi esclusi (servizio, fuori data), per mostrare l'anteprima del messaggio a cui si risponde. `position` permette di prendere il contesto attorno alla coppia in tempo costante.
- `band_of(0)` rientra nella prima fascia: due messaggi nello stesso secondo hanno gap 0, e l'intervallo `lo < gap` lo escluderebbe.
