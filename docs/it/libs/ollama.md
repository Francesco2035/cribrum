# ollama

**Ollama** è un programma che scarica ed esegue LLM in locale ed espone
un'API su `http://localhost:11434`. La libreria Python **`ollama`** è solo il
client che parla con quell'API. In Cribrum serve **solo** per la sintesi
opzionale (`core/synth.py`).

Doc client Python: https://github.com/ollama/ollama-python
Doc API REST: https://github.com/ollama/ollama/blob/main/docs/api.md
Modelli: https://ollama.com/library

## Installazione del server (Arch)

```bash
sudo pacman -S ollama
sudo systemctl start ollama        # oppure: ollama serve (in un terminale)
ollama pull qwen2.5:3b             # scarica un modello (~2 GB)
ollama run qwen2.5:3b "ciao"       # prova veloce
ollama list                        # modelli scaricati
```

Su CPU senza GPU conviene stare su modelli **1-4B quantizzati** (default Q4):
`qwen2.5:3b`, `llama3.2:3b`, `gemma3:4b`. Un 7-8B funziona, ma è lento.

## Uso dal client Python

```python
import ollama

client = ollama.Client(host="http://localhost:11434")

messages = [
    {"role": "system", "content": "Rispondi SOLO usando i messaggi forniti. "
                                  "Se l'informazione non c'è, scrivi 'Non trovato nei messaggi'. "
                                  "Cita gli id dei messaggi tra parentesi quadre."},
    {"role": "user", "content": f"Domanda: {query}\n\nMessaggi:\n{contesto}"},
]

# risposta intera
resp = client.chat(model="qwen2.5:3b", messages=messages,
                   options={"temperature": 0.1, "num_ctx": 4096})
print(resp["message"]["content"])

# streaming: i token arrivano man mano (su CPU lenta è molto meglio)
for chunk in client.chat(model="qwen2.5:3b", messages=messages, stream=True):
    print(chunk["message"]["content"], end="", flush=True)
```

## Opzioni utili (`options=`)

- `temperature`: bassa (0-0.2) per riassumere in modo fedele, senza inventare.
- `num_ctx`: dimensione del contesto in token. Il default può essere piccolo: se passi 10 chunk lunghi, parte del prompt viene **tagliata senza avvisi**. Più contesto significa anche più RAM e più lentezza.
- `num_predict`: tetto ai token generati.

`keep_alive` (parametro di `chat`) indica per quanto il modello resta in RAM
dopo la richiesta. Il default è qualche minuto: la seconda domanda è veloce, la
prima deve caricare il modello.

## Gestione errori

- Server spento → errore di connessione (`ConnectionError` / `httpx.ConnectError`, dipende dalla versione).
- Modello non scaricato → `ollama.ResponseError` con status 404.

Intercettali in `synth.py` e rilancia un'eccezione del progetto con un messaggio chiaro, ad esempio "Ollama non è attivo: `systemctl start ollama`".

## Trappole

- L'LLM **inventa** se glielo permetti: il prompt deve vietarlo esplicitamente, e se la ricerca ha già dato `not_found` è meglio non chiamarlo proprio.
- Modelli piccoli seguono male istruzioni lunghe: prompt brevi e diretti.
- È tutto locale, ma controlla che `OLLAMA_HOST` non punti a una macchina remota.
