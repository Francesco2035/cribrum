# Usage

All commands run from the project root with `uv`. `HF_HUB_OFFLINE=1` makes sure `huggingface_hub` never goes to the network; the embedding model must already be in the local cache (it is downloaded on the first run without the variable).

## Setup

```bash
uv sync                 # installs dependencies, dev ones included (pytest, ruff)
```

## Global options

They go before the command name:

```bash
uv run python -m cli.main --config config.yaml -v <command> ...
```

- `--config`: main configuration file (default `config.yaml`).
- `-v` / `--verbose`: debug logs.

## From a chat to the vault

For every chat (a new one too):

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main windows MAS --merge-model data/models/merge_model.pkl   # prints data/windows/MAS/<hash>
HF_HUB_OFFLINE=1 uv run python -m cli.main embed data/windows/MAS/<hash>
HF_HUB_OFFLINE=1 uv run python -m cli.main discover data/windows/MAS/<hash>      # small chats: --min-topic-size 5
```

Then, once for all chats:

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main facets
HF_HUB_OFFLINE=1 uv run python -m cli.main export
```

The sections below describe each command.

## Windows

```bash
# builds the windows of one chat (path, or name in data/exports)
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining

# with the merge model instead of the time-gap rule
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --merge-model data/models/merge_model.pkl

# sample to read by hand: 20 windows, seed 7, list the 10 longest
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --sample 20 --seed 7 --top 10

# comparing configurations: every run writes to a different folder (hash)
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --gap-course 300
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --windows-config config/windows_alt.yaml
```

- Dates come from the `dates` section of `config.yaml` (now from 2023-01-01). `--min-date` / `--max-date` change them for a single run.
- Overrides: `--gap-course`, `--gap-general`, `--reply-max-gap`, `--burst-gap`, `--dependent-gap`, `--mention-gap`, `--max-messages`, `--max-tokens`, `--overlap`, `--chat-type course|general`.
- `windows` does not depend on `ingest`: it reads the export directly and does not use ChromaDB.

Output in `data/windows/<chat>/<config_hash>/`:

- `windows.jsonl`: the windows (message ids, links, metadata), one per line;
- `windows.md`: all windows, readable, with the rule that linked each message (`reply ← #id`, `model ← #id`, ...);
- `sample.md`: the random sample;
- `meta.json`: parameters, hash and statistics.

Tuning over all exports at once:

```bash
HF_HUB_OFFLINE=1 uv run python scripts/tune_windows.py   # -> data/windows/tuning/report.md
```

## Blocklist

Accounts excluded from windows and annotation (bots, for example).

```bash
uv run python -m cli.main blocklist list
uv run python -m cli.main blocklist add polinetwork --all   # by name: every account containing it
uv run python -m cli.main blocklist add user386048772       # by from_id
uv run python -m cli.main blocklist remove "Bot 3"
```

The file is `config/blocklist.yaml`. Changing it changes the window hash.

## Labelling message pairs

```bash
uv run python -m cli.main annotate                    # queue of 300 pairs from all chats
uv run python -m cli.main annotate --chat datamining  # one chat only
uv run python -m cli.main annotate --status           # progress per chat
```

Keys: `y` same conversation, `n` new topic, `e` continues an older message, `?` not sure, `u` undo, `q` quit. Running the same command again (same `--target` and `--seed`) resumes from the first pair not done yet. Labels go to `data/labels/merge_pairs.jsonl`. They cannot be regenerated, so do not delete them.

### Assistant labels

Labels proposed by an LLM assistant, kept in a separate file and used only for training, never for evaluation.

```bash
uv run python -m cli.main labels status                  # your labels, the assistant's, agreement
uv run python -m cli.main labels review                  # review the pairs the assistant is unsure about
uv run python -m cli.main labels export --batches 5      # 5 text batches of 100 pairs
uv run python -m cli.main labels export --calibration    # your pairs, to be relabelled blind
uv run python -m cli.main labels import data/labels/batches/batch_002_pairs.answers.txt
```

In `review`: Enter accepts the proposal, `y`/`n`/`e`/`?` change it, `k` skips, `q` quits. Exported batches contain chat text and are ignored by git.

