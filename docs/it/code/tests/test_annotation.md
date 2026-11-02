# tests/test_annotation.py

(I test della blocklist sono in `tests/test_blocklist.py`.)

## Librerie
- `pytest`, con la fixture `tmp_path` (cartella temporanea per il file delle etichette).
- `rich.Console(file=StringIO())`: la sessione stampa su un buffer invece che sul terminale.

## Logica
Riusa `msg` e `PARAMS` da `test_windows.py`: messaggi costruiti a mano, parametri fissi.

Casi coperti:
- le coppie decise da reply, raffica e messaggio dipendente sono escluse, e così quelle con gap oltre le fasce;
- un reply troppo vecchio è invece candidato;
- i confini delle fasce di gap;
- la coda è ripetibile con lo stesso seed, copre tutte le chat (minimo 15 per chat) e non ha doppioni;
- il file delle etichette: aggiunta, lettura, undo;
- l'avanzamento per chat (coppie fatte nella coda, conteggi per etichetta);
- una sessione completa con tasti simulati: etichetta, undo, tasto ignorato, uscita, e poi ripresa dalla coppia successiva.
