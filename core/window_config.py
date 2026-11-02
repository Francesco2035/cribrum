import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

CHAT_TYPES = ("course", "general")


@dataclass(frozen=True)
class WindowParams:
    tokenizer_model: str = "intfloat/multilingual-e5-base"
    default_chat_type: str = "course"
    chat_types: dict[str, str] = field(default_factory=dict)
    gap: dict[str, int] = field(default_factory=lambda: {"course": 600, "general": 900})
    reply_max_gap: int = 21600
    burst_gap: int = 120
    dependent_gap: int = 300
    mention_gap: int = 1800
    max_messages: int = 40
    max_tokens: int = 512
    overlap: int = 0
    short_max_messages: int = 1
    short_min_tokens: int = 8
    include: dict[str, bool] = field(
        default_factory=lambda: {"service": False, "media": True, "forwarded": True, "poll": True}
    )
    dependent_phrases: tuple[str, ...] = ()
    mention_aliases: dict[str, str] = field(default_factory=dict)
    min_date: str | None = None     # ISO date, inclusive; set from config.yaml `dates`
    max_date: str | None = None     # ISO date, exclusive
    blocked_ids: tuple[str, ...] = ()   # from_ids from config/blocklist.yaml
    merge_model: str | None = None      # id of the trained merge model replacing the gap rule (None = gap rule)

    def chat_type_for(self, chat_id: int) -> str:
        return self.chat_types.get(str(chat_id), self.default_chat_type)

    def gap_for(self, chat_type: str) -> int:
        return self.gap[chat_type]


def load_window_params(path: Path, overrides: dict | None = None) -> tuple[WindowParams, dict]:
    """Returns the params plus the `inspect` section (sampling settings that
    don't affect the windows, hence not part of the hash)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    inspect = raw.pop("inspect", {}) or {}
    known = {f.name for f in dataclasses.fields(WindowParams)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown window config keys in {path}: {sorted(unknown)}")

    defaults = WindowParams()
    raw["chat_types"] = {str(k): v for k, v in (raw.get("chat_types") or {}).items()}
    raw["gap"] = {**defaults.gap, **(raw.get("gap") or {})}
    raw["include"] = {**defaults.include, **(raw.get("include") or {})}
    raw["dependent_phrases"] = tuple(str(p) for p in raw.get("dependent_phrases") or ())
    raw["mention_aliases"] = {str(k).lower(): v for k, v in (raw.get("mention_aliases") or {}).items()}

    params = apply_overrides(WindowParams(**raw), overrides or {})
    _validate(params)
    return params, inspect


def apply_overrides(params: WindowParams, overrides: dict) -> WindowParams:
    """Overrides use flat names; `gap_course` / `gap_general` target the gap dict."""
    overrides = {k: v for k, v in overrides.items() if v is not None}
    gap = dict(params.gap)
    for chat_type in CHAT_TYPES:
        if f"gap_{chat_type}" in overrides:
            gap[chat_type] = overrides.pop(f"gap_{chat_type}")
    return dataclasses.replace(params, gap=gap, **overrides)


def config_hash(params: WindowParams, chat_type: str) -> str:
    """Hash of the parameters that actually shape one chat's windows: the
    chat_types mapping is replaced by the resolved type, so adding a new chat
    to the mapping doesn't change the hash of the others."""
    data = dataclasses.asdict(params)
    data.pop("chat_types")
    data.pop("default_chat_type")
    data["chat_type"] = chat_type
    if data["merge_model"] is None:      # absent = gap rule: hashes from before the field stay the same
        data.pop("merge_model")
    data["dependent_phrases"] = sorted(data["dependent_phrases"])
    data["blocked_ids"] = sorted(data["blocked_ids"])
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _validate(params: WindowParams) -> None:
    for chat_type in [params.default_chat_type, *params.chat_types.values()]:
        if chat_type not in CHAT_TYPES:
            raise ValueError(f"Unknown chat type '{chat_type}', expected one of {CHAT_TYPES}")
    if params.max_messages < 1 or params.max_tokens < 1:
        raise ValueError("max_messages and max_tokens must be >= 1")
    if not 0 <= params.overlap < params.max_messages:
        raise ValueError("overlap must be >= 0 and smaller than max_messages")
    for d in (params.min_date, params.max_date):
        if d is not None:
            datetime.fromisoformat(d)
