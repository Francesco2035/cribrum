# config/vault.yaml

Parametri di `export` (vault Obsidian).

| chiave | default | significato |
|---|---|---|
| `top_k` | 3 | quanti argomenti simili collega al massimo ogni nota |
| `min_similarity` | 0.4 | similarità minima (coseno tra centroidi) perché due argomenti siano collegati |
| `label_words` | 3 | parole chiave nel titolo della nota |
| `max_windows` | 40 | finestre citate al massimo per nota argomento, scelte tra le più centrali |
| `max_message_chars` | 500 | lunghezza massima di un messaggio citato |

## Come è stata scelta la soglia
Sulle prime tre chat (MAS, datamining, t2i: 38 argomenti) la similarità con il vicino più simile ha mediana 0.37 e 90° percentile 0.58. Le coppie sopra 0.4 sono quasi tutte sensate:
- opinioni sul corso MAS ↔ datamining, 0.66;
- domande d'esame MAS ↔ voti d'esame datamining, 0.63;
- lezioni e orari datamining ↔ t2i, 0.56;
- coalizioni ↔ equilibri di Nash in MAS, 0.51.

Sotto 0.4 compaiono collegamenti casuali, per esempio registrazioni ↔ voti. Con 0.4 escono 23 collegamenti, 12 dei quali tra chat diverse. Con più chat la distribuzione può cambiare: conviene ricontrollarla aggiungendo chat.
