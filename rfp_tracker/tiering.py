from __future__ import annotations

"""Conservative, title-led fit assessment for Innergen's climate workflow.

Tier 3 remains an internal exclusion value so historical source rows and manual
decisions can be preserved. Only Tier 1/2 are reader-facing opportunities.
"""

import re
from dataclasses import dataclass
from typing import Iterable


TIER_1 = "tier_1"
TIER_2 = "tier_2"
TIER_3 = "tier_3"
UNCLASSIFIED = "unclassified"
VALID_BUSINESS_TIERS = {TIER_1, TIER_2, TIER_3, UNCLASSIFIED}
VISIBLE_BUSINESS_TIERS = frozenset({TIER_1, TIER_2})

TIER_LABELS = {
    TIER_1: "Tier 1 · 이너젠 직접 컨설팅 검토",
    TIER_2: "Tier 2 · 고객사 설비·금융지원 추천",
    TIER_3: "제외 · 업무범위 밖",
    UNCLASSIFIED: "미분류 · 원문 확인 필요",
}

TIER_SHORT_LABELS = {
    TIER_1: "Tier 1",
    TIER_2: "Tier 2",
    TIER_3: "제외",
    UNCLASSIFIED: "미분류",
}


@dataclass(frozen=True, slots=True)
class TierAssessment:
    tier: str
    reason: str
    matched_signals: tuple[str, ...] = ()


# A ministry/buyer name containing "기후" and a generic "용역" category are
# not evidence of fit. These signals are evaluated against the notice title.
NON_CONSULTING_SIGNALS = (
    "투자유치", "펀드", "ir 행사", "행사", "포럼", "세미나", "컨퍼런스",
    "콘퍼런스", "박람회", "전시회", "캠페인", "홍보", "영상", "촬영",
    "교육", "연수", "공모전", "시상", "조직문화", "국민만족도",
    "메타버스", "iot센서", "센서 구매", "시스템 기능개선", "서버 구매",
)

SCIENCE_ONLY_SIGNALS = (
    "순수과학", "기초과학", "기초 연구", "실험실", "시료", "시약",
    "분석장비", "유전자", "미생물", "핵연료", "파우더", "소재 실험",
)

TIER_1_DOMAINS = (
    "온실가스", "배출권거래제", "배출권 거래제", "배출권", "k-ets",
    "ets", "외부사업", "국제감축", "국제 감축", "itmo", "감축실적",
    "감축량", "상쇄배출권", "verra", "gold standard", "puro earth",
    "scope 1", "scope 2", "scope 3", "scope1", "scope2", "scope3",
    "스코프1", "스코프2", "스코프3", "배출량 산정", "배출계수",
    "목표관리제", "mrv", "csrd", "cbam", "issb", "kssb", "cdp",
    "탄소중립", "넷제로", "net zero", "탈탄소", "sbti", "pas 2060",
    "iso 14064", "iso14064", "iso 14068", "iso14068",
    "기후변화 산업", "산업 전환 시나리오",
    "re100", "k-re100", "ppa", "vppa", "i-rec", "rec", "재생에너지 조달",
)

TIER_1_WORK = (
    "컨설팅", "산정", "평가", "검증", "방법론", "발급", "인벤토리",
    "명세서", "모니터링계획", "모니터링 계획", "공시", "보고", "전략",
    "시나리오", "로드맵", "이행계획", "전환계획", "할당신청",
    "과부족 분석", "한계저감비용", "재무적 영향", "거버넌스",
    "조달 계획", "전력사용 패턴", "포트폴리오", "인증", "기획 연구",
    "기획연구", "사전기획", "타당성조사", "영향 및 대응연구",
    "이행점검", "관리체계", "제도 개선", "운영 지원", "운영지원",
    "계획 수립", "진단", "민감도", "중개", "확보 지원", "검토",
)

# Research that designs a GHG reduction programme is advisory; technology
# development, lab testing or purchases on their own are not.
PLANNING_RESEARCH = ("기획 연구", "기획연구", "사전기획", "사업 기획")
SCIENCE_PROJECT = ("기술개발", "실증", "시험", "r&d")

