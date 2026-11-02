# Cribrum: workflow del grafo stile Obsidian

Documento di riferimento per la costruzione del grafo dei messaggi dei gruppi Telegram. Descrive obiettivo, concetti, struttura dei dati, pipeline, organizzazione del codice, valutazione e ciclo di aggiornamento. Non contiene codice.

---

## 1. Obiettivo

Partendo dai JSON esportati da Telegram (per ora solo testo) ottenere un vault in stile Obsidian in cui:

- il rumore (messaggi generici, saluti, logistica banale) è rimosso;
- i messaggi sono organizzati in note per concetto, non per ordine cronologico;
- gruppi diversi si collegano tra loro tramite concetti condivisi (esempio: una nota "Modalità d'esame" del corso A e quella del corso B sono collegate allo stesso concetto);
- esiste un indice per professore e per corso;
- il sistema scala: aggiungere una chat o un dominio nuovo non obbliga a rifare tutto.

Vincoli: 100% offline, core logic separata dalle interfacce, gestione pacchetti con uv, CLI prima, GUI (eventualmente Streamlit) dopo.

---

## 2. Concetti chiave

**Finestra.** Unità di lavoro: un pezzo coerente di conversazione in una singola chat, ottenuto unendo messaggi per reply e vicinanza temporale, con un tetto di lunghezza. Non si mescolano mai chat diverse. Lunghezza variabile.

