# tests/test_topics.py

Test di `core/window_embeddings.py` e `core/topics.py`.

- `window_text`: solo i corpi dei messaggi della finestra, senza autori, righe vuote e messaggi di overlap.
- Embedding salvati e ricaricati; `is_current` è falso se cambia il modello o l'elenco delle finestre.
- `guess_language` su una frase italiana e una inglese.
- `center_by_language`: due argomenti in due lingue, con un vettore "lingua" aggiunto alle versioni italiane. Dopo la centratura, lo stesso argomento nelle due lingue ha coseno > 0.99 e i vettori hanno norma 1.
- Parametri: override, rifiuto delle chiavi sconosciute. L'hash cambia se cambia la lista di parole escluse, ma non se cambia solo il loro ordine.
- Parole escluse: unione della lista di scikit-learn e del YAML, in minuscolo.
- `summarize` con un modello finto e `topics_markdown`: dimensioni, parole chiave, outlier in fondo, risultato serializzabile in JSON.
- `fit_topics` vero (UMAP + HDBSCAN + BERTopic) su tre gruppi sintetici ben separati: trova 3 argomenti, e ogni gruppo cade per almeno 20 finestre su 25 nello stesso argomento. È il test più lento, perché `numba` compila UMAP al primo uso.
- `center_by_language` lascia invariata una lingua con troppe poche finestre: una finestra italiana isolata non diventa un vettore nullo.
