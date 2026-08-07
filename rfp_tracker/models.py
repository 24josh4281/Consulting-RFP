from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Attachment:
    label: str
    url: str
    file_type: str = ""


@dataclass(slots=True)
class Notice:
    source_id: str
    source_name: str
    external_id: str
    title: str
    url: str
    published_at: str = ""
    deadline_at: str = ""
    buyer: str = ""
    budget: str = ""
    procurement_method: str = ""
    category: str = ""
    relevance_score: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

