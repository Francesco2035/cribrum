# Taratura delle finestre — risultati

Dati: i 9 export in `data/exports/`, solo messaggi dal **2023-01-01** (`dates.min_date` in `config.yaml`). Report grezzo, rigenerabile: `HF_HUB_OFFLINE=1 uv run python scripts/tune_windows.py` → `data/windows/tuning/report.md`.

## Metodo
Le statistiche da sole dicono solo *quanto* una configurazione unisce, non se unisce bene. Per giudicare ho letto i **casi di confine**: coppie di messaggi consecutivi il cui gap cade tra due soglie candidate. Sono le sole decisioni che cambiano da una configurazione all'altra. Per ogni chat, 3 coppie casuali (seed 42) per fascia, giudicate a mano come "stessa conversazione" o "conversazioni diverse".

Il campione è piccolo (27 coppie per fascia, sommando le 9 chat), quindi le percentuali sono indicative.

| regola | fascia | stessa conversazione |
|---|---|---|
| gap (autori diversi, senza reply) | 5–10 min | ~17/27 (63%) |
| | 10–15 min | ~22/27 (81%) |
| | 15–30 min | ~20/27 (74%) |
| | 30–60 min | ~12/27 (44%) |
| raffica stesso autore | 1–2 min | ~23/27 (85%) |
| | 2–5 min | ~24/27 (89%) |
| reply (padre → risposta) | 3–6 h | 27/27 |
| | 6–12 h | ~27/27 |
| | 12–24 h | 27/27 |

## Cosa ne ricavo
- **Gap.** Fino a circa 30 minuti, due messaggi vicini sono più spesso della stessa conversazione che no (~70–80%); oltre i 30 minuti si scende sotto il 50%. Il 63% della fascia 5–10 min è più basso di quelle successive per due motivi: le chat affollate (anndl, UAI, CSGeneral) hanno conversazioni parallele anche a pochi minuti di distanza, e il campione è piccolo. → `gap.course` **1200 s (20 min)**, `gap.general` **1800 s (30 min)**. Le due chat generali (CSGeneral, t2i) reggono bene anche 30–60 min (4/6), quelle di corso affollate no.
- **Raffica.** Lo stesso autore entro 5 minuti continua quasi sempre lo stesso discorso. I pochi errori sono di chi ringrazia e poi fa subito una domanda nuova. → `burst_gap` **300 s**.
- **Reply.** Un reply esplicito è affidabile anche a 24 ore di distanza: in tutte le coppie lette la risposta riguardava il messaggio citato. Il limite di 6 h scartava legami buoni (es. anndl: 152 reply "troppo vecchi"). → `reply_max_gap` **86400 s (24 h)**. Oltre le 24 h non ho misurato.
- **Invariati:** `dependent_gap` 300, `max_messages` 40, `max_tokens` 512, `overlap` 0.

## Configurazione proposta: `config/windows_proposed.yaml`
I default in `config/windows.yaml` **non sono stati cambiati**: la proposta è in un file separato, da controllare prima di adottarla.

## Risultati chat per chat (default → proposta)

| chat | tipo | messaggi | finestre | da 1 msg % | msg/finestra p50/p90 | token medi | chiuse dal tetto |
|---|---|---|---|---|---|---|---|
| anndl | corso | 8928 | 2383 → 1909 | 45.1 → 37.8 | 2/9 → 2/13 | 87 → 108 | 113 → 152 |
| computer_ethics | corso | 1014 | 466 → 405 | 60.9 → 54.1 | 1/5 → 1/5 | 55 → 63 | 2 → 3 |
| CSGeneral | generale | 10640 | 3457 → 2811 | 47.4 → 40.2 | 2/7 → 2/9 | 92 → 113 | 96 → 141 |
| datamining | corso | 1930 | 611 → 493 | 49.6 → 42.0 | 2/7 → 2/10 | 70 → 87 | 16 → 19 |
| MAS | corso | 825 | 260 → 222 | 52.7 → 42.3 | 1/7 → 2/9 | 73 → 85 | 4 → 7 |
| NLP | corso | 2281 | 889 → 755 | 55.1 → 50.2 | 1/5 → 1/7 | 49 → 57 | 7 → 7 |
| RS | corso | 2270 | 868 → 715 | 51.7 → 45.0 | 1/5 → 2/7 | 60 → 72 | 10 → 12 |
| t2i | generale | 2160 | 759 → 644 | 50.3 → 43.3 | 1/6 → 2/8 | 88 → 104 | 16 → 22 |
| UAI | corso | 3859 | 1095 → 898 | 47.7 → 41.8 | 2/8 → 2/12 | 76 → 93 | 30 → 46 |

Note per chat:
- **anndl, UAI** (corso, molto attive): gap mediano 141–165 s e molte conversazioni parallele; sono le chat in cui il gap sbaglia di più. Il tetto interviene più spesso (150 finestre su 1900 in anndl): se le continuazioni risultano spezzate a metà discorso, valutare `overlap` 2–3.
- **datamining, MAS, RS, NLP, computer_ethics** (corso, più lente): domanda e risposta breve a 15–30 min di distanza sono la norma ("Is it at 9 or 8?" → "Somebody told me 9"), quindi la soglia più ampia recupera molte coppie. computer_ethics resta la più frammentata (54% da un messaggio): molte domande senza risposta.
- **CSGeneral, t2i** (generali): conversazioni lente (gap mediano 423–454 s), molti consigli su corsi e piani di studio; 30 min sono ragionevoli. In CSGeneral ci sono 160 reply orfani (messaggi citati precedenti al 2023 o assenti dall'export) e un bot (PoliNetwork) che ripete messaggi a raffica.

## Limiti e osservazioni
- **Circa metà delle finestre resta da un messaggio** anche con la proposta (38–54%). Non è un difetto delle soglie: sono in gran parte domande senza risposta o annunci isolati, marcati `is_short`.
- **La regola mention non scatta quasi mai** (0–1 unioni per chat): l'export non contiene gli username, e il confronto con i nomi visualizzati raramente è univoco. Per renderla utile servono gli alias in `mention_aliases`.
- **Un limite strutturale del gap**: in una chat affollata, una domanda nuova che arriva 3 minuti dopo un'altra conversazione viene unita a quella. Le soglie non possono risolverlo. Una possibile regola futura: non unire per gap un messaggio che "apre un argomento" (domanda lunga, "Qualcuno sa…", "Ciao ragazzi…").
- **La soglia ideale sembra dipendere più dall'attività della chat che dal tipo** (corso/generale): le chat di corso lente si comportano come quelle generali. Si potrebbe aggiungere una soglia per singola chat, se serve.

## Come controllare
```
HF_HUB_OFFLINE=1 uv run python -m cli.main windows anndl --windows-config config/windows_proposed.yaml --sample 20
HF_HUB_OFFLINE=1 uv run python -m cli.main windows datamining --windows-config config/windows_proposed.yaml --sample 20
HF_HUB_OFFLINE=1 uv run python -m cli.main windows CSGeneral --windows-config config/windows_proposed.yaml --sample 20
```
Leggi `sample.md` nella cartella stampata alla fine, seguendo la procedura di `docs/it/code/config/windows.md` ("Come tarare le soglie"). Se ti convince, copia i quattro valori in `config/windows.yaml`.
