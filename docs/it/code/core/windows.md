# windows.py

## Librerie
- `collections.Counter` / `defaultdict`: contatori per le statistiche e raggruppamento dei messaggi per chat.
- `unicodedata.category`: classifica i caratteri (`P*` = punteggiatura, `S*` = simboli/emoji). Serve a normalizzare i messaggi brevi senza scrivere a mano una regex di tutta la punteggiatura Unicode.
- `statistics.quantiles` e `itertools.pairwise`: percentili dei gap.

## Logica
`build_windows` raggruppa i messaggi per `chat_id` ed elabora ogni chat da sola, quindi chat diverse non finiscono mai nella stessa finestra. Per ogni chat:
1. **Filtro**: prima l'intervallo di date (`in_date_range`, con `min_date` inclusa e `max_date` esclusa, conteggio `out_of_date_range`), poi `exclusion_reason` toglie i messaggi degli account in blocklist (`blocked_ids`, motivo `blocked`) e decide cosa entra in base a `include` (di default i messaggi di servizio restano fuori). Gli esclusi vengono contati per motivo, mai scartati in silenzio.
2. **Scansione cronologica** (ordinamento per `(timestamp, id)`). Per ogni messaggio, `_find_link` prova le regole in ordine di priorità e si ferma alla prima che scatta:
   1. `reply`: il padre esiste ed è entro `reply_max_gap`. Un padre assente dall'export (`orphan_replies`), escluso dal filtro (`replies_to_excluded`) o troppo vecchio (`stale_replies`) viene contato, e il messaggio prosegue con le regole successive come se fosse normale.
   2. `burst`: il messaggio precedente ha lo stesso `from_id` ed è entro `burst_gap`.
   3. `dependent`: il testo normalizzato è nel dizionario ed è entro `dependent_gap` dal precedente. Poi `mention`: l'utente citato ha un messaggio entro `mention_gap` e il messaggio si lega a quello.
   4. `gap`: il precedente è entro la soglia del tipo di chat. Se invece è stato passato un modello delle unioni (`merge_decider`), al posto del gap c'è la regola `model`: si unisce al precedente se il modello lo dice (vedi sotto).
   Se nessuna regola scatta, si apre una finestra nuova.
3. **Un solo legame per messaggio**: il messaggio entra nella finestra del messaggio a cui si lega. Due finestre esistenti non vengono mai fuse, a differenza delle componenti connesse con union-find: lì un reply a una conversazione vecchia più la vicinanza temporale con un'altra le incollerebbe insieme. Le catene di reply restano comunque unite, per transitività. Di conseguenza una finestra può essere non contigua nel tempo (un reply a un messaggio di due ore prima rientra nella sua finestra).
4. **Tetto**: se la finestra di destinazione ha già `max_messages` messaggi o supererebbe `max_tokens`, viene chiusa (`hit_cap`) e se ne apre una continuazione; il messaggio vi entra con regola `cap`. I legami successivi verso la finestra chiusa vengono rediretti alla continuazione (`_current` segue la catena dei `successor`). Con `overlap > 0` gli ultimi N messaggi della finestra chiusa vengono ripetuti in `overlap_ids` della continuazione: servono solo come contesto e non contano come appartenenza. Un singolo messaggio più lungo di `max_tokens` forma comunque una finestra da solo.
5. **Finestre corte**: `is_short` se ci sono ≤ `short_max_messages` messaggi o meno di `short_min_tokens` token. Non vengono scartate né fuse.

## Risoluzione delle @menzioni
L'export contiene i nomi visualizzati, non gli username. `_username_resolver` prova prima `mention_aliases` dalla config, poi il confronto con i nomi visualizzati normalizzati (minuscolo, solo caratteri alfanumerici), accettato solo se il match è **univoco**. Le menzioni non risolte vengono contate.

## Costrutti
- `normalize_phrase`: `"".join(c for c in text if c == "+" or not unicodedata.category(c).startswith("P"))` tiene ogni carattere che non è punteggiatura, salvo il `+` (per `+1`). `" ".join(text.split())` comprime gli spazi multipli.
- `is_dependent` prova due varianti: con le emoji (per frasi come `👍`) e senza (così `grazie 🙏` corrisponde a `grazie`).
- `statistics.quantiles(gaps, n=100, method="inclusive")` restituisce i 99 punti di taglio p1…p99, quindi p50 è `cuts[49]`. `inclusive` tratta i dati come l'intera popolazione.
- `pairwise(messages)` produce le coppie consecutive `(m0, m1), (m1, m2), ...`.

## Modello delle unioni al posto del gap
`build_windows(..., merge_decider=...)` accetta una funzione `(messaggi inclusi della chat, tipo di chat) -> {id messaggio: unire?}` (tipo `MergeDecider`). Di solito è `decider_for(model)` di `core/merge_decider.py`.
- Le decisioni sono calcolate una volta per chat, prima della scansione, e consultate da `_find_link` all'ultimo passo, al posto della regola del gap. Le regole `reply`, `burst`, `dependent` e `mention` vengono prima e restano invariate.
- La regola compare come `model` nei legami e nelle statistiche (`RULES`).
- `params.merge_model` (l'id del modello) e `merge_decider` vanno passati insieme, altrimenti viene sollevato un `ValueError`. Così l'hash delle finestre indica sempre se e con quale modello sono state fatte.
