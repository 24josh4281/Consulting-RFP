from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class MatchResult:
    score: int
    keywords: list[str]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _contains(text: str, term: str) -> bool:
    term_norm = normalize_text(term)
    if not term_norm:
        return False
    return term_norm in text


def score_text(text: str, keyword_config: dict) -> MatchResult:
    normalized = normalize_text(text)
    matched: list[str] = []
    score = 0

    for group_name, terms in keyword_config.get("keyword_groups", {}).items():
        group_hit = False
        for term in terms:
            if _contains(normalized, term):
                matched.append(term)
                group_hit = True
        if group_hit:
            if group_name in {"climate_core", "ghg", "ets"}:
                score += 3
            else:
                score += 2

    for term in keyword_config.get("tender_terms", []):
        if _contains(normalized, term):
            matched.append(term)
            score += 1

    return MatchResult(score=score, keywords=sorted(set(matched)))


def is_relevant(text: str, keyword_config: dict) -> bool:
    result = score_text(text, keyword_config)
    min_score = int(keyword_config.get("min_relevance_score", 2))
    return result.score >= min_score


def extension_from_url(url: str) -> str:
    clean = (url or "").split("?", 1)[0].split("#", 1)[0].lower()
    for extension in (".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip"):
        if clean.endswith(extension):
            return extension.lstrip(".")
    return ""


def has_any_term(text: str, terms: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(_contains(normalized, term) for term in terms)

