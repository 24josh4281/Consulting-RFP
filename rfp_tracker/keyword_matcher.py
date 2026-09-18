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


def matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized = normalize_text(text)
    return sorted({term for term in terms if _contains(normalized, term)})


def excluded_terms(text: str, keyword_config: dict) -> list[str]:
    return matched_terms(text, keyword_config.get("exclude_terms", []))


def is_excluded(text: str, keyword_config: dict) -> bool:
    return bool(excluded_terms(text, keyword_config))


def is_relevant(text: str, keyword_config: dict) -> bool:
    if is_excluded(text, keyword_config):
        return False
    result = score_text(text, keyword_config)
    min_score = int(keyword_config.get("min_relevance_score", 2))
    return result.score >= min_score


def extension_from_url(url: str) -> str:
    """Find a supported document extension in a URL or a human-facing link label.

    Some official boards expose a download endpoint without the filename in its URL,
    then add the filename and byte count to the link text.  Matching only ``endswith``
    loses the HWP/HWPX type in that common case.
    """
    clean = (url or "").lower()
    match = re.search(r"\.(pdf|hwpx|hwp|docx|doc|xlsx|xls|pptx|ppt|zip)(?=$|[?#\s()\[\],])", clean)
    if match:
        return match.group(1)
    return ""


def has_any_term(text: str, terms: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(_contains(normalized, term) for term in terms)
