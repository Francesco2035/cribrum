# Cosa si può migliorare

Elenco ragionato di miglioramenti possibili, fase per fase, nate da quello che si è visto sui dati (9 chat, ~42k messaggi). Per ogni punto c'è:
- **il problema** osservato;
- **le opzioni**, dalla più semplice alla più complessa;
- **come misurare** se l'opzione aiuta.

In fondo una tabella di priorità.

Regola generale, valida per tutto: **nessuna modifica va tenuta senza una misura che la giustifichi**. Molte delle opzioni sotto servono proprio ad avere più modi di confrontare.

---

## 1. Fondamenta: etichette e valutazione

È la cosa che limita di più tutto il resto. Oggi abbiamo 103 coppie etichettate a mano. Con 100 coppie l'incertezza sull'accuratezza è di circa ±6 punti, quindi differenze di 1–3 punti non si vedono.

| problema | opzione | costo |
|---|---|---|
| Test set piccolo | Portare le etichette umane a 300 (la coda esiste già): l'incertezza scende a ±3–4 punti | basso, solo tempo |
| Test "contaminato" | Le liste di `config/merge_cues.yaml` sono state scelte guardando anche le coppie di test. Serve un **secondo test set** mai guardato, da usare solo per i confronti finali | basso |
| Etichette casuali poco informative | **Active learning**: il modello propone le coppie su cui è più incerto (probabilità vicina a 0.5). Un campo `source: uncertain` nel file le tiene separate dal campione casuale, che resta l'unico usato per misurare | medio |
| Numeri senza incertezza | In `merge evaluate`, un **intervallo di confidenza bootstrap** per ogni accuratezza (ricampionando le coppie 1000 volte). Si vede subito se due modelli sono davvero diversi | basso |
| Accordo umano non misurato | Un secondo annotatore umano su 50 coppie dà il vero tetto massimo raggiungibile. Oggi lo stimiamo solo con l'accordo tra te e Claude, al 91% | basso |

---

## 2. Concatenare meglio i thread (finestre)

**Il limite strutturale di oggi.** L'algoritmo può unire un messaggio solo al messaggio **subito prima**, oppure a quello a cui risponde con un reply esplicito. Due casi restano scoperti:
- una persona riprende una conversazione di qualche messaggio prima, senza reply (il caso `earlier`);
- due conversazioni si intrecciano nello stesso intervallo di tempo, come nelle sessioni di domande prima dell'esame.

Nella letteratura questo problema si chiama *conversation disentanglement*. I riferimenti classici sono Elsner & Charniak (2008) e Kummerfeld et al. (2019), con il dataset di IRC di Ubuntu.

### 2.1 Agganciare a una finestra recente, non solo al messaggio precedente
Per ogni messaggio si considerano come **candidati** le finestre ancora "aperte", cioè con un messaggio negli ultimi T minuti (per esempio 60), più l'opzione "nuova finestra". Un modello dà un punteggio a ogni candidato e si sceglie il migliore.

- **Feature per candidato.** Quasi tutte esistono già, ma vanno calcolate rispetto alla finestra invece che al messaggio precedente:
  - similarità TF-IDF ed embedding con il centroide della finestra;
  - l'autore partecipa già alla finestra;
  - qualcuno nella finestra ha risposto all'autore;
  - tempo dall'ultimo messaggio della finestra;
  - numero di messaggi in mezzo.
- **Modello.** Lo stesso albero, oppure una regressione logistica, addestrato come *ranking*: il candidato giusto deve avere un punteggio più alto degli altri.
- **Etichette necessarie.** Non più "stessa / nuova" ma "**a quale messaggio si collega**". Serve una variante di `annotate` che mostra gli ultimi 10 messaggi numerati e chiede di indicare il numero (oppure 0 = nuovo). È lo schema di annotazione di Kummerfeld, ed è più veloce di quanto sembri: ogni etichetta dà già la risposta corretta su tutti i candidati.
- **Misura.** Accuratezza del collegamento: la percentuale di messaggi agganciati al genitore giusto. Si confronta con l'algoritmo attuale sugli stessi messaggi.

