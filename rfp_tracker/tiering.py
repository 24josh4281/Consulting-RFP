from __future__ import annotations

"""Explainable business-fit classification for Innergen's RFP workflow.

This module deliberately evaluates only collected public notice metadata.  It does not
infer bid eligibility or change any source text.  A human may override its result through
the CLI; storage preserves that manual decision on later syncs.
"""

import re
from dataclasses import dataclass
from typing import Iterable


TIER_1 = "tier_1"
TIER_2 = "tier_2"
TIER_3 = "tier_3"
UNCLASSIFIED = "unclassified"
VALID_BUSINESS_TIERS = {TIER_1, TIER_2, TIER_3, UNCLASSIFIED}

TIER_LABELS = {
    TIER_1: "Tier 1 · 이너젠 직접 컨설팅 검토",
    TIER_2: "Tier 2 · 고객사 추천 가능 사업",
    TIER_3: "Tier 3 · 참고 / 직접 컨설팅 비적합",
    UNCLASSIFIED: "미분류 · 원문 확인 필요",
}

TIER_SHORT_LABELS = {
    TIER_1: "Tier 1",
    TIER_2: "Tier 2",
    TIER_3: "Tier 3",
    UNCLASSIFIED: "미분류",
}


@dataclass(frozen=True, slots=True)
class TierAssessment:
    tier: str
    reason: str
    matched_signals: tuple[str, ...] = ()


# Tier 3 is intentionally evaluated first.  A climate keyword occurring in a fund,
# event, promotional video, or science-only project should not create an Innergen
# consulting alert.
TIER_3_NON_CONSULTING_SIGNALS = (
    "투자유치",
    "투자",
    "펀드",
    "ir 행사",
    "행사",
    "포럼",
    "세미나",
    "컨퍼런스",
    "콘퍼런스",
    "박람회",
    "전시",
    "캠페인",
    "홍보",
    "영상",
    "콘텐츠 제작",
    "촬영",
    "교육",
    "연수",
    "공모전",
    "시상",
)

TIER_3_SCIENCE_SIGNALS = (
    "순수과학",
    "기초과학",
    "기초 연구",
    "실험실",
    "실험",
    "시료",
    "시약",
    "분석장비",
    "유전자",
    "미생물",
    "천문",
    "원자력",
    "핵연료",
    "심해",
    "부식",
    "소재",
    "파우더",
)

# These are direct Innergen-style consulting themes.  They take priority over an
# equipment/IT word because, for example, an ETS information-system improvement still
# belongs in the ETS consulting opportunity queue.
TIER_1_EXPLICIT_SIGNALS = (
    "온실가스 외부사업",
    "외부사업",
    "배출권거래제",
    "배출권 거래제",
    "배출권",
    "k-ets",
    " ets ",
    "scope 1",
    "scope 2",
    "scope 3",
    "스코프1",
    "스코프2",
    "스코프3",
    "온실가스 산정",
    "배출량 산정",
    "배출계수",
    "온실가스 인벤토리",
    "인벤토리",
    "명세서",
    "모니터링계획",
    "모니터링 계획",
    "감축실적",
    "상쇄",
    "할당",
    "mrv",
    "기후리스크",
    "전환리스크",
    "물리적 리스크",
    "시나리오 분석",
    "기후변화 산업",
    "cdp",
    "tcfd",
    "tnfd",
    "issb",
    "ifrs s1",
    "ifrs s2",
    "지속가능보고서",
    "지속가능경영보고서",
)

TIER_1_DOMAIN_SIGNALS = (
    "기후변화",
    "기후위기",
    "기후",
    "온실가스",
    "배출권",
    "탄소중립",
    "넷제로",
    "net zero",
    "탈탄소",
    "탄소발자국",
    "전과정평가",
    "lca",
    "환경성적표지",
    "기후적응",
    "esg",
)

TIER_1_WORK_SIGNALS = (
    "컨설팅",
    "산정",
    "고도화",
    "분석",
    "시나리오",
    "전략",
    "로드맵",
    "전환계획",
    "계획 수립",
    "이행계획",
    "검토",
    "검증",
    "인증",
    "명세",
    "모니터링",
    "인벤토리",
    "연구",
    "조사",
    "평가",
    "진단",
    "관리체계",
)

# Tier 2 means a climate/environment-related physical, operational, or technical
# project that may fit a customer's recommendation rather than Innergen's own core work.
TIER_2_DOMAIN_SIGNALS = (
    "기후",
    "탄소",
    "온실가스",
    "배출",
    "환경",
    "대기",
    "수질",
    "물순환",
    "비점오염",
    "인공습지",
    "자원순환",
    "순환경제",
    "재생에너지",
    "신재생에너지",
    "에너지효율",
    "친환경",
    "환경영향평가",
)

