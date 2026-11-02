# Future work

What I want to improve, step by step, based on what I saw on the data. For each point there is the problem, the options from simplest to most complex, and how to tell whether an option helps. The general rule: no change is kept without a measurement that justifies it.

A longer version, in Italian, is in [it/miglioramenti.md](it/miglioramenti.md).

## 1. Labels and evaluation

This limits everything else. With about 100 human-labelled pairs, the uncertainty on accuracy is around ±6 points, so differences of 1 to 3 points are invisible.

- **More human labels.** The queue of 300 pairs already exists; finishing it brings the uncertainty to about ±3–4 points.
- **A clean test set.** The word lists in `config/merge_cues.yaml` were chosen while looking at the test pairs too. A second test set, never looked at, should be used only for final comparisons.
- **Bootstrap confidence intervals** in `merge evaluate`, to see right away whether two models are really different.
- **Active learning.** Let the model propose the pairs it is least sure about, kept separate from the random sample used for evaluation.
- **A second human annotator** on 50 pairs would give the real ceiling. Today it is estimated from the agreement between me and the assistant labels (91%).

## 2. Better windows: conversation disentanglement

The current algorithm can only link a message to the one right before it, or to the one it explicitly replies to. Two cases are not covered: someone picking up a conversation from a few messages back without replying, and two conversations interleaved in the same minutes, which is common right before an exam.

This is the *conversation disentanglement* problem:

- M. Elsner and E. Charniak. [You Talking to Me? A Corpus and Algorithm for Conversation Disentanglement](https://aclanthology.org/P08-1095/). ACL 2008. Pairwise classifier on chat features (time, speaker, mentions), followed by a greedy clustering step.
- J. K. Kummerfeld et al. [A Large-Scale Corpus for Conversation Disentanglement](https://aclanthology.org/P19-1374/). ACL 2019. Ubuntu IRC corpus where every message is annotated with the message it responds to.
- T. Yu and S. Joty. [Online Conversation Disentanglement with Pointer Networks](https://aclanthology.org/2020.emnlp-main.512/). EMNLP 2020. Each message points to its parent, end to end.

Options:

- **Link to a recent window, not only to the previous message.** Candidates are the windows still "open" (a message in the last T minutes) plus "new window". Features are computed against the window (similarity with its centroid, author already in it, someone in it replied to the author, time since its last message), and a model ranks the candidates. It needs a different annotation: "which of the last 10 messages does this one continue?", as in Kummerfeld et al. Measure: share of messages linked to the right parent.
- **Message graph and clustering.** Estimate a same-conversation probability for every pair of nearby messages, then find conversations as groups: connected components, correlation clustering, or Leiden. More robust to single wrong links, but no longer streaming.
- **Split long windows afterwards.** Windows closed by the cap often contain several topics. A TextTiling-style segmenter on the message embeddings can cut where similarity drops.
- **Stronger pair models.** A small multilingual cross-encoder, pre-trained on weak labels (explicit replies are "same", messages on different days are "different") and fine-tuned on the real ones. Or a local LLM only for uncertain pairs. Calibrated probabilities instead of yes/no.
- **Metrics on whole conversations**: variation of information, one-to-one overlap, exact conversation F1. They need 5 to 10 stretches of chat (about 100 messages each) annotated in full.

## 3. Better search

The search path is the oldest part of the project and works on single messages and reply threads.

- Search over **conversation windows**, which carry more context than single messages.
- **Hybrid search**: BM25 next to the embeddings, merged with reciprocal rank fusion, and a cross-encoder to rerank the top results.
- A **local LLM** on top (for example through Ollama) that answers using only the retrieved windows and cites them. The decision "answer found / unanswered question / nothing relevant" stays with retrieval, so the model cannot make things up.
- Recognise **courses and professors** in the query, to filter or boost results.
- An interactive mode (REPL) and, later, a small GUI on top of the same `core/` functions.

## 4. Window embeddings

- Variants of the window text: weight the first message more (often the question), drop short acknowledgements, average per-message embeddings.
- Other offline models: `multilingual-e5-large`, `bge-m3`, instruction-tuned models.
- A real language detector instead of word counts, or removing the language direction linearly instead of subtracting means.

Measure: topic quality (section 5) with the same BERTopic configuration.

## 5. Topics

A third of the windows stay outliers.

- BERTopic `reduce_outliers`, or a lower `min_samples`, measured.
- Better keywords with `KeyBERTInspired` or `MaximalMarginalRelevance`.
- Readable names from a local LLM, kept next to the keywords and not instead of them.
- Hierarchical topics for the large chats.
- A `topics compare` command: number of topics, outlier share, keyword coherence (NPMI), diversity, silhouette, and stability across UMAP seeds.

## 6. Facets

- **Freeze the taxonomy.** Save facet prototypes, assign new chats to them, and let only the topics far from all of them form new facets. Match facets across runs with the Hungarian algorithm on similarity. This gives stable ids and an incremental vault.
- Hierarchical facets (two cut thresholds), multi-label assignment, automatic detection of noisy facets.
- Other clustering methods to compare: HDBSCAN on topic centroids, Leiden on the topic kNN graph, a single global BERTopic.
- A small labelled set of windows with their correct facet, to choose thresholds by precision and recall instead of by eye.

## 7. Entities and vault

- Professors and courses as nodes, from a semi-automatic dictionary plus offline NER.
- Mutual-neighbour links, community detection on the facet graph, timelines per facet (grades in February and July), short generated summaries marked as such.

## 8. Comparing options

Every step already writes to a folder named after its configuration hash, so configurations live side by side. What is missing:

- `windows compare`, `topics compare`, `facets compare` commands, like `merge compare`;
- parameter sweep scripts, like `scripts/tune_windows.py`;
- a single `eval` command over all labelled sets;
- an experiment log (`data/experiments.jsonl`) with date, step, hash, parameters and metrics.

## 9. More sources and media

WhatsApp and Discord adapters in `core/ingest/`, producing the same `ChatMessage` objects as the Telegram one.

Media content is not used today: a photo or a screenshot is a message of kind `media` with no text. Offline OCR (for example Tesseract) on screenshots and photos of exercises, and offline speech-to-text (for example Whisper) on voice messages, would turn them into text for windows, topics and search. It needs the media in the export, which today are not required.

## Priorities

| # | what | impact | cost |
|---|---|---|---|
| 1 | More human labels and confidence intervals | high: makes the rest measurable | low |
| 2 | Link to a recent window, with the new annotation mode | high: fixes interleaved conversations | medium |
| 3 | `topics compare` / `facets compare` | medium-high | medium |
| 4 | Frozen facets with stable ids | medium | medium |
| 5 | Window search with a local LLM | medium-high | medium |
| 6 | Professors and courses as nodes | medium | medium |
| 7 | Message graph clustering, cross-encoder | potentially high, after 1 and 2 | high |
