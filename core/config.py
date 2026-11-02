from pathlib import Path
import yaml


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File di config non trovato: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if cfg is None:
        raise ValueError(f"Il file di config {path} è vuoto o malformato")

    return cfg

def load_blocklist(path: Path) -> dict[str, str]:
    """Blocked accounts as {from_id: display name}. A missing file means no block."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {str(a["from_id"]): str(a.get("name", "")) for a in raw.get("accounts") or []}


def save_blocklist(path: Path, accounts: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"accounts": [{"from_id": fid, "name": name} for fid, name in sorted(accounts.items())]}
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Accounts whose messages are dropped before building windows and pairs.\n")
        f.write("# Managed with `cli.main blocklist list|add|remove`; editing by hand works too.\n")
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def match_accounts(authors: dict[str, str], query: str) -> dict[str, str]:
    """Accounts matching a from_id exactly, or whose name contains the query (case-insensitive)."""
    if query in authors:
        return {query: authors[query]}
    q = query.lower()
    return {fid: name for fid, name in authors.items() if q in name.lower()}


def blocklist_path(cfg: dict) -> Path:
    return Path(cfg["paths"].get("blocklist", "config/blocklist.yaml"))


def blocked_ids(cfg: dict) -> tuple[str, ...]:
    return tuple(load_blocklist(blocklist_path(cfg)))


CUE_LISTS = ("group_request", "answer_start", "anaphora_start")


def load_merge_cues(path: Path) -> dict[str, tuple[str, ...]]:
    """Word lists of the merge model's text cues. A missing file or list means an empty list."""
    raw = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    unknown = set(raw) - set(CUE_LISTS)
    if unknown:
        raise ValueError(f"Unknown cue lists in {path}: {sorted(unknown)}")
    return {name: tuple(str(p) for p in raw.get(name) or ()) for name in CUE_LISTS}


def merge_cues_path(cfg: dict) -> Path:
    return Path(cfg["paths"].get("merge_cues", "config/merge_cues.yaml"))


def export_paths(cfg: dict) -> list[Path]:
    return sorted(Path(cfg["paths"]["raw_data"]).glob("*.json"), key=lambda p: p.stem.lower())