TIER_2_SUPPORT_SIGNALS = (
    "설비",
    "시설",
    "장비",
    "시공",
    "공사",
    "설치",
    "보수",
    "유지보수",
    "정비",
    "현대화",
    "기본설계",
    "실시설계",
    "처리시설",
    "처리장",
    "정화",
    "공법",
    "플랫폼 개발",
    "시스템 구축",
    "제품",
    "품질인증",
    "현장평가",
    "환경개선",
    "사후환경영향조사",
    "운영",
    "관리 대행",
)

TIER_2_REFERRAL_SIGNALS = (
    "환경영향평가",
    "사후환경영향조사",
    "환경성 검토",
    "환경조사",
    "환경관리",
)


def tier_label(tier: str) -> str:
    return TIER_LABELS.get(tier, TIER_LABELS[UNCLASSIFIED])


def tier_short_label(tier: str) -> str:
    return TIER_SHORT_LABELS.get(tier, TIER_SHORT_LABELS[UNCLASSIFIED])


def _normalized_text(title: str, category: str, matched_keywords: Iterable[str] | None) -> str:
    parts = [title or "", category or ""]
    if matched_keywords:
        parts.extend(str(keyword) for keyword in matched_keywords)
    return " ".join(" ".join(parts).casefold().split())


def _signals(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    matched: list[str] = []
    for term in terms:
        needle = term.casefold()
        # The source matcher already treats English abbreviations as whole tokens.
        # Apply the same safeguard here so CDPR is not explained as a CDP opportunity.
        if needle.isascii() and any(character.isalpha() for character in needle):
            pattern = r"(?<![a-z0-9])" + re.escape(needle.strip()) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                matched.append(term)
        elif needle in text:
            matched.append(term)
    return tuple(matched)


def _reason(prefix: str, signals: Iterable[str]) -> str:
    visible = list(signals)[:3]
    if visible:
        return f"{prefix} ({', '.join(visible)})"
    return prefix


def _combined_signals(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(signal for group in groups for signal in group))


def assess_innergen_tier(
    title: str,
    *,
    category: str = "",
    matched_keywords: Iterable[str] | None = None,
) -> TierAssessment:
    """Classify a notice into a business-fit tier without mutating source data.

    The decision uses the title first and may supplement it with a source category.  The
    general tracker keyword list is deliberately not passed by the sync path: it can contain
    a broad source-side match and must not elevate an unrelated security/IT procurement.
    Buyer names are also excluded because a buyer named "환경…" must not turn an unrelated
    procurement into a climate consulting opportunity.
    """

    text = _normalized_text(title, category, matched_keywords)
    if not text:
        return TierAssessment(TIER_3, "공고 제목·업무 신호가 없어 직접 컨설팅 적합성을 확인하지 못함")

    non_consulting = _signals(text, TIER_3_NON_CONSULTING_SIGNALS)
    if non_consulting:
        return TierAssessment(
            TIER_3,
            _reason("행사·영상·투자·교육 등 직접 컨설팅과 거리가 있는 사업 신호", non_consulting),
            non_consulting,
        )

    explicit_tier_1 = _signals(text, TIER_1_EXPLICIT_SIGNALS)
    if explicit_tier_1:
        return TierAssessment(
            TIER_1,
            _reason("이너젠 핵심 기후·GHG·ETS 컨설팅 신호", explicit_tier_1),
            explicit_tier_1,
        )

    science_only = _signals(text, TIER_3_SCIENCE_SIGNALS)
    if science_only:
        return TierAssessment(
            TIER_3,
            _reason("순수 과학·실험 중심 사업 신호", science_only),
            science_only,
        )

    tier_2_domain = _signals(text, TIER_2_DOMAIN_SIGNALS)
    tier_2_support = _signals(text, TIER_2_SUPPORT_SIGNALS)
    if tier_2_domain and tier_2_support:
        signals = _combined_signals(tier_2_domain, tier_2_support)
        return TierAssessment(
            TIER_2,
            _reason("기후·환경 관련 설비·시설·기술 지원 사업 신호", signals),
            signals,
        )

    tier_2_referral = _signals(text, TIER_2_REFERRAL_SIGNALS)
    if tier_2_domain and tier_2_referral:
        signals = _combined_signals(tier_2_domain, tier_2_referral)
        return TierAssessment(
            TIER_2,
            _reason("이너젠 핵심 범위 밖 환경 컨설팅·고객사 추천 신호", signals),
            signals,
        )

    tier_1_domain = _signals(text, TIER_1_DOMAIN_SIGNALS)
    tier_1_work = _signals(text, TIER_1_WORK_SIGNALS)
    if tier_1_domain and tier_1_work:
        signals = _combined_signals(tier_1_domain, tier_1_work)
        return TierAssessment(
            TIER_1,
            _reason("기후·탄소 주제의 컨설팅·분석·연구 업무 신호", signals),
            signals,
        )

    return TierAssessment(
        TIER_3,
        "이너젠 직접 컨설팅 또는 고객사 설비 지원 신호를 제목에서 확인하지 못함",
    )
