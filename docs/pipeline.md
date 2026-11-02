# Pipeline

Cribrum works on chat exports (JSON files in `data/exports/`, never modified). The logic is in `core/`; `cli/` is only the command line interface. There are two independent paths, both starting from the raw exports.

## 1. From chats to the Obsidian vault

```text
export JSON -> ingest/telegram (ChatMessage) -> windows -> embed -> discover -> facets -> export
               data/windows/  data/embeddings/  data/topics/  data/facets/  vault/
```

### Conversation windows (`core/windows.py`)

A **window** is a piece of conversation from a single chat. Embeddings, topics, facets and vault notes are all computed on windows, not on single messages.

Messages are scanned in time order. For each one, the rules below are tried in order, and the first that fires links it to an earlier message:

| rule | when | default |
|---|---|---|
| `reply` | it replies to a message within some time | 6 h |
| `burst` | same author as the previous message, shortly after | 120 s |
| `dependent` | a short acknowledgement ("ok", "thanks", "+1") | 300 s |
| `mention` | it mentions a user who wrote recently | 30 min |
| `gap` or `model` | the previous message is within a time threshold, or the merge model says "same conversation" | 600 s for course chats, 900 s for general ones |

If no rule fires, a new window starts.

- Each message gets **one link only**, with no union-find. Otherwise a reply to an old conversation plus closeness in time to another one would glue two different conversations together.
- Windows are capped at 40 messages or 512 tokens (the limit of the embedding model). Past the cap, the window is closed and a continuation starts.
- Service messages and blocklisted accounts (bots) are excluded.
- Windows refer to messages by their stable ids `(chat_id, id)`, so they can always be regenerated.

### Merge model (`core/merge_features.py`, `core/merge_model.py`, `core/merge_decider.py`)

The time-gap rule is wrong about one pair in three. Even at 10 to 20 minutes apart, a third of the pairs start a new topic, and past 40 minutes half of them are still the same conversation. There is no clean cut-off.

So the `gap` rule can be replaced by a decision tree trained on labelled pairs. The labels are collected with `annotate` (human) and `labels` (an assistant, used only for training). The tree looks at 17 features: the gap (as a log, and relative to the median gap of the chat), same author, whether the author was active in the last messages, questions, openers ("hi, does anyone know..."), thanks, lengths, media, replies, TF-IDF similarity with the previous message and with the last five, and the chat type.

Evaluation is leave-one-chat-out on human labels only, with balanced accuracy because "merge" is the majority class. The tree reaches 0.89, against 0.69 for the gap rule. The first splits are: is it a question, was the author already in the conversation, does it share words with the previous message. That is the same reasoning I use when labelling by hand.

### Window embeddings (`core/window_embeddings.py`)

One `intfloat/multilingual-e5-base` vector per window, computed on the window text without author names. Vectors are cached and only recomputed when the windows change.

### Topics per chat (`core/topics.py`)

BERTopic on the window embeddings: UMAP, then HDBSCAN (`leaf` cluster selection, which gives more specific topics), then c-TF-IDF for keywords. Two details matter:

- `language="multilingual"` is required. With the English default, BERTopic strips non-ASCII characters before extracting keywords, and Italian words get cut ("perché" becomes "perch").
- **Language centering.** Multilingual embeddings also encode the language, so the same theme in Italian and English came out as two topics. Each vector has the mean vector of its language subtracted (language estimated from very frequent words), and is renormalised. Languages with fewer than 10 windows are left as they are.

About a third of the windows stay outliers, mostly isolated questions.

### Facets across chats (`core/facets.py`)

1. All windows of all chats are centered by language **together**, so the spaces of different chats are comparable.
2. Topics (not windows) are clustered with average-linkage agglomerative clustering on cosine distance. Two groups are merged when their mean similarity is at least `merge_similarity` (0.45). The number of facets comes out of this.
3. A facet is `shared` if its topics come from at least 2 chats, otherwise it is a `local` concept of one chat.
4. Names are the c-TF-IDF keywords **between facets**: words frequent in the facet and rare in the others.
5. A window inside a topic takes the facet of its topic. An outlier window joins the nearest facet among those its chat already has, if it is at least as close as the 25th percentile of that facet's members. The threshold is derived from the data, and is different for every facet.

On 9 chats, this gives 93 facets (37 shared) and puts 74% of the windows in a facet, against 60% with a topic.

### Vault (`core/vault.py`, `core/facet_vault.py`)

```text
index.md                          chats and shared facets
chats/<chat>.md                   shared facets of the chat and its own concepts
facets/<keywords>.md              shared facet: the node that connects chats
notes/<chat>/<chat> · <facet>.md  the windows of one chat about that facet, quoted
concepts/<chat>/...               local concepts
```

In the graph: chat -> (chat, facet) note -> facet -> (other chat, facet) note -> other chat. Windows that joined a facet by proximity are marked. Every export only rewrites the generated folders.

## 2. Semantic search

```text
export JSON -> ingest/telegram (Message) -> chunking (Q&A threads) -> embeddings (E5) -> ChromaDB -> search
```

- `ingest` reads an export, builds question/answer threads from explicit replies and adjacent messages (`core/chunking.py`), embeds them and stores them in ChromaDB (`data/chroma_db/`).
- `search` returns the messages and threads closest in meaning to a question, and flags questions that never got an answer.

## Why every step writes to disk

Each step reads one file and writes another, instead of doing everything in one pass:

1. **Look before going on.** Windows can be read and tuned (`windows.md`, `sample.md`) before computing embeddings on them.
2. **Redo only what changes.** New thresholds mean new windows and embeddings; a new embedding model keeps the windows; new facet parameters touch neither.
3. **Know where every result comes from.** Each output folder is named after the hash of its configuration and has a `meta.json` with the parameters, so two configurations can be compared side by side.
4. **Resume after a failure.** If a step stops, only that step is rerun: its inputs are already on disk.
