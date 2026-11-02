# config/facets.yaml

Parametri di `facets`. Nessuno dipende dal dominio delle chat. I primi due sono soglie sulla similarità coseno nello spazio comune, il terzo è un percentile ricavato dai dati.

| chiave | default | significato |
|---|---|---|
| `merge_similarity` | 0.45 | due gruppi di argomenti si uniscono in un facet se la loro similarità media è almeno questa. Più bassa = facet più ampi e meno numerosi |
| `min_chats` | 2 | un facet i cui argomenti vengono da almeno questo numero di chat è **condiviso**; altrimenti è un **concetto locale** |
| `member_percentile` | 25 | una finestra senza argomento entra nel facet più vicino (tra quelli della sua chat) se è vicina almeno quanto questo percentile dei membri del facet |
| `top_n_words` | 10 | parole chiave salvate per facet |
| `n_examples` | 3 | finestre di esempio per facet |
| `stop_words_file` | `config/topic_stopwords.yaml` | parole escluse dalle parole chiave (le stesse di `discover`) |

## Come sono stati scelti (9 chat, 211 argomenti)
`merge_similarity`:

| valore | facet | condivisi | osservazione |
|---|---|---|---|
| 0.35 | 63 | 31 | un facet "blob" di 950 finestre mette insieme gli esercizi tecnici di 6 corsi |
| 0.40 | 82 | 34 | blob più piccolo (438 finestre, 4 corsi) |
| **0.45** | 93 | 37 | facet specifici, nessun blob grande |
| 0.50 | 111 | 38 | gli stessi temi cominciano a dividersi in più facet |

`member_percentile`, valutato leggendo un campione di finestre assegnate per vicinanza:
- con **10** quasi metà dei facet ha una soglia sotto 0.33, e lì le assegnazioni sono per lo più sbagliate (per esempio una battuta finita nel facet dei voti);
- con **25** solo il 16% dei facet ha una soglia sotto 0.33, e il campione sopra quella zona è quasi tutto corretto. Si recuperano 1217 finestre;
- con **50** se ne recuperano solo 471.

Con questi valori il 74% delle finestre ammissibili ha un facet (60% tramite un argomento, 14% per vicinanza). Con altre chat conviene ricontrollare: la tabella stampata da `facets` mostra subito se compaiono blob (un facet molto più grande degli altri) o temi spezzati.
