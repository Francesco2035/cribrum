# cli/annotate.py

Sessione interattiva di annotazione da terminale: mostra una coppia alla volta e salva la risposta con un solo tasto.

## Librerie
- `click.getchar()`: legge un tasto senza bisogno di Invio. `click` è già installato come dipendenza di `typer`.
- `rich`: `Console.clear`, `Console.rule` (linea orizzontale) e gli stili per evidenziare la coppia.

## Cosa si vede
```
37/299 labelled overall · datamining 4/27
Data Mining · 2024-01-15
10:02  Anna: Mi pare: 1) apriori 2) clustering ...          (contesto, grigio)
10:05  Paolo: il 3 secondo me era il clustering                   (precedente, grassetto)
──────────────
10:13  Luca: qualcuno sa quando escono i voti?                   (da decidere, giallo)
──────────────
10:14  Anna: dopo il 20 credo                                 (dopo, corsivo)
```
- Contesto: 5 messaggi prima (`--before`). Il precedente, cioè quello con cui si decide l'unione, è in grassetto.
- 2 messaggi dopo (`--after`): spesso la risposta chiarisce di cosa parlava il messaggio. L'algoritmo non li vede, ma qui stiamo costruendo la risposta giusta, quindi è corretto usarli.
- Un messaggio che è un reply mostra sopra di sé `↪ reply to <autore>: "<anteprima>"`.

Tasti:
- `y` (oppure `s`): stessa conversazione;
- `n`: argomento nuovo;
- `e`: continua un messaggio più vecchio del contesto, non quello in grassetto;
- `?`: non so;
- `u`: annulla l'ultima etichetta;
- `q` (oppure Ctrl-C): esci.

Gli altri tasti vengono ignorati.

La prima riga dice a che punto sei: coppie fatte sul totale della coda, e coppie fatte sul totale della chat mostrata.

## Avanzamento per chat
`print_progress` stampa una tabella, alla fine di ogni sessione e con `annotate --status` (senza aprire la sessione):
- `queue`: coppie della coda etichettate / coppie della coda per quella chat;
- `same`, `new`, `earlier`, `unsure`: conteggi per etichetta;
- `labels`: tutte le etichette della chat nel file.

`labels` può superare il numero fatto in `queue` se il file contiene etichette che non sono nella coda attuale: per esempio fatte con un altro `--seed` o `--target`, o prima di un cambio della blocklist, che cambia i candidati. Restano valide e servono comunque all'addestramento.

## Revisione delle etichette dell'assistente
`run_review` (usata da `labels review`) mostra le coppie a bassa sicurezza con la proposta di Claude in alto. Invio accetta la proposta (`click.getchar` restituisce `\r`); `y`/`n`/`e`/`?` la cambiano; `k` salta; `q` esce. La tabella dell'avanzamento umano si chiama ora "Your labels".

## Logica
`run_session` rilegge il file delle etichette a ogni passo e mostra la prima coppia della coda non ancora etichettata. In questo modo undo e ripresa non richiedono stato: dopo un undo la coppia annullata torna a essere la prima da fare, e alla sessione successiva si riparte da dove ci si era fermati. Il file ha poche centinaia di righe, quindi rileggerlo costa niente.

## Costrutti
- `Counter.total()` (Python 3.10+) somma i conteggi; `Table.add_section()` traccia la linea prima della riga dei totali.
- `getchar` è un parametro con default `click.getchar`: nei test si passa una funzione che restituisce tasti prefissati, così la sessione si prova senza terminale.
- `markup=False` sui messaggi: il testo della chat può contenere `[...]`, che rich leggerebbe come markup.
