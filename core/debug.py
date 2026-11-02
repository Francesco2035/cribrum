import json
from dataclasses import asdict
from pathlib import Path
from core.models import Message


def dump_messages_to_json(messages: list[Message], path: Path) -> None:
    """Writes a list of Message objects to a JSON file, for inspection/debugging."""
    data = [asdict(m) for m in messages]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)