TIER_2_DOMAINS = (
    "탄소중립", "온실가스", "저탄소", "탈탄소", "탄소감축",
    "탄소 감축", "재생에너지", "신재생에너지", "에너지효율",
    "환경설비", "환경 설비", "친환경 설비", "오염저감설비", "오염 저감 설비",
)
TIER_2_SUPPORT = (
    "지원사업", "지원 사업", "보조금", "지원금", "융자", "금리",
    "이차보전", "이자지원", "이자 지원", "자금지원", "자금 지원",
    "설비 지원", "설비지원", "설치 지원", "도입 지원", "투자 지원",
)
TIER_2_EQUIPMENT_OR_FINANCE = (
    "설비", "시설", "장비", "설치", "도입", "설비투자", "효율화",
    "에너지전환", "공기압축기", "인버터", "히트펌프", "모터",
    "보일러", "자금", "융자", "금리", "이차보전", "이자지원",
    "이자 지원", "재생에너지", "신재생에너지",
)
TIER_2_APPLICATION = (
    "모집", "신청", "공모", "접수", "참여기업", "지원대상",
    "사업공고", "사업 공고", "자금 신청",
)
GOODS_PROCUREMENT = (
    "구매", "납품", "물품", "견적", "시공", "발주", "공기압축기",
    "컴프레셔", "인버터", "히트펌프", "보일러", "모터", "fems",
    "사출성형기", "가공기", "레이저", "건조로", "쇼트기",
)
PRIVATE_BUYER = ("주식회사", "유한회사", "(주)", "㈜", "co., ltd", "corp.")


def tier_label(tier: str) -> str:
    return TIER_LABELS.get(tier, TIER_LABELS[UNCLASSIFIED])


def tier_short_label(tier: str) -> str:
    return TIER_SHORT_LABELS.get(tier, TIER_SHORT_LABELS[UNCLASSIFIED])


def _signals(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    matched: list[str] = []
    for term in terms:
        needle = term.casefold().strip()
        if needle.isascii() and any(character.isalpha() for character in needle):
            pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                matched.append(term)
        elif needle in text:
            matched.append(term)
    return tuple(matched)


def _reason(prefix: str, signals: Iterable[str]) -> str:
    visible = list(dict.fromkeys(signals))[:3]
    return f"{prefix} ({', '.join(visible)})" if visible else prefix


def assess_innergen_tier(
    title: str,
    *,
    category: str = "",
    matched_keywords: Iterable[str] | None = None,
    buyer: str = "",
    procurement_method: str = "",
) -> TierAssessment:
    """Classify title evidence; buyer/procurement facts can reject supplier bids."""
    del category, matched_keywords
    text = " ".join((title or "").casefold().split())
    if not text:
        return TierAssessment(TIER_3, "제외: 공고 제목에서 사업범위를 확인할 수 없음")

    unrelated = _signals(text, NON_CONSULTING_SIGNALS)
    if unrelated:
        return TierAssessment(TIER_3, _reason("제외: 행사·홍보·IT 구매 등 비대상", unrelated), unrelated)

    domain = _signals(text, TIER_1_DOMAINS)
    support_domain = _signals(text, TIER_2_DOMAINS)
    support = _signals(text, TIER_2_SUPPORT)
    equipment = _signals(text, TIER_2_EQUIPMENT_OR_FINANCE)
    if support_domain and support and equipment:
        accepting_applications = bool(_signals(text, TIER_2_APPLICATION))
        supplier_purchase = bool(_signals(text, GOODS_PROCUREMENT))
        private_supplier_bid = bool(procurement_method.strip()) and bool(
            _signals(buyer.casefold(), PRIVATE_BUYER)
        )
        if not accepting_applications and (supplier_purchase or private_supplier_bid):
            return TierAssessment(
                TIER_3,
                "제외: 지원사업을 활용한 개별 기업의 물품·설비 구매입찰로 신청 공고가 아님",
            )
        signals = tuple(dict.fromkeys((*support_domain, *support, *equipment)))
        return TierAssessment(TIER_2, _reason("고객사 설비·금융지원 사업", signals), signals)

    if not domain:
        return TierAssessment(TIER_3, "제외: 이너젠 기후·온실가스·배출권 업무영역 신호 없음")

    science = _signals(text, SCIENCE_ONLY_SIGNALS)
    if science:
        return TierAssessment(TIER_3, _reason("제외: 실험·기초과학 중심", science), science)
    if _signals(text, SCIENCE_PROJECT) and not _signals(text, PLANNING_RESEARCH):
        return TierAssessment(TIER_3, "제외: 기술개발·실증·시험 자체는 컨설팅 과업이 아님")

    work = _signals(text, TIER_1_WORK)
    if work:
        signals = tuple(dict.fromkeys((*domain, *work)))
        return TierAssessment(TIER_1, _reason("이너젠 직접 수행 컨설팅·기획 과업", signals), signals)

    return TierAssessment(TIER_3, "제외: 직접 컨설팅 과업 또는 고객사 지원 근거 없음")
