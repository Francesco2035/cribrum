# core/merge_model.py

Costruisce la tabella di addestramento a partire dalle etichette e confronta i modelli con la regola del gap attuale.

## Librerie
`scikit-learn` (già installato):
- `DecisionTreeClassifier`, `RandomForestClassifier`, `HistGradientBoostingClassifier`, `LogisticRegression`;
- `SimpleImputer` e `StandardScaler` (solo per la logistica, che non accetta `NaN` e vuole feature sulla stessa scala);
- metriche e `export_text`.

## Logica
- **Obiettivo binario** (`TARGET`): `same` = unire (1); `new` ed `earlier` = separare (0). `unsure` viene escluso.
- **Chi addestra e chi misura.**
  - Le tue etichette sono il **set di test**.
  - Le etichette dell'assistente servono solo all'addestramento (`training_records`). Per una coppia etichettata da entrambi vale la tua, e quella dell'assistente viene scartata, così la stessa coppia non può stare sia nel training sia nel test.
- **Leave-one-chat-out** (`leave_one_chat_out`): per ogni chat del test si addestra un modello su tutte le **altre** chat, comprese le tue etichette delle altre chat, e si predice quella. Si misura così quanto il modello generalizza a una chat che non ha mai visto, che è il caso reale per un gruppo nuovo.
- **Baseline** (`gap_rule`): unire se il gap è entro la soglia del tipo di chat (`config/windows.yaml`). È la regola attuale.
- **Modelli** (`model_factories`): alberi di profondità 3 e 5, foresta, boosting e logistica, tutti con `class_weight="balanced"`. "Unire" è la classe più frequente, e senza bilanciamento un modello potrebbe vincere dicendo quasi sempre "unisci".
- **Metriche** (`scores`):
  - accuratezza;
  - **accuratezza bilanciata**, cioè la media dell'accuratezza sulle due classi: è la metrica principale;
  - F1 delle due classi.

  `accuracy_by_band` riporta l'accuratezza per fascia di gap.
- `with_floor`: variante mista, che unisce sempre sotto una soglia di gap e lascia decidere il modello sopra. In valutazione si applica alle predizioni leave-one-chat-out.
- `ablation_sets`: insiemi di feature dell'ablazione. Si parte da quelle di base, poi base + un gruppo alla volta, poi tutto insieme, e infine tutto + embedding se richiesto.
- `parse_feature_groups`: traduce `--features` di `merge train` (`all`, `base` oppure `density,author,...`) nella tupla di feature. Le feature di base sono sempre incluse.
- `tree_rules`: un albero poco profondo addestrato su tutte le etichette, stampato come regole leggibili, per capire *cosa* guarda il modello. Non serve a misurarlo.
