# rich

Output "bello" nel terminale: colori, tabelle, pannelli, barre di avanzamento,
spinner, evidenziazione. Typer lo usa già per formattare l'help.

Doc: https://rich.readthedocs.io/

## Concetti chiave

- **`Console`**: l'oggetto da cui passa tutto l'output. Creane uno per modulo (`console = Console()`) e usa `console.print(...)` al posto di `print`.
- **Markup**: stile inline tra parentesi quadre, stile BBCode.
  `console.print("[bold green]trovato[/] 3 risultati")` — `[/]` chiude l'ultimo stile aperto.
- **Renderable**: oggetti che `console.print` sa disegnare, come `Table`, `Panel`, `Text` e `Markdown`.

## Esempi

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markup import escape

console = Console()

# Tabella
table = Table(title="Risultati")
table.add_column("#", justify="right")
table.add_column("Data")
table.add_column("Testo")
table.add_column("Score", justify="right")
table.add_row("1", "2024-01-12", "l'esame di AM1 è tosto…", "0.82")
console.print(table)

# Pannello (ottimo per un singolo risultato o per l'esito)
console.print(Panel(escape(testo_messaggio), title="Domanda senza risposta", border_style="yellow"))

# Spinner mentre si carica il modello
with console.status("Carico il modello di embedding…"):
    ...  # operazione lenta

# Barra di avanzamento su un iterabile
from rich.progress import track
for batch in track(batches, description="Embedding"):
    ...
```

Per avere più controllo sulla barra (più task, tempo stimato) usa
`rich.progress.Progress`: https://rich.readthedocs.io/en/stable/progress.html

## Trappola importante: il markup nel testo delle chat

I messaggi delle chat possono contenere parentesi quadre (`[AM1] qualcuno ha le tracce?`).
Se li stampi così, rich li interpreta come markup: rischi di perdere pezzi di
testo o di ottenere un errore. Qualsiasi testo che viene dai dati va quindi
passato da **`escape()`**:

```python
from rich.markup import escape
console.print(f"[dim]{data}[/] {escape(testo)}")
```

In alternativa usa `Text(testo)`, che non interpreta il markup.

## Evidenziare parole nel testo

```python
from rich.text import Text
t = Text(testo)
t.highlight_words(["analisi", "rossi"], style="bold yellow", case_sensitive=False)
console.print(t)
```

Utile per mostrare perché un risultato è uscito, ad esempio le parole trovate
dal ramo BM25.
