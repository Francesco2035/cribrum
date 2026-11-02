# core/assisted_labels.py

Etichette proposte da un assistente (Claude) a blocchi, tenute **separate** da quelle fatte a mano: servono per allenare, mai per misurare un modello.

## Librerie
Solo libreria standard: `re` per leggere le risposte, `collections.Counter` per la matrice di confusione.

## Logica
- **Due file separati.** Le etichette umane stanno in `data/labels/merge_pairs.jsonl`, quelle dell'assistente in `data/labels/claude_pairs.jsonl`. Così la stessa coppia può avere sia l'etichetta umana sia quella dell'assistente (serve per la calibrazione), e la sessione `annotate` conta solo le etichette umane.
- **Coda dell'assistente** (`assistant_queue`): stessa costruzione della coda umana (stratificata per fascia di gap, quote per chat), ma senza le coppie **riservate**, cioè la coda umana da 300 (seed 42) e tutte le coppie già etichettate a mano. Il campione casuale umano resta così solo umano e può fare da set di test. Default: 3000 coppie, seed 7.
- **Calibrazione** (`calibration_batch`): le coppie già etichettate a mano, che l'assistente rietichetta senza vedere le risposte. `agreement` le confronta.
- **Blocchi di testo** (`batch_text`): per ogni coppia una sezione `## <chat>:<message_id>` con il contesto. Il prefisso `P ` indica il messaggio precedente, `T ` il messaggio da decidere, `+ ` quelli dopo. I blocchi stanno in `data/labels/batches/`, che è in `.gitignore` perché contiene il testo delle chat.
- **Risposte** (`parse_answers`): una riga per coppia, `<chat>:<message_id> <same|new|earlier|unsure> <high|low>`. Le righe malformate sono segnalate, non ignorate in silenzio. `import_answers` scrive i record con `source: "claude"` e `confidence`; una coppia già presente viene sostituita.
- **Revisione** (`to_review`, `review_record`): le etichette a bassa sicurezza non ancora riviste, saltando le coppie che hai già fatto a mano. Una coppia rivista diventa `source: "claude_reviewed"`, con l'etichetta finale in `label` e la proposta originale in `claude_label`.
- **Accordo**:
  - `agreement` restituisce numero di coppie in comune, quante sono uguali e la matrice di confusione `(tua, di Claude)`. Per le coppie riviste usa la proposta originale (`claude_label`), perché si vuole misurare l'assistente, non la tua correzione.
  - `binary_agreement` misura la decisione che conta per il modello: unire (`same`) o no (`new` ed `earlier` insieme). Sono escluse le coppie in cui uno dei due ha risposto `unsure`.

## Uso delle etichette (per dopo)
- **Allenamento**: umane + `claude` + `claude_reviewed`.
- **Misura**: solo umane, e solo quelle della coda casuale.