**Facet.** Concetto trasversale ai gruppi (esempi: modalità d'esame, domande uscite agli esami, opinioni sul professore, carico di lavoro, materiale e appunti, progetti e scadenze, logistica, consigli di studio). È dato, non modello: ha nome, descrizione, esempi e un prototipo (vettore).

**Entità.** Professori e corsi, riconosciuti tramite un dizionario curato a mano (con varianti e soprannomi).

**Nota.** Coppia (gruppo o corso, facet). Contiene le finestre assegnate, ordinate per data. È il nodo che porta il contenuto.

**Grafo.** Nodi: note, corsi, facet, professori. Archi: nota→corso, nota→facet, nota→professore, nota↔nota (similarità).

**Tassonomia congelata.** I facet si scoprono con BERTopic ma poi si salvano come dati stabili. L'assegnazione dei messaggi non dipende più da un fit di BERTopic.

---

## 3. Principi di progetto

1. Separare dati grezzi, derivati e output: i derivati devono essere rigenerabili senza rifare ingest ed embedding.
2. Tutto ciò che cambia spesso (soglie, tassonomia, dizionario entità) vive in file di configurazione o dati, non nel codice.
3. Stesso modello di embedding per tutte le chat, altrimenti i vettori non sono confrontabili.
4. Ogni fase ha input e output espliciti e salvati su disco, così si può ripartire da qualunque punto.
5. Nessun risultato è affidabile senza un piccolo set etichettato a mano su dati reali.
6. Esito esplicito "nessun facet" per rumore e novità, invece di forzare un'etichetta.

---

## 4. Struttura dei dati su disco

```
data/
  raw/                  JSON originali esportati (sola lettura)
  windows/              tabella finestre (chat, testo, date, autori, id messaggi)
  embeddings/           matrice vettori allineata alla tabella finestre + metadati modello
  topics/               risultati BERTopic per chat (topic, keyword, centroidi, membri)
  taxonomy/
    facets.*            nome, descrizione, esempi, prototipo per facet
    entities.*          dizionario professori e corsi con varianti
  assignments/          finestra -> facet(+punteggio), corso, entità
  eval/                 set etichettato a mano e risultati delle metriche
vault/                  output Obsidian (rigenerabile)
config/
  settings.*            soglie, parametri finestre, modello embedding, top-k archi
```

Regola: `raw`, `taxonomy`, `entities`, `eval` sono dati curati; `windows`, `embeddings`, `topics`, `assignments`, `vault` sono derivati.

---

## 5. Pipeline

### Parte A: costruzione della tassonomia (una tantum, supervisionata)

**A1. Ingest e finestre** (per ogni chat)
- Input: JSON Telegram.
- Logica: messaggi in ordine, unione per reply, apertura di una nuova finestra quando il gap temporale supera una soglia, tetto su messaggi o token, eventuale scarto di finestre troppo corte.
- Output: tabella finestre.
- Taratura: distribuzione dei gap per chat, soglia attorno a un percentile alto, lettura a mano di ~20 finestre.

**A2. Embedding**
- Input: tabella finestre.
- Output: matrice di vettori, salvata con nome e versione del modello.

**A3. BERTopic per chat**
- Input: testi e embedding già calcolati (non ricalcolarli).
- Output: per ogni chat topic con keyword, dimensione, centroide, membri.
- Attenzione: il topic outlier non coincide col rumore; i topic generici ("grazie", "link lezione") possono essere molto compatti.

**A4. Consolidamento tra chat**
- Input: centroidi di tutti i topic di tutte le chat.
- Logica: raggruppamento dei centroidi per similarità; ogni gruppo che attraversa più chat è un candidato facet.
- Output: lista di candidati con le chat coinvolte e messaggi d'esempio.
- Segnale utile: un candidato presente in quasi tutte le chat è probabilmente generico (rumore), non un facet.

**A5. Revisione a mano**
- Per ogni candidato: leggere 5-10 esempi, decidere tieni / unisci / scarta, assegnare un nome e una descrizione di una frase.
- Output: file della tassonomia, con prototipo per facet (centroide dei membri, embedding della descrizione, oppure media dei due).
- Opzionale: guided topic modeling con parole chiave seed se esistono già facet in mente.

### Parte B: pipeline a regime (automatica)

**B1. Assegnazione dei facet**
- Per ogni finestra: similarità coseno con tutti i prototipi; facet col punteggio massimo se supera la soglia, altrimenti "nessun facet". Eventuale multi-etichetta: tutti i facet sopra soglia.
- Output: facet e punteggio per finestra; le finestre scartate formano il residuo.
- I messaggi singoli ereditano il facet dalla finestra che li contiene.

**B2. Estrazione delle entità**
- Ricerca delle menzioni di professori e corsi tramite il dizionario.
- Output: entità per finestra.

**B3. Attribuzione al corso**
- Chat di corso: il corso è la chat.
- Chat generali: corso da menzioni esplicite; in assenza, similarità con le finestre dei corsi; in assenza ancora, "generale".

**B4. Aggregazione in note**
- Raggruppamento per (corso, facet).
- Output: note con le finestre ordinate per data.

**B5. Calcolo degli archi**
- Strutturali: nota→corso, nota→facet.
- Entità: nota→professore se citato.
- Similarità: nota↔nota sul vettore medio, con top-k e soglia minima (o solo vicini reciproci) per evitare il blob.
- Opzionale: community detection sul grafo di similarità per raggruppamenti emergenti.

**B6. Export in Obsidian**
- Un file `.md` per nota, corso, facet, professore.
- Frontmatter con tag, chat di origine, periodo.
- Wikilink verso i nodi collegati.
- Messaggi come citazioni con data e riferimento alla chat.
- Cartelle separate per tipo di nodo, così la graph view può colorarli.

---

## 6. Ciclo di aggiornamento

| Evento | Cosa si rifà |
|---|---|
| Nuovi messaggi in chat esistente | A1 e A2 solo sul nuovo, poi B1-B6 |
| Nuova chat | Come sopra, poi BERTopic solo sul residuo senza facet; cluster coerenti diventano candidati facet (A4-A5) |
| Nuovo dominio (non universitario) | Facet non pertinenti semplicemente non scattano; i nuovi emergono dal residuo |
| Cambio di soglia o tassonomia | Solo B1-B6, senza toccare ingest ed embedding |
| Cambio modello di embedding | Tutto da A2 in poi |

---

## 7. Organizzazione del codice (coerente con la struttura esistente)

Moduli già presenti: modelli, ingest Telegram, chunking, embeddings, vectorstore, search, CLI.

Moduli nuovi, in ordine di costruzione:

1. **Costruzione finestre**: estensione del chunking esistente con logica di reply e gap (valutare se riusare o affiancare).
2. **Topic discovery**: wrapper di BERTopic per chat, con salvataggio dei risultati.
3. **Tassonomia**: caricamento e salvataggio dei facet, calcolo dei prototipi.
4. **Assegnazione**: facet, entità, corso.
5. **Grafo**: note, archi, sfoltimento.
6. **Export Obsidian**: generazione dei file markdown.
7. **Valutazione**: caricamento del set etichettato, calcolo delle metriche.

Comandi CLI previsti (nomi indicativi): `windows`, `embed`, `discover`, `assign`, `graph`, `export`, `eval`. Ognuno legge e scrive i file della sezione 4.

---

## 8. Valutazione

- **Set etichettato:** ~100-150 finestre reali, ciascuna con facet corretto o "nessuno", e corso corretto per le chat generali.
- **Metriche:** precisione e recall per facet alla soglia scelta; percentuale di finestre scartate; confronto tra metodi di assegnazione (prototipo da centroide, da descrizione, media).
- **Split:** per tempo o per conversazione, mai a caso, per evitare quasi-duplicati che falsano i numeri.
- **Controlli sul grafo:** distribuzione dei gradi, facet che assorbono troppo, facet con prototipi quasi identici (da unire), note troppo piccole.

**Dati sintetici:** utili per verificare che la pipeline giri, ma i topic risultano più puliti del reale. Non tarare le soglie sul sintetico. Se possibile aggiungere rumore realistico (messaggi generici, ambigui, a metà tra due facet).

---

## 9. Decisioni aperte

1. Unità di assegnazione: finestra o messaggio singolo (consigliata la finestra, con propagazione ai messaggi).
2. Prototipo del facet: centroide, descrizione o media.
3. Singola etichetta o multi-etichetta per finestra.
4. Parametri delle finestre: soglia del gap per chat di corso e per chat generali, tetto di lunghezza.
5. Livello "intento" (domanda, opinione, avviso, richiesta materiale) come tag aggiuntivo indipendente dal dominio.
6. Uso di un LLM locale per proporre i nomi dei facet o per i casi ambigui (dipende dall'hardware).
7. Professori come nodi di prima classe o solo come etichette.
8. Visualizzazione: solo vault Obsidian, o anche versione interattiva nell'app.

---

## 10. Ordine di lavoro consigliato

1. Finestre su 4-5 chat, lettura a mano di un campione.
2. Embedding e BERTopic per chat; stampa di topic ed esempi.
3. Consolidamento e revisione: prima versione della tassonomia.
4. Set etichettato.
5. Assegnazione dei facet e prima misura di precisione.
6. Entità e attribuzione al corso.
7. Note e archi, con stampa testuale per verificare che abbiano senso.
8. Export in Obsidian e iterazione guardando il grafo reale.
9. Estensione a tutte le chat; ciclo di aggiornamento sul residuo.

Criterio per passare al passo successivo: il risultato del passo corrente è leggibile e sensato a mano, non solo "il codice gira".

---

## 11. Riferimenti da leggere

- Documentazione BERTopic: Guided Topic Modeling, Merge Models, Zero-shot Topic Modeling, Topics per Class, Hierarchical Topics.
- Documentazione sentence-transformers: semantic search e similarità.
- Documentazione Obsidian: link, tag, frontmatter, graph view.
- scikit-learn: calibrazione delle probabilità e classificazione one-vs-rest (se si passa a un classificatore).
- networkx: costruzione del grafo e algoritmi di community detection.
