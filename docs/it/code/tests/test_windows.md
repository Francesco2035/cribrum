# tests/test_windows.py

## Librerie
- `pytest`: test con semplici `assert`; `@pytest.mark.parametrize` esegue lo stesso test su più input (qui il testo come stringa e come lista di pezzi).

## Logica
I messaggi sono costruiti a mano con `msg(id, secondi_da_T0, autore, ...)`, e i parametri sono fissati nel test (`PARAMS`), indipendenti da `config/windows.yaml`, così cambiare la configurazione non rompe i test. I token si contano a parole (`word_count`) per non caricare il tokenizer.

Casi coperti: catena di reply con gap grandi, reply troppo vecchio, raffica dello stesso autore, messaggio dipendente, menzione, soglia di gap diversa per corso/generale, tetto in messaggi (con redirect dei legami) e in token (con overlap), reply orfano, servizio escluso ma contato, nessun mescolamento fra chat, finestre corte marcate e non scartate, normalizzazione del testo, hash della configurazione.

## Esecuzione
```
uv run pytest            # tutti
uv run pytest -k reply   # solo i test con "reply" nel nome
```
`pythonpath = ["."]` in `pyproject.toml` (`[tool.pytest.ini_options]`) rende importabili `core` e `cli` dalla radice del progetto.
