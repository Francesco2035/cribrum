# core/ingest/ — adattatori per le sorgenti di chat

Ogni file qui è un **adattatore**: legge l'export di una piattaforma e lo converte
nel formato comune (`Message` di `core/models.py`). Tutto ciò che viene dopo
(question detection, chunking, embedding…) non deve sapere da quale piattaforma
arrivano i messaggi.

Per aggiungere WhatsApp/Discord in futuro basterà creare `whatsapp.py` /
`discord.py` con la stessa "forma" di `telegram.py`.

---

## `__init__.py`

**Scopo:** esporre un punto d'ingresso unico per scegliere l'adattatore giusto.

- Definire (anche solo per convenzione, o con un `typing.Protocol`) l'interfaccia comune: "dato un percorso, restituisci i messaggi normalizzati".
- Tenere un piccolo registro `nome_sorgente → funzione/classe loader` (es. `"telegram" → telegram.load`), così script e CLI possono dire `load("telegram", path)` senza importare il modulo specifico.
- (opz.) Autodetect della sorgente guardando la struttura del file.

**Input/Output:** nome sorgente + percorso → lista di `Message`.

**Librerie:**
- `typing.Protocol` (stdlib) per descrivere l'interfaccia senza ereditarietà. Doc: https://docs.python.org/3/library/typing.html#typing.Protocol

**Dipendenze:** `core/models.py`, `core/ingest/telegram.py` (e futuri adattatori).

---

## `telegram.py`

**Scopo:** convertire l'export JSON di Telegram Desktop (`result.json`) in una lista di `Message` normalizzati.

- Leggere il file prodotto da *Telegram Desktop → Esporta cronologia chat → formato JSON (machine-readable)*. Può contenere una singola chat o, con l'export completo, `chats.list[]`: gestire entrambi i casi.
- Tenere solo i messaggi con `type == "message"` (scartare `service`: ingressi, pin, cambi titolo…).
- **Normalizzare il testo:** il campo `text` può essere una stringa **oppure** una lista mista di stringhe e oggetti `{type, text}` (link, grassetto, menzioni, hashtag…). Concatenare le parti testuali. In alternativa usare `text_entities`, che è sempre una lista.
- Estrarre: `id`, `date`/`date_unixtime` → timestamp, `from`/`from_id` → autore, `reply_to_message_id` → collegamento risposta (fondamentale per `question_detect.py`), `forwarded_from`, eventuali allegati (`photo`, `file`, `media_type`) solo come flag/descrizione (non li indicizziamo).
- Scartare o marcare messaggi vuoti (solo sticker/foto senza didascalia).
- (opz.) Anonimizzare gli autori (hash di `from_id`) se vuoi evitare di tenere nomi nel DB.

**Input:** percorso a un file `result.json` (in `data/raw/`).
**Output:** lista di `Message` (id, chat, autore, timestamp, testo normalizzato, `reply_to`, flag), ordinata per data.

**Librerie:**
- `json` (stdlib) — basta per export di dimensioni normali.
- `ijson` se l'export è enorme (centinaia di MB) e vuoi leggerlo in streaming senza caricarlo tutto in RAM. Doc: https://github.com/ICRAR/ijson
- `datetime` (stdlib): preferire `date_unixtime` (UTC, non ambiguo) a `date` (ora locale senza timezone).

**Riferimenti sul formato:**
- Telegram non pubblica uno schema ufficiale del JSON esportato: il modo più affidabile è aprire un `result.json` reale e guardarlo. Pagina ufficiale sull'export: https://telegram.org/blog/export-and-more
- Utile come riferimento sui tipi di entità di testo (bold, mention, text_link…): https://core.telegram.org/type/MessageEntity

**Dipendenze:** `core/models.py` (`Message`).
