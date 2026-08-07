from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ApiKeyStatus:
    id: str
    name: str
    env: str
    present: bool
    apply_url: str
    required_for: list[str]
    notes: str


def get_api_key_status(key_config: dict[str, Any]) -> list[ApiKeyStatus]:
    statuses: list[ApiKeyStatus] = []
    for item in key_config.get("keys", []):
        env_name = item["env"]
        value = os.environ.get(env_name, "")
        statuses.append(
            ApiKeyStatus(
                id=item["id"],
                name=item["name"],
                env=env_name,
                present=bool(value.strip()),
                apply_url=item.get("apply_url", ""),
                required_for=list(item.get("required_for", [])),
                notes=item.get("notes", ""),
            )
        )
    return statuses

