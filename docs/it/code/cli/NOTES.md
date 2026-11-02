# cli/ — interfaccia a riga di comando

> Nota di progettazione iniziale. Alcune parti descrivono moduli previsti ma non ancora scritti (`courses.py`, `synth.py`, `interactive.py`, la REPL): sono lavoro futuro, vedi il README.

Strato **sottile**: legge l'input dell'utente, chiama le funzioni di `core/`,
formatta l'output. Nessuna logica di ricerca/ingest qui dentro: se ti accorgi
di scrivere qualcosa che servirebbe anche alla GUI, va spostato in `core/`.

---

## `__init__.py`

**Scopo:** rendere `cli` un package, così si può lanciare con `python -m cli.main`.

- Può restare vuoto.
- **Input/Output:** nessuno.
- **Librerie:** nessuna.
- **Dipendenze:** nessuna.

---

## `main.py`

**Scopo:** entry point della CLI: interpreta i sottocomandi e smista verso `core/` o verso la REPL.

- Sottocomandi previsti (indicativi):
  - `ingest <percorso> [--source telegram]` → indicizza un export (riusa la stessa logica di `scripts/run_ingest.py`).
  - `search "<query>" [--top-k N] [--course X] [--synth]` → ricerca one-shot, utile anche per test veloci.
  - `repl` (o nessun argomento) → avvia la modalità interattiva di `interactive.py`.
  - `stats` → numero di messaggi/chunk indicizzati, modello di embedding in uso, ecc.
- Caricare `config.yaml` una volta e passarlo a `core/`.
- Tradurre le eccezioni di `core/` in messaggi leggibili ed exit code sensati.

**Input:** argomenti da riga di comando.
**Output:** testo su terminale + exit code.

**Librerie:** 
- `argparse` (stdlib) — zero dipendenze. Doc: https://docs.python.org/3/library/argparse.html
- oppure `typer` — più comodo per sottocomandi, help automatico dai type hint. Doc: https://typer.tiangolo.com/
- `rich` per output formattato (tabelle, colori, evidenziazione). Doc: https://rich.readthedocs.io/

**Dipendenze:** `core/search.py`, `core/synth.py`, `core/ingest/`, `cli/interactive.py`.

---

## `interactive.py`

**Scopo:** REPL interattiva: l'utente scrive domande in linguaggio naturale e vede i risultati, senza ricaricare il modello a ogni query.

- Caricare **una volta** modello di embedding e collection all'avvio (è la parte lenta), poi ciclo domanda → risultati.
- Mostrare per ogni risultato: estratto del chunk, chat, data, autore (o anonimo), punteggio, e soprattutto l'esito esplicito: *risposta trovata* / *domanda trovata ma senza risposta* / *nessun risultato rilevante*.
- Comandi speciali con prefisso (es. `/synth` per chiedere la sintesi LLM sugli ultimi risultati, `/course AM1` per impostare un filtro, `/more` per altri risultati, `/help`, `/quit`).
- Cronologia comandi e (opz.) autocompletamento dei nomi corso/prof presi da `courses.py`.

**Input:** righe digitate dall'utente.
**Output:** risultati formattati a terminale; nessun valore di ritorno significativo.

**Librerie:**
- `prompt_toolkit` per cronologia, autocompletamento, editing della riga. Doc: https://python-prompt-toolkit.readthedocs.io/
  - Alternativa minima: `input()` + modulo `readline` (stdlib, su Linux dà già cronologia e frecce). Doc: https://docs.python.org/3/library/readline.html
- `rich` per il rendering dei risultati (pannelli, tabelle, testo evidenziato). Doc: https://rich.readthedocs.io/

**Dipendenze:** `core/search.py`, `core/synth.py`, `core/courses.py` (per autocompletamento/filtri), `core/models.py` (per leggere i `SearchResult`).
