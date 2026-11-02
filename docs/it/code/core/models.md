# models.py

## Librerie
- `dataclasses`: `@dataclass` genera `__init__`, `__repr__` e `__eq__` dai campi annotati; `field(default_factory=list)` serve perché un default mutabile (`[]`) sarebbe condiviso fra tutte le istanze.
- `datetime`, `typing.Optional`: tipi dei campi.

## Logica
- `Message` (invariato) è l'unità dell'indice di ricerca. `is_synthetic` significa "chunk Q&A aggregato" e non va riusato.
- `ChatMessage` è un messaggio fedele all'export, usato solo per le finestre. Tiene ciò che `Message` scarta: `chat_id`, `from_id` (stabile, a differenza del nome visualizzato), `kind` (`text`/`media`/`poll`/`service`), flag inoltrato/modificato, numero di reaction, azione di servizio, menzioni. L'ID stabile è la coppia `(chat_id, id)`, esposta da `key`.
- `WindowLink` dice perché un messaggio è entrato nella finestra: regola (`reply`, `burst`, `dependent`, `mention`, `gap`, `cap`; `None` per il primo) e messaggio a cui si è legato. Con `rule="cap"`, `capped_rule` indica la regola che avrebbe unito il messaggio se il tetto non fosse stato raggiunto.
- `Window` contiene la lista ordinata degli ID dei messaggi (non il testo concatenato), i legami, i metadati e `config_hash`, che identifica i parametri che l'hanno generata. Il `window_id` (`<chat_id>-<id del primo messaggio>`) è derivato e cambia se cambiano i parametri.

## Costrutti
- `@property key`: si legge come un attributo (`m.key`) ma viene calcolato, quindi non va tenuto sincronizzato a mano.
