# tokens.py

## Librerie
- `transformers.AutoTokenizer` (già installata come dipendenza di sentence-transformers, quindi nessuna dipendenza nuova): carica **solo il tokenizer** del modello di embedding (`intfloat/multilingual-e5-base`), non i pesi. È leggero e veloce.

## Logica
`get_token_counter(model_name)` restituisce una funzione `count(text) -> int` e una descrizione del contatore usato, che finisce nelle statistiche. Contare con lo stesso tokenizer del modello significa che il tetto `max_tokens` corrisponde davvero a ciò che il modello vedrà (E5 tronca a 512 token).
Se il tokenizer non si può caricare offline, si ricade su una stima: parole × 1.3. Viene registrato un warning e la descrizione lo dichiara (`approx (words x 1.3)`).

## Costrutti
- `from_pretrained(..., local_files_only=True)`: legge solo dalla cache di Hugging Face e non scarica nulla.
- `encode(text, add_special_tokens=False)`: non conta `[CLS]`/`[SEP]` per ogni messaggio; la somma sui messaggi approssima così la lunghezza della finestra concatenata.
- `tokenizer.model_max_length = 10**9`: serve solo a zittire l'avviso "sequence longer than 512", che qui non ha senso perché il testo non viene passato al modello.
- Nota offline: `huggingface_hub` può fare una richiesta di rete indipendente dal tokenizer (rilevamento degli "agent harness", in cache per 24 h). Per garantire zero rete, lanciare i comandi con `HF_HUB_OFFLINE=1`.
