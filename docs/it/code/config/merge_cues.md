# config/merge_cues.yaml

Liste di parole usate dalle feature testuali del modello delle unioni (`core/merge_features.py`). Si modifica a mano, come `config/blocklist.yaml`. Il percorso è in `config.yaml` → `paths.merge_cues`.

## Le liste
| lista | dove deve comparire | feature | cosa indica |
|---|---|---|---|
| `group_request` | in qualunque punto del messaggio | `cur_group_request` | il messaggio si rivolge al gruppo ("qualcuno", "anyone", "ragazzi"): di solito apre una domanda nuova |
| `answer_start` | all'inizio | `cur_answer_start` | il messaggio inizia come una risposta ("yes", "no", "i think", "credo", "boh") |
| `anaphora_start` | all'inizio | `cur_anaphora_start` | il messaggio inizia riferendosi a qualcosa già detto ("he", "lui", "quello") |

## Come si confrontano le parole
- Il testo del messaggio e le frasi della lista vengono **normalizzati** allo stesso modo (`normalize_phrase`): minuscolo, senza punteggiatura, spazi singoli. "C'è qualcuno?" diventa "cè qualcuno", quindi nella lista si può scrivere `c'è qualcuno` oppure `cè qualcuno`.
- Il confronto è per **parole intere**: `no` non scatta su "nobody".
- In YAML `yes` e `no` senza virgolette diventano `true`/`false`: vanno scritti tra virgolette (`"yes"`, `"no"`).
- Una chiave sconosciuta, per esempio un errore di battitura, dà errore. Una lista mancante o vuota non scatta mai.

## Come sono state scelte
Contando, nelle ~600 coppie etichettate, in quanti messaggi da separare e da unire compare ogni parola:
- `group_request`: nel 53% dei messaggi da separare, contro il 9% di quelli da unire.
- `answer_start`: 1 da separare contro 50 da unire.
- `anaphora_start`: 2 contro 16.

Parole **escluse** di proposito:
- `si`: in italiano è anche il pronome riflessivo ("si può fare?").
- `comunque`: compare solo in conversazioni che continuano.
- `same`, `also`, `ma`, `but`, `quindi`, `so`: compaiono in modo simile in entrambi i casi.
- I segnali di cambio argomento ("btw", "invece", "un'altra domanda"): sono rarissimi (meno dello 0,5% dei messaggi) e quando compaiono non indicano un cambio di argomento.

## Dopo una modifica
Rilanciare `merge evaluate` per vedere l'effetto, poi `merge train`. Le liste vengono **salvate dentro il modello**, così `windows --merge-model` usa sempre quelle con cui il modello è stato addestrato, anche se nel frattempo il file è cambiato.

Con l'ablazione attuale (`docs/it/code/cli/merge.md`) queste feature non migliorano il modello, quindi il modello di default (`merge train` senza `--features`) non le usa. Restano disponibili per quando ci saranno più etichette.
