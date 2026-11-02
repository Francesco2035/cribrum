# ingest/telegram.py

## Librerie
- `json`: legge l'export (`result.json`).
- `re`: `SKIN_TONE_PATTERN` toglie i modificatori di carnagione dalle emoji.
- `datetime.fromisoformat`: converte `"2024-01-03T00:50:05"` in `datetime` (senza fuso, come nell'export).

## Logica
Ci sono due parser, con scopi diversi:
- `parse_telegram_export` (invariato): produce i `Message` per la ricerca e scarta i messaggi di servizio.
- `parse_telegram_chat` (nuovo): produce i `ChatMessage` per le finestre e **non scarta niente**. I messaggi di servizio restano, con `kind="service"` e `service_action` (`join_group_by_link`, `migrate_from_group`, ...); decidere se escluderli spetta alla configurazione delle finestre. Restituisce anche `chat_info` (`id`, `name`, `type` dall'intestazione dell'export).

Classificazione del `kind`: `service` se `type != "message"`; `poll` se c'è la chiave `poll` (il testo diventa la domanda del sondaggio); `media` se ci sono foto/file/sticker ecc. **e** nessun testo; altrimenti `text`. Una foto con didascalia resta quindi `text`.

## Costrutti
- `normalize_text`: nell'export `text` è una stringa oppure una lista che mescola stringhe e dizionari (`{"type": "link", "text": "..."}`). L'espressione `"".join(p if isinstance(p, str) else p.get("text", "") for p in text)` attraversa la lista e prende il testo di ogni pezzo. Se il risultato è vuoto si ricade su `_extract_text`, che usa `text_entities` e la mappa degli sticker (`👍` → `"sì"`).
- `_extract_mentions`: le entità `mention_name` contengono un `user_id` numerico, che corrisponde a `from_id` nella forma `"user<id>"`. Le `mention` semplici (`@nome`) hanno solo lo username, che l'export non collega mai a un utente: vengono salvate in minuscolo, senza `@`, e risolte più avanti (vedi `windows.md`).
- `sum(r.get("count", 0) for r in msg.get("reactions", []))`: totale delle reaction di tutte le emoji.
