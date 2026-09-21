from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class MatchResult:
    score: int
    keywords: list[str]


@dataclass(slots=True)
class G2BTitleAssessment:
    """Classify a 나라장터 title without using buyer or incidental metadata.

    ``strong`` items may enter the ordinary notice and alert workflow.
    ``needs_review`` items remain visible in the dashboard, but need a person to
    decide whether they are consulting opportunities.  ``ignore`` means the title
    itself has no configured climate/environment/GHG/ETS signal.
    """

    tier: str
    match: MatchResult
    strong_keywords: list[str]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _contains(text: str, term: str) -> bool:
    term_norm = normalize_text(term)
    if not term_norm:
        return False
    # Short Latin abbreviations (for example CDP, LCA, ETS) must be standalone
    # tokens.  Plain substring matching made unrelated titles such as ``CDPR``
    # look like CDP reporting opportunities.
    if re.fullmatch(r"[a-z0-9][a-z0-9 .-]*", term_norm):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term_norm)}(?![a-z0-9])", text))
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


def assess_g2b_title(title: str, keyword_config: dict) -> G2BTitleAssessment:
    """Apply the conservative G2B title-only intake rule.

    G2B list responses include fields such as buyer names and administrative
    descriptions.  Scoring every field makes a non-environmental cybersecurity
    tender look relevant merely because its buyer contains ``환경``.  This helper
    evaluates only the public notice title and keeps ambiguous environmental
    notices in a human-review tier instead of silently dropping them.
    """

    match = score_text(title, keyword_config)
    groups = keyword_config.get("keyword_groups", {})
    policy = keyword_config.get("g2b_title_policy", {})

    group_hits = {
        group_name: matched_terms(title, terms)
        for group_name, terms in groups.items()
    }
    # Assurance words (검증, 검토, 인증) are supporting evidence, not a
    # climate-domain signal by themselves.  They must accompany one of the
    # specified domain groups below.
    domain_groups = policy.get(
        "domain_keyword_groups",
        ["climate_core", "environment", "ghg", "ets", "reporting", "risk"],
    )
    domain_hits = sorted(
        {
            term
            for group_name in domain_groups
            for term in group_hits.get(str(group_name), [])
        }
    )
    if not domain_hits:
        return G2BTitleAssessment("ignore", match, [])

    if policy.get("enabled", True) is False:
        return G2BTitleAssessment("strong", match, domain_hits)

    strong_groups = policy.get(
        "strong_keyword_groups",
        ["climate_core", "ghg", "ets", "reporting", "risk"],
    )
    strong_group_hits = sorted(
        {
            term
            for group_name in strong_groups
            for term in group_hits.get(str(group_name), [])
        }
    )

    environment_terms = groups.get("environment", [])
    generic_environment_terms = policy.get(
        "generic_environment_terms",
        ["환경", "환경부", "환경관리"],
    )
    generic_normalized = {normalize_text(term) for term in generic_environment_terms}
    specific_environment_terms = [
        term for term in environment_terms if normalize_text(term) not in generic_normalized
    ]
    specific_environment_hits = matched_terms(title, specific_environment_terms)

    explicit_environment_terms = policy.get(
        "explicit_consulting_environment_terms",
        [
            "환경정책",
            "환경영향평가",
            "환경성 검토",
            "환경컨설팅",
            "환경조사",
            "전과정평가",
            "lca",
            "탄소발자국",
            "환경성적표지",
        ],
    )
    explicit_environment_hits = matched_terms(title, explicit_environment_terms)
    advisory_terms = policy.get(
        "advisory_terms",
        ["컨설팅", "연구", "평가", "조사", "분석", "계획", "설계", "검토", "검증", "진단", "모니터링", "개발"],
    )
    advisory_hits = matched_terms(title, advisory_terms)

    if strong_group_hits or explicit_environment_hits:
        return G2BTitleAssessment(
            "strong",
            match,
            sorted(set(strong_group_hits + explicit_environment_hits)),
        )
    if specific_environment_hits and advisory_hits:
        return G2BTitleAssessment(
            "strong",
            match,
            sorted(set(specific_environment_hits + advisory_hits)),
        )
    return G2BTitleAssessment("needs_review", match, domain_hits)


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
