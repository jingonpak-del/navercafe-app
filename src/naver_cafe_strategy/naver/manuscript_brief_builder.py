# -*- coding: utf-8 -*-
"""Build a compact manuscript brief from Naver search intent + morphology analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .morphological_analyzer import SearchMorphAnalysis
from .search_intent_analyzer import SearchIntentProfile
from .seo_content_analyzer import SearchSEOAnalysis


@dataclass(slots=True)
class ManuscriptBrief:
    keyword: str
    selected_type: str
    selected_type_label: str
    search_intent: str
    reason: str
    must_include_terms: list[str]
    blog_reference_terms: list[str]
    avoid_overuse_terms: list[str]
    recommended_endings: list[str]
    content_structure: list[str]
    tone_guidelines: list[str]
    safety_guidelines: list[str] = field(default_factory=list)


_TYPE_STRUCTURES = {
    "question": ["검색/고민 계기", "상위글에서 확인한 비교 기준", "본인 상황과 우려", "경험자에게 질문"],
    "review": ["알아보게 된 배경", "진행 전 고민", "진행/상담 과정에서 느낀 점", "회복·불편·주의점", "비슷한 고민자에게 남기는 말"],
    "info": ["키워드 관련 고민 소개", "사람들이 많이 확인하는 기준", "비용·방법·회복 등 비교 요소", "상담/결정 전 체크 포인트", "경험자 의견 요청"],
}

_TYPE_ENDINGS = {
    "question": ["궁금해요", "같아요", "더라고요", "할까요", "부탁드려요"],
    "review": ["했어요", "더라고요", "느꼈어요", "같아요", "좋겠어요"],
    "info": ["라고 해요", "볼 수 있어요", "확인하는 게 좋겠더라고요", "나눠보면 좋을 것 같아요"],
}

_TYPE_TONES = {
    "question": ["결정 전 고민을 드러내는 자연스러운 카페 질문글", "검색한 흔적은 넣되 광고처럼 단정하지 않기", "마지막은 경험자 댓글 요청으로 마무리"],
    "review": ["개인 경험처럼 보이되 과장·보장 표현 금지", "좋은 점과 조심할 점을 함께 언급", "의료/시술 주제는 개인차를 분명히 남기기"],
    "info": ["블로그식 딱딱한 설명보다 카페 공유글 톤 유지", "기준을 정리하되 경험자 의견을 묻는 흐름 포함", "체크리스트 나열을 사람 말투로 풀기"],
}

SAFETY_GUIDELINES = [
    "특정 병원·업체를 직접 추천하거나 유도하지 않는다.",
    "의료/시술·법률·금융 등 민감 주제는 효과·결과를 보장하지 않는다.",
    "후기성 원고라도 개인차가 있다는 표현을 남긴다.",
    "키워드는 유지하되 기계적 반복은 피하고 대체 표현으로 분산한다.",
]


def _clean_term(term: str) -> str:
    return "".join(ch for ch in (term or "").strip() if ch.isalnum() or "가" <= ch <= "힣")


def _is_useful_term(term: str, keyword: str = "") -> bool:
    term = _clean_term(term)
    if len(term) < 2:
        return False
    if term.isdigit():
        return False
    if keyword and term == keyword.replace(" ", ""):
        return False
    return True


def _top_terms(morph: SearchMorphAnalysis, content_type: str | None = None, *, limit: int = 12) -> list[str]:
    if content_type and content_type in morph.by_content_type:
        top = morph.by_content_type[content_type].get("top_nouns", {})
        return [_clean_term(term) for term in top.keys() if _is_useful_term(term, morph.keyword)][:limit]
    nouns = morph.global_top_by_pos_group.get("명사/체언", {})
    return [_clean_term(term) for term in nouns.keys() if _is_useful_term(term, morph.keyword)][:limit]


def _avoid_terms(keyword: str, seo: SearchSEOAnalysis | None) -> list[str]:
    terms = [keyword]
    if seo:
        for word, count in seo.body_global_repeated_words.items():
            if count >= max(5, seo.document_count) and word not in terms:
                terms.append(word)
            if len(terms) >= 6:
                break
    return terms


def build_manuscript_brief(
    *,
    keyword: str,
    morph: SearchMorphAnalysis,
    intent: SearchIntentProfile,
    seo: SearchSEOAnalysis | None = None,
) -> ManuscriptBrief:
    cafe_terms = _top_terms(morph, "cafe", limit=14)
    blog_terms = _top_terms(morph, "blog", limit=10)
    global_terms = _top_terms(morph, None, limit=14)

    must_include: list[str] = []
    for term in [*cafe_terms, *global_terms]:
        if term not in must_include and term not in keyword.replace(" ", "") and len(term) >= 2:
            must_include.append(term)
        if len(must_include) >= 10:
            break

    return ManuscriptBrief(
        keyword=keyword,
        selected_type=intent.selected_type,
        selected_type_label=intent.selected_type_label,
        search_intent=intent.search_intent_summary,
        reason=intent.reason,
        must_include_terms=must_include,
        blog_reference_terms=[term for term in blog_terms if term not in must_include][:8],
        avoid_overuse_terms=_avoid_terms(keyword, seo),
        recommended_endings=_TYPE_ENDINGS.get(intent.selected_type, _TYPE_ENDINGS["question"]),
        content_structure=_TYPE_STRUCTURES.get(intent.selected_type, _TYPE_STRUCTURES["question"]),
        tone_guidelines=_TYPE_TONES.get(intent.selected_type, _TYPE_TONES["question"]),
        safety_guidelines=SAFETY_GUIDELINES,
    )


def brief_to_dict(brief: ManuscriptBrief) -> dict:
    return asdict(brief)


def build_brief_markdown(brief: ManuscriptBrief) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- 없음"

    return f"""# 네이버 검색 의도 기반 원고 브리프

## 키워드
- {brief.keyword}

## 권장 원고 타입
- {brief.selected_type_label}

## 검색 의도
{brief.search_intent}

## 타입 결정 사유
{brief.reason}

## 반드시 반영할 형태소/표현
{bullets(brief.must_include_terms)}

## 블로그 참고 표현
{bullets(brief.blog_reference_terms)}

## 과반복 주의 표현
{bullets(brief.avoid_overuse_terms)}

## 권장 종결 어미
{bullets(brief.recommended_endings)}

## 권장 구성
{bullets(brief.content_structure)}

## 톤 가이드
{bullets(brief.tone_guidelines)}

## 안전/품질 가이드
{bullets(brief.safety_guidelines)}
"""
