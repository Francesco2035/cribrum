# PyYAML

Legge e scrive file YAML e li converte in strutture Python (dict, list, str,
int, float, bool, None).

Doc: https://pyyaml.org/wiki/PyYAMLDocumentation

## Uso

```python
from pathlib import Path
import yaml

with Path("config.yaml").open(encoding="utf-8") as f:
    config = yaml.safe_load(f)      # -> dict (oppure None se il file è vuoto)

config["embedding"]["model"]        # accesso come un normale dict
```

## Esempio di YAML e il suo equivalente Python

```yaml
paths:
  raw: data/raw
  chroma: data/chroma_db
embedding:
  model: intfloat/multilingual-e5-small
  batch_size: 32
synth:
  enabled: false
courses:
  - id: am1
    name: Analisi Matematica 1
    aliases: [AM1, analisi 1, analisi uno]
```

```python
{
  "paths": {"raw": "data/raw", "chroma": "data/chroma_db"},
  "embedding": {"model": "intfloat/multilingual-e5-small", "batch_size": 32},
  "synth": {"enabled": False},
  "courses": [{"id": "am1", "name": "Analisi Matematica 1",
               "aliases": ["AM1", "analisi 1", "analisi uno"]}],
}
```

## Trappole

- **Usa sempre `yaml.safe_load`**, mai `yaml.load` senza `Loader`: la versione non sicura può istanziare oggetti Python arbitrari.
- **File vuoto → `None`**, non `{}`. Il nostro `config.yaml` adesso è vuoto! Quindi scrivi `config = yaml.safe_load(f) or {}`.
- **Tipi impliciti**: `yes`, `no`, `on` e `off` diventano booleani, e `010` può diventare un numero. Nel dubbio metti le stringhe tra virgolette (`"AM1"`, `"no"`).
- **Indentazione**: solo spazi, niente tab.
- Il dict non ha validazione: se manca una chiave ottieni un `KeyError` più avanti. Conviene convertire la config in una dataclass con valori di default (vedi `core/config.py` in ARCHITECTURE.md).
