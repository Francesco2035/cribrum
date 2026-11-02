# Guide alle librerie

Appunti pratici sulle librerie usate in Cribrum: cosa fanno, i concetti chiave,
gli esempi minimi e le trappole. Gli esempi sono indipendenti dal progetto e
servono a capire la libreria, non sono codice da copiare così com'è.

| Libreria                                       | Dove si usa                          | Fase       |
|------------------------------------------------|--------------------------------------|------------|
| [typer](typer.md)                              | `cli/main.py`                        | CLI        |
| [rich](rich.md)                                | `cli/`, `scripts/`                   | CLI        |
| [prompt_toolkit](prompt_toolkit.md)            | REPL (prevista)                      | futuro     |
| [pyyaml](pyyaml.md)                            | caricamento `config.yaml`            | core       |
| [sentence-transformers](sentence_transformers.md) | `core/embeddings.py`              | core       |
| [chromadb](chromadb.md)                        | `core/vectorstore.py`                | core       |
| [rank-bm25](rank_bm25.md)                      | ricerca ibrida (prevista)            | futuro     |
| [rapidfuzz](rapidfuzz.md)                      | corsi e professori (previsto)        | futuro     |
| [ollama](ollama.md)                            | sintesi LLM locale (prevista)        | futuro     |

Le API cambiano tra versioni: in caso di dubbio controlla la versione installata
(`uv pip list`) e la documentazione linkata in ogni file. Le librerie segnate "futuro"
non sono tra le dipendenze: vanno aggiunte con `uv add` quando servono.
