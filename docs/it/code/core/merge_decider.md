# core/merge_decider.py

Salva e carica il modello delle unioni addestrato, e lo applica a una chat intera per sostituire la regola del gap in `build_windows`.

## Librerie
- `pickle` (libreria standard): serializza il modello. Si usa al posto di `joblib`, che è solo una dipendenza indiretta di scikit-learn. Va caricato solo un file creato da noi, perché `pickle` può eseguire codice.
- `hashlib`: id del modello, cioè l'hash del contenuto del file.
- `numpy`: matrice delle feature.

## Logica
- `MergeModel` contiene lo stimatore di scikit-learn e tutto quello che serve per applicarlo come in addestramento:
  - le feature, nell'ordine usato;
  - `always_merge_below` (default 120 s): sotto questo gap si unisce sempre e il modello non viene interpellato;
  - `max_gap` (3 h): sopra questo gap non c'è mai stata una coppia etichettata, quindi il modello non decide e si apre una finestra nuova, come faceva già la regola del gap;
  - i metadati dell'addestramento;
  - `cue_lists`: le liste di `config/merge_cues.yaml` al momento dell'addestramento. Così applicare il modello dà le stesse feature anche se nel frattempo il file è stato modificato.
- `save_model` scrive `merge_model.pkl` e accanto `merge_model.json` (id, feature, soglie, liste di parole, quante coppie per fonte, data). Le feature di embedding sono rifiutate: in `windows` servirebbero gli embedding di tutti i messaggi della chat, e l'ablazione ha mostrato che non aiutano.
- `model_id` è un hash del contenuto: entra nell'hash della configurazione delle finestre, così un modello riaddestrato produce una cartella nuova in `data/windows/` invece di sovrascrivere.
- `decide_pairs` decide tutte le coppie consecutive di una chat in un colpo solo, prima di costruire le finestre. È possibile perché le feature guardano solo i messaggi (gap, testo, autori, TF-IDF) e non le finestre già formate. Restituisce `{id del messaggio: unire con il precedente?}`.
- `decider_for` adatta il modello alla firma `MergeDecider` attesa da `build_windows`.

## Dove sta il modello
`data/models/` è in `.gitignore`: il modello si rigenera dalle etichette con `merge train`.
