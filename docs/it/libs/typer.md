# typer

Costruisce CLI a partire da normali funzioni Python: i **type hint** dei
parametri diventano argomenti e opzioni, e il **docstring** diventa l'help.
È costruito sopra `click`.

Doc: https://typer.tiangolo.com/ — tutorial: https://typer.tiangolo.com/tutorial/

## Concetti chiave

- **`typer.Typer()`**: l'applicazione. Ogni funzione decorata con `@app.command()` diventa un sottocomando (`cribrum search`, `cribrum ingest`).
- **Argument vs Option**
  - *Argument*: posizionale, di solito obbligatorio → `cribrum search "testo"`
  - *Option*: con nome, di solito opzionale → `--top-k 5`
- **`Annotated[tipo, typer.Option(...)]`**: il modo moderno per aggiungere help, alias (`-k`) e validazione. Il valore di default si scrive dopo `=`.
- **Conversione automatica dei tipi**: `int`, `float`, `Path`, `bool`, `Enum`, `str | None`. Se l'utente scrive `--top-k abc`, typer mostra da solo l'errore.
- **`bool`** diventa una coppia di flag: `--synth / --no-synth`.
- **`@app.callback()`**: funzione che gira prima di qualsiasi comando, utile per le opzioni globali (`--config`). Con `invoke_without_command=True` gira anche se l'utente non specifica alcun comando.
- **`typer.Context`**: oggetto condiviso tra callback e comandi. `ctx.obj` è uno spazio libero dove mettere la config; `ctx.invoked_subcommand` dice quale comando è stato chiesto (`None` se nessuno).

## Esempio minimo

```python
from typing import Annotated
import typer

app = typer.Typer()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, verbose: bool = False):
    ctx.obj = {"verbose": verbose}
    if ctx.invoked_subcommand is None:
        print("nessun comando: qui partirebbe la REPL")

@app.command()
def hello(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Chi salutare")],
    times: Annotated[int, typer.Option("--times", "-n")] = 1,
):
    """Saluta qualcuno."""
    for _ in range(times):
        print(f"ciao {name}")
    if ctx.obj["verbose"]:
        print("fatto")

if __name__ == "__main__":
    app()
```

```bash
python app.py --help
python app.py hello Mario -n 3
python app.py --verbose hello Mario   # le opzioni del callback vanno PRIMA del comando
```

## Uscire con errore

```python
if not path.exists():
    print("file non trovato")
    raise typer.Exit(code=1)
```

Meglio usare `typer.Exit` che `sys.exit`: si integra con il runner dei test.

## Testare una CLI

```python
from typer.testing import CliRunner
from cli.main import app

def test_help():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
```

## Trappole

- Le opzioni del callback (`--config`) vanno **prima** del nome del comando.
- Se c'è un solo `@app.command()` e nessun callback, typer non crea sottocomandi: il comando diventa l'app stessa. Con più comandi, o con un callback, i sottocomandi funzionano normalmente.
- Il nome della funzione diventa il nome del comando (i `_` diventano `-`), e il docstring diventa l'help.
