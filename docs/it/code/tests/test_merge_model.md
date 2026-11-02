# tests/test_merge_model.py

Test delle feature, della tabella di addestramento e della valutazione, su chat costruite a mano (helper `msg` di `tests/test_windows.py`).

- `shrink`: testo vuoto → media della chat; testo lungo → coseno vera; in mezzo un valore intermedio.
- Feature di testo: domanda, apertura, autore diverso, TF-IDF alta con parole in comune. Senza vettori le feature di embedding sono `NaN`.
- Feature di embedding calcolate su vettori noti (coseno 1/√2 e 1).
- `needed_ids` comprende T e i 5 messaggi precedenti.
- `build_rows`: `unsure` escluso; per una coppia etichettata da entrambi vale l'etichetta umana; baseline della regola del gap.
- `leave_one_chat_out`: un modello finto registra su quali righe viene addestrato, e il test verifica che non veda mai la chat che deve predire.
- `message_vectors`: con un encoder finto (`monkeypatch`) controlla che i media non ricevano un vettore e che la seconda chiamata usi la cache senza ricalcolare.
- `decide_pairs`, con uno stimatore finto che risponde sempre 0 o sempre 1: sotto la soglia si unisce sempre, tra la soglia e `max_gap` decide il modello, sopra `max_gap` la coppia non viene decisa.
- `save_model` / `load_model`: andata e ritorno, metadati in `.json`, id che cambia con il contenuto, rifiuto delle feature di embedding.
- Integrazione con `build_windows`:
  - messaggi a 700 s di distanza restano separati con la regola del gap e vengono uniti dal modello finto, con la regola `model`;
  - l'hash cambia quando c'è un modello;
  - un id di modello senza decisore solleva un errore.
- Liste di parole:
  - `compile_cues` confronta sul testo normalizzato, quindi l'apostrofo viene tolto da entrambi i lati;
  - per parole intere ("no" non scatta su "nobody");
  - all'inizio, per le liste di inizio frase;
  - una lista vuota non scatta mai;
  - le feature seguono le liste passate e senza liste valgono 0.
- Densità e autore, su una chat costruita a mano: messaggi e autori negli ultimi 30 e 60 minuti, messaggi dello stesso autore, risposta ricevuta da un altro, P che è un reply all'autore di T; un messaggio isolato più tardi ha tutto a 0.
- `ablation_sets` e `parse_feature_groups`: insiemi dell'ablazione, `all`, `base`, una lista di gruppi (l'ordine segue i gruppi, non la stringa) e l'errore per un gruppo sconosciuto.
- `config/merge_cues.yaml` si carica con tutte e tre le liste piene; una chiave sconosciuta dà errore; un file mancante dà liste vuote.
- Il modello salvato conserva le liste di parole, anche nel `.json`.
