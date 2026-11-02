# scripts/tune_windows.py

## Librerie
- `argparse`: opzioni da riga di comando dello script (`--exports`, `--out`, `--seed`, ...). È uno script di analisi, non un comando dell'app, quindi non sta nella CLI typer.
- `functools.lru_cache`: memorizza il conteggio dei token per testo, così le 5 configurazioni candidate tokenizzano ogni messaggio una volta sola (l'intera analisi su 9 chat richiede circa 20 s).
- `random.Random(seed)`: estrazione riproducibile delle coppie di confine.

## Logica
Per ogni export in `data/exports/`:
1. costruisce le finestre con ciascuna configurazione di `CANDIDATES` (override applicati sopra `config/windows.yaml` sul filtro date di `config.yaml` e sulla blocklist) e ne riporta le statistiche in tabella;
2. estrae le **coppie di confine**: messaggi consecutivi in cui una regola è quella decisiva (gap: autori diversi, nessun reply, non dipendente; raffica: stesso autore; reply: padre → risposta), divise per fasce di distanza (`GAP_BANDS`, `BURST_BANDS`, `REPLY_BANDS`), 3 per fascia.

Leggendo se le coppie di una fascia sono la stessa conversazione si capisce se conviene che la soglia includa quella fascia. È molto più economico che leggere centinaia di finestre intere. L'interpretazione dei risultati è in `docs/it/taratura_finestre.md`.

## Costrutti
- `sys.path.insert(0, ...)`: lo script sta in `scripts/` ma importa `core`; aggiunge la root del progetto ai percorsi di import.
- Importa funzioni "private" (`_gap`) di `core/windows.py`: accettabile per uno script di analisi, ma non va fatto dal codice dell'app.
- `rng.sample(in_band, min(PAIRS_PER_BAND, len(in_band)))`: estrae senza ripetizioni, anche quando una fascia ha meno di 3 coppie.

## Uso
```
HF_HUB_OFFLINE=1 uv run python scripts/tune_windows.py [--out data/windows/tuning/report.md] [--seed 42]
```
Per provare altre soglie basta aggiungere una voce a `CANDIDATES`.
