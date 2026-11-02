# config/windows.yaml

Parametri della costruzione delle finestre. Tempi in **secondi**. Ogni valore influisce su `config_hash` (tranne `inspect`), quindi ogni configurazione scrive in una cartella diversa e due configurazioni si confrontano direttamente.

## Come sono stati scelti i default
Gap fra messaggi consecutivi (solo messaggi non di servizio), misurati sugli export:

| chat | p50 | p75 | p90 | p95 |
|---|---|---|---|---|
| datamining (corso) | 199 s | 68 min | 22 h | 3 gg |
| anndl (corso) | 85 s | 11 min | 80 min | 5.3 h |
| t2i (generale) | 337 s | 98 min | 24 h | 3.1 gg |

Stesso autore consecutivo: p75 47–74 s, p90 129–395 s. Distanza dei reply: p50 5–14 min, p75 0.5–1.6 h, p90 2.5–15 h.

La coda (p90–p95) mescola conversazioni diverse a ore o giorni di distanza, quindi i default stanno nell'ordine dei minuti, fra p50 e p75 dei gap. Per tararli conviene confrontare `sample.md` di due configurazioni.

## Parametri
- **Intervallo di date** (in `config.yaml`, sezione `dates`, non in questo file perché vale per tutto il progetto): `min_date` (inclusa) e `max_date` (esclusa), in formato ISO (`"2023-01-01"`); `null` = nessun limite. I messaggi fuori intervallo non entrano nelle finestre e vengono contati come `out_of_date_range`. L'intervallo entra nell'hash. Dalla CLI: `--min-date` / `--max-date`. Default attuale: dal 2023-01-01, per ridurre il volume e restare su corsi e regole recenti.
- `tokenizer_model`: modello il cui tokenizer conta i token. Deve essere lo stesso di `embedding.model_name` in `config.yaml`, altrimenti il tetto non corrisponde a ciò che vedrà il modello.
- `default_chat_type`: tipo per le chat non elencate (`course` o `general`).
- `chat_types`: mappa `chat_id → tipo`. Il `chat_id` è il campo `id` in cima all'export, ed è stampato dal comando `windows`. `--chat-type` lo sovrascrive per un'esecuzione.
- `gap.course` = 600 (10 min), `gap.general` = 900 (15 min): unione per vicinanza temporale, senza altri legami. Le chat generali sono più lente (p50 337 s contro 85–199 s), quindi la soglia è un po' più ampia. Alzarla se le conversazioni risultano spezzate, abbassarla se nella stessa finestra finiscono argomenti diversi.
- `reply_max_gap` = 21600 (6 h): oltre questa distanza un reply non unisce. È più permissivo del gap perché il reply è un collegamento esplicito, ma resta sotto il p90 dei reply, per non riattaccare risposte a discussioni di giorni prima.
- `burst_gap` = 120: raffiche dello stesso autore (≈ p80–p90 del gap fra messaggi dello stesso autore).
- `dependent_gap` = 300: aggancio dei messaggi "dipendenti" (`ok`, `grazie`) al precedente.
- `mention_gap` = 1800: una menzione aggancia all'ultimo messaggio dell'utente citato se entro 30 min.
- `max_messages` = 40, `max_tokens` = 512: tetto della finestra. 512 è la lunghezza massima di E5: oltre, l'embedding verrebbe troncato.
- `overlap` = 0: messaggi ripetuti come contesto dopo uno split da tetto (es. 2–3). Deve essere minore di `max_messages`.
- `short_max_messages` = 1, `short_min_tokens` = 8: soglie per il flag `is_short`. Le finestre corte non vengono scartate.
- `include.service` = false: join, migrazioni ecc. vengono contati ma non entrano nelle finestre. `include.media`/`poll`/`forwarded` = true: media senza testo, sondaggi e inoltrati fanno parte della conversazione (es. foto di un esercizio seguita da domande).
- `dependent_phrases`: frasi che sono quasi sempre risposte. Il confronto avviene sul testo normalizzato (minuscolo, senza punteggiatura tranne `+`, con o senza emoji) e deve coincidere con l'intero messaggio: `ok grazie mille` non corrisponde se non è nella lista. Aggiungere varianti leggendo i messaggi da una riga in `windows.md`.
- `mention_aliases`: `username → from_id` per le `@menzioni` che non si risolvono da sole (l'export non contiene gli username). Il `from_id` si trova nell'export (`"from_id": "user123..."`).
- `inspect.seed`, `inspect.sample_size`, `inspect.top_longest`: campione casuale riproducibile e numero di finestre più lunghe da elencare. Non entrano nell'hash. Il campione serve **solo per la verifica a occhio** delle soglie: leggere 20 finestre prese a caso (e non le prime del file, tutte dello stesso periodo, o le più lunghe, che sono casi estremi) dà un'idea rappresentativa di come la configurazione taglia le conversazioni. Non è un dato usato dalla pipeline e non influisce sulle finestre: `windows.md` le contiene sempre tutte. Il seed rende il campione ripetibile (stessa configurazione + stesso seed = stesse finestre), così si può tornare sulle stesse finestre dopo averle annotate; con una configurazione diversa le finestre cambiano e quindi cambia anche il campione.

## Modello delle unioni
La regola del gap (`gap.course`, `gap.general`) si può sostituire con un modello addestrato sulle etichette: `windows <chat> --merge-model data/models/merge_model.pkl`. Il modello non è una chiave di questo file. Si passa dalla CLI perché il suo id (l'hash del file) entra nell'hash delle finestre. Con il modello, le soglie del gap non vengono usate. Vedi `docs/it/code/cli/merge.md`.

## Come tarare le soglie
"Tarare" significa scegliere i valori di questo file leggendo le finestre che producono, invece di fissarli a priori. Il criterio è quello del workflow: le finestre devono essere leggibili e sensate a mano, non basta che il codice giri.

1. **Lancia con i default** su una chat di corso e una generale (es. `datamining` e `t2i`). Guarda le statistiche: % di finestre da un messaggio, unioni per regola, finestre chiuse dal tetto, menzioni non risolte.
2. **Leggi `sample.md`** (20 finestre) e dai a ciascuna un giudizio:
   - **ok**: una sola conversazione, completa;
   - **troppo unita**: dentro ci sono due argomenti o due conversazioni diverse;
   - **spezzata**: è chiaramente la continuazione di un'altra finestra (per controllare, cerca in `windows.md` la finestra precedente nel tempo).
3. **Risali alla causa.** Ogni messaggio mostra la regola che l'ha unito (`` `gap ← #123` ``), quindi si vede quale soglia intervenire:
   - finestre troppo unite per `gap` → abbassa `gap.course` / `gap.general`; per `reply` → abbassa `reply_max_gap`; per `burst` → abbassa `burst_gap`;
   - finestre spezzate → alza la soglia di gap del tipo di chat. Se il messaggio isolato è una risposta breve ("ok raga", "grazie mille!!") aggiungilo a `dependent_phrases`; se è una @menzione non risolta aggiungi l'alias in `mention_aliases`;
   - molte finestre chiuse dal tetto con conversazioni che continuano → valuta `overlap` 2–3.
4. **Rilancia con un override** (es. `--gap-course 300`). L'output va in una nuova cartella (nuovo hash), così puoi confrontare statistiche e campioni con la run precedente. Il campione cambia con la configurazione: per confrontare lo stesso periodo, cerca le stesse date nei due `windows.md`.
5. **Fissa i valori.** Quando la grande maggioranza delle finestre del campione è "ok" su entrambe le chat (indicativamente 16–17 su 20), scrivi i valori in questo file. Con un seed diverso (`--seed`) puoi fare un ultimo controllo su un campione nuovo.
