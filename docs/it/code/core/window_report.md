# window_report.py

## Librerie
- `random.Random(seed)`: generatore con un proprio stato, non quello globale, quindi lo stesso seed dà sempre lo stesso campione e non interferisce con altro codice.
- `json`, `dataclasses.asdict`: serializzazione delle finestre.
- `statistics.fmean`: media.

## Logica
Funzioni pure: niente `print`, perché la stampa è compito della CLI.
- `window_stats`: dizionario con tutte le statistiche di ispezione (finestre, distribuzione di messaggi e token, % di finestre da un messaggio, unioni per regola, reply orfani/vecchi, esclusi, menzioni non risolte, finestre più lunghe, percentili dei gap).
- `write_jsonl`: una finestra per riga. Contiene gli ID dei messaggi e i legami, non il testo: il testo si ricostruisce sempre dall'export grezzo.
- `write_meta`: parametri completi, hash e statistiche in `meta.json`, così si sa sempre cosa ha generato una cartella.
- `windows_markdown`: versione leggibile. Ogni riga mostra la regola e il messaggio di aggancio (`` `reply ← #123` ``), autore, ora, ID e testo; gli a capo diventano `⏎`.
- `sample_windows`: `rng.sample` estrae N finestre distinte, poi ordinate per data per comodità di lettura. Il campione serve **solo per la verifica a occhio** delle soglie: leggere 20 finestre prese a caso (e non le prime del file, tutte dello stesso periodo, o le più lunghe, che sono casi estremi) dà un'idea rappresentativa di come la configurazione taglia le conversazioni. Non è un dato usato dalla pipeline e non influisce sulle finestre: `windows.md` le contiene sempre tutte. Il seed rende il campione ripetibile (stessa configurazione + stesso seed = stesse finestre), così si può tornare sulle stesse finestre dopo averle annotate; con una configurazione diversa le finestre cambiano e quindi cambia anche il campione.

## Costrutti
- `_distribution`: percentili "nearest rank" su lista ordinata (`ordered[int(q * n)]`), sufficienti per un'ispezione.
