# window_config.py

## Librerie
- `yaml` (PyYAML): legge `config/windows.yaml` con `safe_load`, che non esegue tag Python arbitrari.
- `dataclasses`: `WindowParams` è `frozen=True` (immutabile); `dataclasses.replace` ne crea una copia con alcuni campi cambiati, `dataclasses.fields` elenca i campi validi e `dataclasses.asdict` converte in dizionario.
- `hashlib`, `json`: calcolano l'hash della configurazione.

## Logica
- `load_window_params(path, overrides)`: legge lo YAML, separa la sezione `inspect` (seed e dimensione del campione, che non influiscono sulle finestre), rifiuta le chiavi sconosciute (così un errore di battitura non passa in silenzio), fonde i dizionari annidati (`gap`, `include`) con i default e applica gli override della CLI.
- `apply_overrides`: gli override hanno nomi piatti; `gap_course` e `gap_general` vengono instradati dentro il dizionario `gap`. I valori `None` (opzione non passata) vengono ignorati.
- `config_hash(params, chat_type)`: hash SHA-256 (primi 12 caratteri esadecimali) del JSON canonico dei parametri **effettivi per una chat**. La mappa `chat_types` viene sostituita dal tipo risolto, così aggiungere una chat nuova alla mappa non cambia l'hash delle altre. Le frasi dipendenti vengono ordinate, perché l'ordine nel file non conta.

- `blocked_ids`: `from_id` degli account in blocklist (`config/blocklist.yaml`). Arrivano dalla CLI come override, come le date, ed entrano nell'hash ordinati.
- `min_date` / `max_date`: intervallo di date. Arrivano da `config.yaml` (sezione `dates`) tramite la CLI, come override, e quindi entrano nell'hash; `_validate` controlla che siano date ISO valide.

- `merge_model`: id del modello delle unioni (`merge train`) che sostituisce la regola del gap, `None` = regola del gap. Non si imposta nello YAML ma dalla CLI (`windows --merge-model FILE`), che ricava l'id dall'hash del file. Quando è `None` il campo viene tolto dall'hash, così le configurazioni precedenti al campo mantengono lo stesso hash e le stesse cartelle.

## Costrutti
- `json.dumps(..., sort_keys=True)`: rende la serializzazione deterministica (stesso dizionario → stessa stringa → stesso hash), indipendentemente dall'ordine di inserimento delle chiavi.
- Le chiavi di `chat_types` vengono convertite in stringa perché YAML legge `1525042706:` come intero mentre la CLI passa una stringa.
