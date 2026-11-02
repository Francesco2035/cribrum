# tests/test_blocklist.py

## Librerie
`pytest` con `tmp_path`; `dataclasses.replace` per ricavare dai parametri di test (`PARAMS`) una copia con un account bloccato.

## Casi coperti
- lettura e scrittura della blocklist, con un file assente che vale come blocklist vuota ed emoji nei nomi;
- ricerca degli account per `from_id` esatto o per parte del nome, senza distinguere maiuscole e minuscole;
- i messaggi bloccati restano fuori dalle finestre e sono contati come `blocked`;
- la blocklist cambia l'hash della configurazione;
- dal file delle etichette si tolgono le coppie in cui il bot compare come messaggio o come precedente, e solo quelle.
