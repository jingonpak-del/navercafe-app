# -*- coding: utf-8 -*-
"""Infer Naver search intent and best Naver Cafe manuscript type from morpheme analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from .morphological_analyzer import MorphDocumentAnalysis, SearchMorphAnalysis
from .search_content_crawler import CrawledContent

QUESTION_TERMS = {
    "궁금",
    "고민",
    "어떻게",
    "어디",
    "언제",
    "얼마",
    "비용",
    "기준",
    "조언",
    "추천",
    "분들",
    "괜찮",
    "할까요",
    "될까요",
    "있을까요",
    "인가요",
    "나요",
    "까요",
    "부탁",
}
REVIEW_TERMS = {
    "후기",
    "경험",
    "직접",
    "받아",
    "해봤",
    "했어요",
    "지났",
    "개월",
    "통증",
    "붓기",
    "회복",
    "느낌",
    "불편",
    "만족",
    "전후",
    "생각보다",
    "더라고요",
}
INFO_TERMS = {
    "방법",
    "종류",
    "비용",
    "가격",
    "회복기간",
    "주의사항",
    "비교",
    "차이",
    "총정리",
    "선택법",
    "확인",
    "기준",
    "정리",
    "필요",
    "가능",
    "합니다",
    "입니다",
    "됩니다",
}

TYPE_LABELS = {
    "question": "질문성",
    "review": "후기성",
    "info": "정보성",
}


@dataclass(slots=True)
class DocumentIntentScore:
    rank: int
    content_type: str
    title: str
    url: str
    question_score: float
    review_score: float
    info_score: float
    selected_type: str
    evidence: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class SearchIntentProfile:
    keyword: str
    selected_type: str
    selected_type_label: str
    question_score: float
    review_score: float
    info_score: float
    cafe_type_counts: dict[str, int]
    document_scores: list[DocumentIntentScore]
    search_intent_summary: str
    reason: str
    source_weight_note: str


def _contains_any(text: str, terms: set[str]) -> list[str]:
    return [term for term in terms if term in text]


def _clean_term(term: str) -> str:
    return "".join(ch for ch in (term or "").strip() if ch.isalnum() or "가" <= ch <= "힣")


def _summary_terms(words: dict[str, int], *, limit: int = 8) -> list[str]:
    terms: list[str] = []
    for word in words:
        clean = _clean_term(word)
        if len(clean) < 2 or clean in terms:
            continue
        terms.append(clean)
        if len(terms) >= limit:
            break
    return terms


def _score_document(row: CrawledContent, analysis: MorphDocumentAnalysis | None = None) -> DocumentIntentScore:
    text = " ".join([row.title or "", row.search_title or "", row.search_snippet or "", row.body or ""])
    endings_text = " ".join((analysis.surface_ending_counts.keys() if analysis else []))
    full_text = f"{text} {endings_text}"

    question_hits = _contains_any(full_text, QUESTION_TERMS)
    review_hits = _contains_any(full_text, REVIEW_TERMS)
    info_hits = _contains_any(full_text, INFO_TERMS)

    question_score = len(question_hits) * 1.0
    review_score = len(review_hits) * 1.0
    info_score = len(info_hits) * 1.0

    if row.content_type == "cafe":
        # Cafe language is the primary signal for the final Cafe manuscript type.
        question_score *= 1.25
        review_score *= 1.25
        info_score *= 1.1
    else:
        # Blog text is useful for information axes, but less decisive for Cafe tone.
        info_score *= 1.15
        question_score *= 0.85
        review_score *= 0.85

    if row.title:
        title_hits_q = _contains_any(row.title, QUESTION_TERMS)
        title_hits_r = _contains_any(row.title, REVIEW_TERMS)
        title_hits_i = _contains_any(row.title, INFO_TERMS)
        question_score += len(title_hits_q) * 1.5
        review_score += len(title_hits_r) * 1.5
        info_score += len(title_hits_i) * 1.25

    scores = {"question": question_score, "review": review_score, "info": info_score}
    selected = max(scores, key=scores.get)
    if scores[selected] == 0:
        selected = "question"

    return DocumentIntentScore(
        rank=row.rank,
        content_type=row.content_type,
        title=row.title,
        url=row.url,
        question_score=round(question_score, 2),
        review_score=round(review_score, 2),
        info_score=round(info_score, 2),
        selected_type=selected,
        evidence={
            "question": question_hits[:10],
            "review": review_hits[:10],
            "info": info_hits[:10],
        },
    )


def infer_search_intent(rows: list[CrawledContent], morph: SearchMorphAnalysis) -> SearchIntentProfile:
    docs = [row for row in rows if row.ok and row.body]
    analysis_by_key = {(item.rank, item.url): item for item in morph.analyses}
    scores = [_score_document(row, analysis_by_key.get((row.rank, row.url))) for row in docs]

    cafe_scores = [score for score in scores if score.content_type == "cafe"]
    cafe_type_counts = Counter(score.selected_type for score in cafe_scores)

    weighted = Counter()
    for score in scores:
        source_weight = 1.35 if score.content_type == "cafe" else 0.75
        weighted["question"] += score.question_score * source_weight
        weighted["review"] += score.review_score * source_weight
        weighted["info"] += score.info_score * source_weight

    if cafe_scores:
        selected = cafe_type_counts.most_common(1)[0][0]
        # If type distribution is tied, use weighted score.
        top_count = cafe_type_counts[selected]
        tied = [kind for kind, count in cafe_type_counts.items() if count == top_count]
        if len(tied) > 1:
            selected = max(tied, key=lambda kind: weighted[kind])
    else:
        selected = max(("question", "review", "info"), key=lambda kind: weighted[kind]) if scores else "question"

    if weighted[selected] == 0:
        selected = "question"

    top_words = morph.global_top_by_pos_group.get("명사/체언", {})
    top_word_list = _summary_terms(top_words, limit=8)
    if selected == "question":
        summary = f"'{morph.keyword}' 검색자는 결정 전 단계에서 기준·경험·비용을 확인하려는 질문형 의도가 강합니다."
    elif selected == "review":
        summary = f"'{morph.keyword}' 검색자는 실제 경험담과 진행 후 변화·회복 과정을 확인하려는 후기형 의도가 강합니다."
    else:
        summary = f"'{morph.keyword}' 검색자는 방법·비용·주의사항을 정리해 비교하려는 정보 탐색 의도가 강합니다."

    if top_word_list:
        summary += f" 주요 반복 명사는 {', '.join(top_word_list)}입니다."

    if cafe_scores:
        reason = "카페 노출글의 유형 분포를 우선 적용했습니다. "
        reason += ", ".join(f"{TYPE_LABELS[k]} {v}건" for k, v in cafe_type_counts.items())
    else:
        reason = "분석 가능한 카페 글이 없어 블로그/전체 문서의 형태소와 제목 신호로 기본 타입을 정했습니다."

    return SearchIntentProfile(
        keyword=morph.keyword,
        selected_type=selected,
        selected_type_label=TYPE_LABELS[selected],
        question_score=round(weighted["question"], 2),
        review_score=round(weighted["review"], 2),
        info_score=round(weighted["info"], 2),
        cafe_type_counts=dict(cafe_type_counts),
        document_scores=scores,
        search_intent_summary=summary,
        reason=reason,
        source_weight_note="최종 원고 타입은 카페 글 신호를 우선하고, 블로그는 정보 보강 신호로 낮은 가중치를 적용했습니다.",
    )


def intent_profile_to_dict(profile: SearchIntentProfile) -> dict:
    return asdict(profile)
