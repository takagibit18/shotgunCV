from __future__ import annotations

import json
from dataclasses import MISSING, asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage_dir(run_dir: Path, stage: str) -> Path:
    return ensure_directory(run_dir / stage)


def dump_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_plain_data(payload), handle, indent=2, ensure_ascii=False)
    return path


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def to_plain_data(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain_data(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def hydrate(model_type: type[Any], payload: Any) -> Any:
    if payload is None:
        return None

    origin = get_origin(model_type)
    if origin is list:
        item_type = get_args(model_type)[0]
        return [hydrate(item_type, item) for item in payload]

    if not is_dataclass(model_type):
        return payload

    hints = get_type_hints(model_type)
    values: dict[str, Any] = {}
    for field in fields(model_type):
        field_type = hints[field.name]
        if field.name in payload:
            values[field.name] = hydrate(field_type, payload[field.name])
            continue
        if field.default is not MISSING:
            values[field.name] = field.default
            continue
        if field.default_factory is not MISSING:  # type: ignore[attr-defined]
            values[field.name] = field.default_factory()  # type: ignore[misc]
            continue
        raise KeyError(f"Missing required field `{field.name}` for `{model_type.__name__}`.")
    return model_type(**values)
