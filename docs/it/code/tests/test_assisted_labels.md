# tests/test_assisted_labels.py

## Librerie
`pytest` con `tmp_path`; `rich.Console(file=StringIO())` per la sessione di revisione senza terminale.

## Casi coperti
- lettura delle risposte: righe valide, commenti, backtick, righe malformate segnalate;
- la coda dell'assistente non contiene mai le coppie riservate (coda umana);
- l'import scrive record `claude` con la sicurezza, segnala le coppie sconosciute e sostituisce i duplicati;
- il blocco di calibrazione prende le coppie umane non ancora fatte dall'assistente;
- la coda di revisione salta le etichette ad alta sicurezza, quelle già riviste e le coppie già etichettate a mano;
- l'accordo usa la proposta originale dopo una revisione; quello binario unisce `new` ed `earlier` e salta `unsure`;
- una sessione di revisione con tasti simulati: accetta (Invio), cambia, salta;
- il formato dei blocchi di testo (sezione per coppia, marcatori `P` e `T`).