## Merge model

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main merge evaluate                    # gap rule vs models, on human labels
HF_HUB_OFFLINE=1 uv run python -m cli.main merge evaluate --no-embeddings    # faster, without embedding features
HF_HUB_OFFLINE=1 uv run python -m cli.main merge evaluate --test-on assistant  # second opinion, on the assistant labels
HF_HUB_OFFLINE=1 uv run python -m cli.main merge evaluate --errors           # lists the wrong pairs (prints chat text)
HF_HUB_OFFLINE=1 uv run python -m cli.main merge evaluate --csv data/cache/merge_features.csv
HF_HUB_OFFLINE=1 uv run python -m cli.main merge train                       # saves data/models/merge_model.pkl
HF_HUB_OFFLINE=1 uv run python -m cli.main merge train --features all --out data/models/merge_model_all.pkl
HF_HUB_OFFLINE=1 uv run python -m cli.main merge compare                     # windows: gap rule vs model, all chats
HF_HUB_OFFLINE=1 uv run python -m cli.main merge compare --chat datamining --chat MAS
```

- Evaluation is leave-one-chat-out, on human labels only.
- `evaluate` and `train` need the exports the labels come from, because features are computed from the messages.
- The word lists behind the text features are in `config/merge_cues.yaml`. After changing them, rerun `merge evaluate` and `merge train`.
- The first `evaluate` computes the embeddings of the messages it needs (a few minutes on CPU) and caches them in `data/cache/message_embeddings/`.
- After adding labels, rerun `merge train`. The new model has a new id, so `windows --merge-model` writes to a new folder and the old windows stay for comparison.

## Topics (BERTopic)

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main embed data/windows/MAS/<hash>                           # vectors in data/embeddings/
HF_HUB_OFFLINE=1 uv run python -m cli.main discover data/windows/MAS/<hash>                        # topics in data/topics/
HF_HUB_OFFLINE=1 uv run python -m cli.main discover data/windows/MAS/<hash> --min-topic-size 5     # small chat: smaller topics
HF_HUB_OFFLINE=1 uv run python -m cli.main discover data/windows/MAS/<hash> --cluster-selection eom  # fewer, larger topics
```

- The report to read is `topics.md`, in the folder printed at the end of `discover`.
- Parameters are in `config/topics.yaml`, excluded keywords in `config/topic_stopwords.yaml`.
- `embed` only needs to be redone when the windows change. To try other parameters, rerun `discover`.

## Facets

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main facets                            # latest discover result of every chat -> data/facets/<hash>/
HF_HUB_OFFLINE=1 uv run python -m cli.main facets --merge-similarity 0.40    # broader facets
HF_HUB_OFFLINE=1 uv run python -m cli.main facets --member-percentile 50     # more conservative nearest-facet assignment
```

Parameters are in `config/facets.yaml`. Rerun `facets` every time a chat is added or redone, then rerun `export`.

## Obsidian vault

```bash
HF_HUB_OFFLINE=1 uv run python -m cli.main export                          # by facets (latest facets result) -> vault/
HF_HUB_OFFLINE=1 uv run python -m cli.main export --facets-dir data/facets/<hash>
HF_HUB_OFFLINE=1 uv run python -m cli.main export --by topics              # by topics, without facets
```

- In Obsidian: *Open folder as vault* and pick `vault/`. After a new export the notes update by themselves.
- Every export only rewrites the generated folders (`chats/`, `facets/`, `notes/`, `concepts/`, `topics/`, `index.md`). Settings in `vault/.obsidian/` and notes written by hand are kept.
- Link and quote parameters: `config/vault.yaml`.
- The vault contains chat text and names: it is ignored by git.

## Search

```bash
# indexes one export; --reset empties the index first
HF_HUB_OFFLINE=1 uv run python -m cli.main ingest data/exports/datamining.json --course "Data Mining" --reset

HF_HUB_OFFLINE=1 uv run python -m cli.main search "how is the exam?" --k 5 --course "Data Mining"
```

`ingest` takes one file at a time: run it once per export, with `--reset` only the first time.

## Tests

```bash
uv run pytest            # all tests
uv run pytest -k reply   # only tests with "reply" in the name
```