### 2.2 Grafo dei messaggi + clustering, invece dell'unione greedy
Invece di decidere un messaggio alla volta, si stima una probabilità di "stessa conversazione" per **ogni coppia di messaggi vicini** (per esempio entro 20 messaggi). Poi si cercano le conversazioni come gruppi in quel grafo:
- **componenti connesse** con soglia sulla probabilità: semplice, ma un arco sbagliato unisce due conversazioni;
- **correlation clustering**: minimizza il disaccordo con tutte le probabilità insieme, ed è più robusto. Esistono algoritmi approssimati semplici, per esempio pivot;
- **Leiden** o **Louvain** sul grafo pesato, con `networkx` o `igraph`.

Il vantaggio: corregge gli errori locali usando il contesto. Il costo: è più complesso, e le finestre non sono più costruibili in streaming.

### 2.3 Spezzare a posteriori le finestre lunghe
Le finestre chiuse dal tetto (`hit_cap`), o molto lunghe, spesso contengono più argomenti, come le sessioni d'esame di anndl. Si può applicare un **segmentatore di testo** sulla sequenza di embedding dei messaggi: si taglia dove la similarità tra i blocchi a sinistra e a destra di un punto ha un minimo locale. È l'idea di TextTiling, applicata agli embedding.

**Misura:** coerenza interna delle finestre (similarità media dei messaggi con il centroide della finestra), prima e dopo.

### 2.4 Modelli più forti per la decisione sulla coppia
- **Cross-encoder** piccolo e multilingue (per esempio un MiniLM multilingue), riaddestrato sulle coppie. Legge i due messaggi **insieme** e capisce meglio i cambi di argomento senza punto di domanda, cioè gli errori che restano oggi. Con poche etichette conviene pre-addestrarlo su **etichette deboli**:
  - reply espliciti = stessa conversazione;
  - messaggi di giorni diversi = conversazioni diverse.

  Poi si rifinisce sulle etichette vere.
- **LLM locale** tramite Ollama (da aggiungere alle dipendenze), **solo per le coppie incerte** (probabilità tra 0.35 e 0.65): si chiede "il secondo messaggio continua il primo?". È lento, quindi va usato solo su una piccola frazione. Va misurato sulle stesse coppie di test.
- **Probabilità calibrate** invece di sì/no (`CalibratedClassifierCV`). Servono sia a 2.2 sia per scegliere una soglia diversa per tipo di chat.

### 2.5 Metriche per finestre intere, non solo per coppie
L'accuratezza sulle coppie non dice quanto sono buone le finestre nel complesso. Le metriche standard del disentanglement sono:
- **VI** (variation of information) tra le finestre prodotte e quelle corrette;
- **one-to-one overlap**;
- **F1 esatto delle conversazioni**: la percentuale di conversazioni ricostruite in modo identico.

Servono **5–10 tratti di chat annotati per intero** (circa 100 messaggi ciascuno, con la conversazione a cui appartiene ogni messaggio). È un investimento di qualche ora, ma permette di confrontare qualunque algoritmo di finestre, anche completamente diverso.

---

## 3. Embedding delle finestre

