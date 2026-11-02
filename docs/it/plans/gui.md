# gui/ — interfaccia grafica (fase successiva)

> Piano, non ancora implementato: la cartella `gui/` non esiste.

Da sviluppare **dopo** che la CLI funziona. Deve riusare esattamente le stesse
funzioni di `core/` usate dalla CLI: se la GUI ha bisogno di qualcosa che la CLI
non espone, va aggiunto in `core/`, non qui.

Nota: niente `__init__.py` qui, perché Streamlit esegue `app.py` come script
(`streamlit run gui/app.py`), non come package.

---

## `app.py`

**Scopo:** interfaccia web locale (Streamlit) per cercare nelle chat indicizzate e, su richiesta, generare una sintesi.

- Casella di ricerca + filtri laterali (chat, corso/professore, intervallo date, modalità "opinioni" / "esami", top-k).
- Lista risultati con estratto, metadati, punteggio e badge esplicito sull'esito (*risposta trovata* / *senza risposta* / *nessun risultato*); possibilità di espandere il contesto (messaggi prima/dopo).
- Pulsante "Sintetizza" che chiama `synth.py` solo sui risultati mostrati, con output in streaming.
- (opz.) Pagina di ingest: selezionare un `result.json` e lanciare l'indicizzazione con barra di avanzamento.
- Caricare modello e collection una sola volta con la cache di Streamlit, altrimenti vengono ricaricati a ogni interazione (Streamlit riesegue lo script da capo a ogni click).
- Streamlit gira su `localhost`: nessun dato esce dalla macchina. Disattivare la raccolta statistiche (`browser.gatherUsageStats = false` in `.streamlit/config.toml`).

**Input:** interazioni dell'utente nel browser.
**Output:** pagina web locale.

**Librerie:**
- `streamlit` — Doc: https://docs.streamlit.io/
  - Caching di risorse pesanti (modello, client Chroma): `st.cache_resource` → https://docs.streamlit.io/develop/concepts/architecture/caching
  - Output in streaming: `st.write_stream` → https://docs.streamlit.io/develop/api-reference/write-magic/st.write_stream
  - Config (telemetria): https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- Alternative se Streamlit dovesse stare stretto: `gradio` (https://www.gradio.app/docs) o `NiceGUI` (https://nicegui.io/documentation).

**Dipendenze:** `core/search.py`, `core/synth.py`, `core/courses.py`, `core/ingest/` (se c'è la pagina di ingest), `core/models.py`.
