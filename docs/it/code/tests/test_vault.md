# tests/test_vault.py

Test di `core/vault.py` e della scelta dei risultati in `cli/vault.py`.

- Nomi: caratteri non ammessi rimossi; etichetta che salta le parole chiave già contenute ("grand coalition" dopo "coalition"); nomi duplicati resi unici con l'id.
- `link_similar`: al massimo `top_k` collegamenti, solo sopra soglia (un argomento ortogonale non viene collegato).
- `clean_text`: `#` e `[[ ]]` neutralizzati, testo su una riga e troncato.
- `render_window`: una citazione per messaggio, media senza testo come `_[media]_`, nessuna riga `>` vuota in fondo.
- Nota argomento e nota chat: frontmatter, tag, link reciproci, argomenti collegati, numero di outlier; limite di finestre mostrate (le più centrali, poi in ordine di data).
- `topic_windows`: ordine per vicinanza al centroide, outlier esclusi.
- `reset_generated` cancella solo `chats/`, `topics/` e `index.md`: le impostazioni `.obsidian/` e le note scritte a mano restano. `graph.json` viene scritto solo se non esiste.
- `load_vault_params` rifiuta le chiavi sconosciute; `latest_topics_dirs` (ora in `core/topic_results.py`) sceglie il risultato più recente di ogni chat.
