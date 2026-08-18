# -*- coding: utf-8 -*-
"""Evidence-led Naver Cafe insight analysis and disclosed product-reply drafts.

This module deliberately separates public community evidence from approved product facts.
It does not generate undisclosed consumer-looking endorsements or fabricated experiences.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import re
from typing import Iterable

from .search_content_crawler import CrawledContent

_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_PROMOTION_PATTERNS = (
    "광고", "협찬", "체험단", "공구", "공동구매", "최저가", "구매링크", "문의주세요", "예약하세요",
    "추천하려고", "대만족", "기대 이상", "장점이 많은", "초강력 흡입력",
)
_QUESTION_PATTERNS = ("궁금", "어떻게", "어떤", "추천", "비교", "고민", "될까요", "인가요", "알려", "후기")
_BARRIER_PATTERNS = {
    "비용·가격": ("비용", "가격", "견적", "부담", "가성비"),
    "비교·선택": ("비교", "어떤", "선택", "기준", "추천"),
    "사용성·관리": ("사용", "관리", "편", "불편", "방법"),
    "안전·주의": ("안전", "주의", "부작용", "자극", "걱정", "불안"),
    "배송·구매": ("배송", "구매", "교환", "환불", "주문"),
}


@dataclass(slots=True)
class EvidencePost:
    url: str
    title: str
    body: str
    source: str = ""
    rank: int = 0
    status: str = "keep"
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IssueCluster:
    label: str
    post_count: int
    evidence_urls: list[str]
    excerpts: list[str]
    terms: list[str]


@dataclass(slots=True)
class ConsumerInsightBrief:
    keyword: str
    corpus_size: int
    kept_count: int
    review_count: int
    excluded_count: int
    issue_clusters: list[IssueCluster]
    common_terms: list[str]
    limitations: list[str]


@dataclass(slots=True)
class ProductFacts:
    name: str
    features: list[str]
    evidence: list[str]
    disclosure: str
    restricted_claims: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProductClaimMap:
    issue: str
    allowed_features: list[str]
    evidence: list[str]
    restricted_claims: list[str]
    eligible: bool


@dataclass(slots=True)
class DisclosedReplyDraft:
    title: str
    body: str
    reply: str
    disclosure: str
    issue: str
    claim_map: ProductClaimMap


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _excerpt(text: str, limit: int = 180) -> str:
    text = _compact(text)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def classify_evidence_post(row: CrawledContent) -> EvidencePost:
    """Classify a crawled Cafe post with transparent, reviewable reasons."""
    text = _compact(f"{row.title} {row.body}")
    reasons: list[str] = []
    if not row.ok or not row.body.strip():
        return EvidencePost(row.url, row.title, row.body, rank=row.rank, status="review", reasons=[row.error or "본문 접근 불가"])
    promo_hits = [pattern for pattern in _PROMOTION_PATTERNS if pattern in text]
    question_hits = [pattern for pattern in _QUESTION_PATTERNS if pattern in text]
    if len(text) < 40:
        reasons.append("본문이 짧아 소비자 맥락 확인이 어려움")
    if promo_hits:
        reasons.append(f"홍보/관계 표기 또는 판매 표현: {', '.join(promo_hits)}")
    if question_hits:
        reasons.append(f"질문·고민 신호: {', '.join(question_hits[:3])}")
    if promo_hits:
        status = "review"
    elif len(text) < 40:
        status = "review"
    else:
        status = "keep"
        if not question_hits:
            reasons.append("질문 신호는 약하지만 본문 맥락은 분석 가능")
    return EvidencePost(row.url, row.title, row.body, rank=row.rank, status=status, reasons=reasons)


def build_consumer_insight_brief(keyword: str, rows: Iterable[CrawledContent]) -> tuple[list[EvidencePost], ConsumerInsightBrief]:
    posts = [classify_evidence_post(row) for row in rows if row.content_type == "cafe"]
    kept = [post for post in posts if post.status == "keep"]
    reviewed = [post for post in posts if post.status == "review"]
    clusters: list[IssueCluster] = []
    for label, patterns in _BARRIER_PATTERNS.items():
        matched = [post for post in kept if any(pattern in f"{post.title} {post.body}" for pattern in patterns)]
        if not matched:
            continue
        terms = [pattern for pattern in patterns if any(pattern in f"{post.title} {post.body}" for post in matched)]
        clusters.append(IssueCluster(
            label=label,
            post_count=len(matched),
            evidence_urls=[post.url for post in matched[:5]],
            excerpts=[_excerpt(f"{post.title} — {post.body}") for post in matched[:3]],
            terms=terms,
        ))
    token_counts = Counter(token.lower() for post in kept for token in _TOKEN_RE.findall(f"{post.title} {post.body}"))
    ignore = {token.lower() for token in _TOKEN_RE.findall(keyword)}
    common_terms = [term for term, _ in token_counts.most_common(20) if term not in ignore][:12]
    brief = ConsumerInsightBrief(
        keyword=keyword,
        corpus_size=len(posts),
        kept_count=len(kept),
        review_count=len(reviewed),
        excluded_count=0,
        issue_clusters=sorted(clusters, key=lambda cluster: (-cluster.post_count, cluster.label)),
        common_terms=common_terms,
        limitations=[
            "검색에 노출되고 공개적으로 접근 가능한 카페 글만 분석했습니다.",
            "글 수와 반복 표현은 검색 표본의 신호이며 전체 소비자 집단의 비율을 뜻하지 않습니다.",
            "review 상태 글은 광고성 여부를 자동으로 단정하지 않았으며 사람 검토가 필요합니다.",
        ],
    )
    return posts, brief


def map_product_to_issue(issue: IssueCluster, product: ProductFacts) -> ProductClaimMap:
    features = [feature for feature in product.features if feature.strip()]
    evidence = [item for item in product.evidence if item.strip()]
    return ProductClaimMap(
        issue=issue.label,
        allowed_features=features,
        evidence=evidence,
        restricted_claims=list(product.restricted_claims),
        eligible=bool(features and evidence and product.disclosure.strip()),
    )


def generate_disclosed_reply_draft(keyword: str, issue: IssueCluster, product: ProductFacts) -> DisclosedReplyDraft:
    """Generate a transparent information-first discussion prompt and brand/partner reply.

    The body is deliberately product-neutral. The reply carries the disclosure and only
    repeats supplied product facts; it makes no invented testimonial or performance claim.
    """
    claim_map = map_product_to_issue(issue, product)
    if not claim_map.eligible:
        raise ValueError("제품 특징, 근거, 관계 표기 문구가 모두 있어야 공개 답변 초안을 만들 수 있습니다.")
    primary_term = issue.terms[0] if issue.terms else "확인 기준"
    title = f"{keyword} 알아볼 때 {issue.label} 관련 기준은 어떻게 확인하시나요?"
    body = (
        f"{keyword} 관련 카페 글을 살펴보니 {issue.label} 관련 이야기가 반복해서 보였습니다. "
        f"특히 {primary_term}처럼 실제 선택 전에 확인할 기준을 궁금해하는 경우가 많았어요.\n\n"
        "제품 추천을 받기보다 먼저 내 상황에 필요한 조건, 확인 가능한 정보, 구매 전 체크할 점을 정리해보려 합니다. "
        "비슷하게 알아보셨다면 어떤 기준이 실제로 도움이 됐는지 경험 범위에서 공유 부탁드립니다."
    )
    feature_text = ", ".join(product.features[:3])
    evidence_text = product.evidence[0]
    reply = (
        f"{product.disclosure}\n"
        f"{issue.label} 관련 기준을 확인하시는 분께 참고가 될 수 있어 안내드립니다. {product.name}의 확인 가능한 특징은 {feature_text}입니다. "
        f"근거/확인 자료: {evidence_text}. 개인 상황과 사용 조건에 따라 적합성이 달라질 수 있으니, 구매 전 제품 상세 정보와 제한 사항을 함께 확인해 주세요."
    )
    return DisclosedReplyDraft(title, body, reply, product.disclosure, issue.label, claim_map)


def to_dict(value):
    return asdict(value)
