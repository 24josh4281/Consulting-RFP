from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_dotenv(path: str | Path, *, override: bool = False) -> int:
    """Load simple KEY=VALUE pairs from a local .env file without printing secrets."""
    file_path = Path(path)
    if not file_path.exists():
        return 0

    loaded_count = 0
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        loaded_count += 1
    return loaded_count


def resolve_workspace_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if base_dir is not None:
        return Path(base_dir) / candidate
    return Path.cwd() / candidate


def enabled_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in config.get("sources", []) if source.get("enabled", False)]


def set_source_enabled(config: dict[str, Any], source_id: str, enabled: bool) -> bool:
    for source in config.get("sources", []):
        if source.get("id") == source_id:
            source["enabled"] = enabled
            return True
    return False
