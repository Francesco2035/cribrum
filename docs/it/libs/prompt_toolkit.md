# prompt_toolkit

Sostituisce `input()` nelle applicazioni interattive con un prompt "vero":
cronologia (frecce su/giù), ricerca nella cronologia (Ctrl+R), autocompletamento
(Tab), suggerimenti in grigio, editing multilinea. È la libreria su cui è
costruito IPython.

Doc: https://python-prompt-toolkit.readthedocs.io/ —
sezione più utile: "Asking for input (prompts)".

## Concetti chiave

- **`PromptSession`**: il prompt. Si crea **una volta sola** fuori dal ciclo, così la cronologia resta tra un comando e l'altro.
- **History**: `InMemoryHistory` (default, persa all'uscita) o `FileHistory(path)` (salvata su disco).
- **Completer**: fornisce i suggerimenti per il Tab. Esistono già `WordCompleter` (lista di parole) e `NestedCompleter` (comandi con sotto-argomenti).
- **AutoSuggest**: mostra in grigio il completamento preso dalla cronologia; si accetta con →.
- **Uscita**: Ctrl+C solleva `KeyboardInterrupt` e Ctrl+D solleva `EOFError`. Vanno gestite tutte e due.

## Esempio di REPL

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import NestedCompleter

completer = NestedCompleter.from_nested_dict({
    "/help": None,
    "/quit": None,
    "/synth": None,
    "/course": {"AM1": None, "Fisica1": None},   # in Cribrum: generato da courses.py
})

session = PromptSession(
    history=FileHistory(".cribrum_history"),
    auto_suggest=AutoSuggestFromHistory(),
    completer=completer,
)

while True:
    try:
        line = session.prompt("cribrum> ").strip()
    except KeyboardInterrupt:     # Ctrl+C: annulla la riga, non esce
        continue
    except EOFError:              # Ctrl+D: esce
        break

    if not line:
        continue
    if line.startswith("/"):
        if line == "/quit":
            break
        ...  # gestione comandi
    else:
        ...  # ricerca
```

## Convivenza con rich

Funzionano bene insieme: prompt_toolkit gestisce la riga di input e rich
stampa l'output tra un prompt e l'altro. Non serve niente di speciale.

## Trappole

- Il file di cronologia contiene le query dell'utente: mettilo in `.gitignore`, oppure in `~/.local/share/cribrum/`.
- Se crei `PromptSession` dentro il ciclo, perdi la cronologia a ogni giro.
- Da terminali "finti" (pipe, alcuni runner nell'IDE) prompt_toolkit può lamentarsi di non avere una TTY. Si testa lanciandolo da un terminale vero.
