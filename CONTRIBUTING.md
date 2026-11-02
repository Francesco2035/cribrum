# Contributing

Thanks for wanting to help. Bug reports, ideas and pull requests are all welcome.

## Good places to start

- A new chat source (WhatsApp, Discord): a new adapter in `core/ingest/` that produces the same `ChatMessage` objects as `core/ingest/telegram.py`.
- Anything in [docs/future_work.md](docs/future_work.md), especially better conversation windows and evaluation.
- Bugs, or results that look wrong on your own chats.

If the change is large, open an issue first so we can agree on the approach.

## Setup

```bash
uv sync
uv run pytest
```

## A few rules the code follows

- **Offline.** No external APIs. Models are downloaded once and then used with `HF_HUB_OFFLINE=1`.
- **`core/` does not know about the CLI.** No `print` or `input` in `core/`; the CLI only orchestrates.
- **Nothing domain-specific in the code.** Thresholds and word lists go in `config/`; themes and names are computed from the data.
- **Every step writes its output to a folder named after the hash of its configuration**, so different configurations never overwrite each other.
- **Measure before keeping a change.** If a change is meant to improve windows, topics or facets, say how you measured it (`merge evaluate`, a sample you read, a metric).
- **Never commit chat data.** Exports, windows, embeddings, topics and the vault contain real messages; they are in `.gitignore`. Tests use small hand-written messages.
- Code and comments in English, comments only where the code is not obvious. Add or update tests in `tests/`.

## Documentation

Each source file has a page in `docs/it/code/` with the same path (`core/windows.py` -> `docs/it/code/core/windows.md`). For now these pages are in Italian; English pages are welcome too.