| problema | opzione | come misurare |
|---|---|---|
| Il testo della finestra è una semplice concatenazione | Varianti: **pesare di più il primo messaggio** (spesso è la domanda); togliere i messaggi corti ("ok", "grazie"); embedding per messaggio e poi media, invece di un embedding unico della concatenazione | qualità degli argomenti (sezione 4) con la stessa configurazione di BERTopic |
| Modello unico | Provare altri modelli offline: `multilingual-e5-large`, `bge-m3`, `multilingual-e5-large-instruct` (che accetta un'istruzione, per esempio "raggruppa per argomento") | idem, più il tempo di calcolo |
| Correzione della lingua approssimativa | (a) un **rilevatore di lingua** vero e offline (per esempio `lingua-py`) al posto del conteggio di parole; (b) **proiettare via** la direzione della lingua: si stima la direzione "italiano − inglese" e la si rimuove con un metodo lineare (per esempio LEACE), invece di sottrarre solo le medie; (c) tradurre tutto in una lingua con un traduttore locale, che è costoso | % di argomenti con parole chiave di una sola lingua; numero di coppie di argomenti "doppi" per lingua |
| Finestre più lunghe di 512 token | Spezzare in parti e fare la media | rilevante solo se si aumenta il tetto delle finestre |

---

## 4. Argomenti (BERTopic)

**Problema principale: il 32–47% delle finestre resta outlier.**

| opzione | dettaglio |
|---|---|
| `reduce_outliers` di BERTopic | Assegna gli outlier all'argomento più vicino con varie strategie (embedding, c-TF-IDF, distribuzioni). In pratica è simile al recupero per vicinanza dei facet, ma fatto a livello di argomento |
| `min_samples` più basso | Meno outlier, ma argomenti più "sporchi": va misurato |
| Parole chiave migliori | Rappresentazioni `KeyBERTInspired` o `MaximalMarginalRelevance` di BERTopic: parole più descrittive e meno ripetute ("grade, grades, exam") |
| Nomi leggibili | Un LLM locale (Ollama) che legge le parole chiave e 3 finestre di esempio e propone un nome di 2–4 parole. Da tenere come **campo in più** accanto alle parole chiave, non come sostituto, così resta verificabile |
| Argomenti gerarchici | `hierarchical_topics` di BERTopic: un albero di argomenti, utile per navigare le chat grandi (anndl ha 51 argomenti, CSGeneral 57) |

### Come confrontare le configurazioni (oggi manca)
Un comando `topics compare` che lancia più configurazioni e produce una tabella con:
- **numero di argomenti** e **% di outlier**;
- **coerenza** delle parole chiave, cioè quanto le parole di un argomento compaiono insieme nelle finestre (NPMI, calcolabile sulle finestre stesse);
- **diversità**: la percentuale di parole chiave uniche tra argomenti; se è bassa gli argomenti si ripetono;
- **separazione**: la silhouette sugli embedding;
- **stabilità**: l'accordo (ARI) tra due esecuzioni con semi diversi di UMAP. Se cambia molto, gli argomenti non sono affidabili.

Nessuna di queste sostituisce la lettura, ma permette di scartare subito le configurazioni cattive e di leggere solo le 2–3 migliori.

---

## 5. Facet

| problema | opzione |
|---|---|
| Id e nomi cambiano quando si aggiunge una chat | **Congelare** la tassonomia: si salvano i prototipi, e una chat nuova viene assegnata a quelli. Solo gli argomenti che restano lontani da tutti formano facet nuovi. Per riconoscere lo stesso facet tra due esecuzioni si accoppiano i prototipi con l'**algoritmo ungherese** (`scipy.optimize.linear_sum_assignment`) sulla similarità |
| Una sola granularità | **Facet gerarchici**: lo stesso clustering agglomerativo, tagliato a due soglie (per esempio 0.35 per i macro-temi e 0.45 per i facet). In Obsidian i macro-temi diventano note che raccolgono più facet |
| Facet generici ("niente, ti, così") | **Rilevazione automatica del rumore**: un facet presente in quasi tutte le chat **e** con parole chiave poco specifiche (punteggio c-TF-IDF basso, molte parole della lista di esclusione) è probabilmente rumore. Va marcato come tale, non cancellato. Il segnale è già citato nel documento di workflow |
| Una finestra può riguardare più temi | **Multi-etichetta**: si assegnano tutti i facet sopra soglia, non solo il più vicino |
| Raggruppamento con un solo metodo | Alternative da confrontare: HDBSCAN sui centroidi degli argomenti; **Leiden** sul grafo dei k vicini tra argomenti; clustering direttamente sulle finestre di tutte le chat insieme (BERTopic globale, senza passare dagli argomenti per chat) |
| Soglie scelte guardando i dati | Un piccolo **set etichettato di finestre** (100–150, con il facet corretto o "nessuno") permette di misurare precisione e recall dell'assegnazione e di scegliere `member_percentile` con un numero invece che a occhio. È il punto 8 del documento di workflow |

### Come confrontare
Un comando `facets compare` con la stessa idea di `topics compare`:
- numero di facet, condivisi e locali;
- dimensione del facet più grande rispetto alla mediana, che segnala i blob;
- % di finestre con un facet;
- e, quando esisterà il set etichettato, precisione e recall.

---

## 6. Entità: professori e corsi

Oggi i professori compaiono solo come parole chiave ("matteucci, boracchi, bonarini" è diventato un facet). Opzioni:
1. **Dizionario semi-automatico.** Si estraggono le parole con l'iniziale maiuscola frequenti in più chat, si filtrano quelle che non sono parole comuni, e si propone un elenco da confermare. Il file sarebbe `data/taxonomy/entities.yaml`, con varianti e soprannomi, come previsto dal documento di workflow.
2. **NER offline** con modelli spaCy italiano e inglese, per trovare i nomi di persona. Va unito al dizionario, perché i soprannomi non li trova.
3. Nel vault, i **professori come nodi** collegati alle note (chat, facet) che li citano. Si vede subito chi viene nominato in quali corsi e su quali temi.

---

## 7. Vault e grafo

| opzione | a cosa serve |
|---|---|
| Archi solo tra **vicini reciproci** | Grafo più pulito: A collega B solo se anche B ha A tra i suoi più simili |
| **Community detection** (Leiden) sul grafo dei facet | Raggruppamenti emergenti tra facet, da mostrare come note indice |
| Proprietà più ricche nel frontmatter | Con il plugin Dataview: tabelle per periodo, per numero di finestre, per chat |
| **Timeline** per facet | Le finestre per mese: si vede quando un tema è caldo, per esempio i voti a febbraio e luglio |
| Riassunti | Un LLM locale che riassume ogni nota (chat, facet) in 3–5 punti, in testa alla nota e marcato come generato |
| Vault di confronto | `export --vault vault-B` con un'altra configurazione: si aprono due vault in Obsidian e si confrontano i grafi |

---

## 8. Infrastruttura per confrontare le opzioni

Ogni passo salva già i suoi risultati in una cartella con l'hash della configurazione, quindi configurazioni diverse convivono. Quello che manca è un modo comodo di **confrontarle**:

1. **Comandi `compare` per ogni fase**, come `merge compare`:
   - `windows compare` (configurazioni di finestre affiancate);
   - `topics compare`;
   - `facets compare`.

   Ognuno dà una tabella e, se richiesto, un report markdown.
2. **Script di sweep** (`scripts/sweep_topics.py`, `scripts/sweep_facets.py`), come `scripts/tune_windows.py`: provano una griglia di parametri e scrivono un report con le metriche, per scegliere quali configurazioni leggere a mano.
3. **Comando `eval` unico** (previsto dal documento di workflow) che lancia tutte le misure disponibili sui set etichettati: coppie, finestre intere, facet. Stampa una riga per fase, così una modifica a monte (per esempio le finestre) si vede anche a valle (argomenti e facet).
4. **Registro degli esperimenti**: un file `data/experiments.jsonl` in cui ogni comando aggiunge una riga con data, fase, hash, parametri principali e metriche. Basta per rispondere a "quale configurazione aveva dato il risultato migliore?" senza un tool esterno.

---

## Priorità consigliata

| # | cosa | impatto | costo |
|---|---|---|---|
| 1 | Più etichette umane + intervallo di confidenza in `merge evaluate` | alto: rende misurabile tutto il resto | basso |
| 2 | Agganciare a una finestra recente (2.1), con la nuova modalità di annotazione | alto: risolve i casi `earlier` e le conversazioni intrecciate | medio |
| 3 | `topics compare` / `facets compare` con metriche automatiche | medio-alto: confronti veloci | medio |
| 4 | Congelamento dei facet con id stabili | medio: aggiornamenti senza rimescolare il vault | medio |
| 5 | Set etichettato di finestre → facet, per tarare le soglie | medio | basso-medio |
| 6 | Entità professori/corsi come nodi | medio: molto utile nel grafo | medio |
| 7 | Nomi e riassunti con LLM locale | medio: leggibilità | medio, e lento su CPU |
| 8 | Grafo dei messaggi + correlation clustering (2.2), cross-encoder (2.4) | potenzialmente alto, ma solo dopo 1–2 | alto |
