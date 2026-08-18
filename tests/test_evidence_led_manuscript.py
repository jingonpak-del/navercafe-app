from naver_cafe_strategy.naver.evidence_led_manuscript import (
    ProductFacts,
    build_consumer_insight_brief,
    generate_disclosed_reply_draft,
)
from naver_cafe_strategy.naver.search_content_crawler import CrawledContent, build_search_url


def _row(rank: int, title: str, body: str, *, ok: bool = True) -> CrawledContent:
    return CrawledContent(
        content_type="cafe",
        url=f"https://cafe.naver.com/testcafe/{rank}",
        title=title,
        body=body,
        rank=rank,
        ok=ok,
    )


def test_search_url_supports_integrated_and_cafe_tab_pagination():
    integrated = build_search_url("무선 청소기", where="nexearch", start=11)
    cafe_tab = build_search_url("무선 청소기", where="article", start=21)

    assert "where=nexearch" in integrated
    assert "start=11" in integrated
    assert "where=article" in cafe_tab
    assert "start=21" in cafe_tab


def test_insight_brief_keeps_real_questions_and_reviews_promotional_posts():
    rows = [
        _row(1, "무선청소기 가격이랑 흡입력 어떤 기준으로 비교하세요?", "가격이 너무 차이나서 고민이에요. 흡입력, 배터리, 관리 편의성 중 뭘 먼저 봐야 할지 궁금합니다."),
        _row(2, "무선청소기 사용 후 관리가 불편한가요", "필터 청소와 먼지통 관리가 실제로 번거로운지 써보신 분들 의견이 궁금해요."),
        _row(3, "무선청소기 공동구매 최저가", "광고 체험단 공구 진행합니다. 구매링크 문의주세요."),
    ]

    posts, brief = build_consumer_insight_brief("무선청소기", rows)

    assert brief.corpus_size == 3
    assert brief.kept_count == 2
    assert brief.review_count == 1
    assert any(cluster.label == "비용·가격" for cluster in brief.issue_clusters)
    assert any(cluster.label == "비교·선택" for cluster in brief.issue_clusters)
    assert next(post for post in posts if post.rank == 3).status == "review"


def test_disclosed_draft_requires_facts_evidence_and_relationship_label():
    rows = [_row(1, "무선청소기 비교 기준", "가격과 관리 편의성, 사용 방법이 궁금합니다. 어떤 기준으로 비교할까요?")]
    _, brief = build_consumer_insight_brief("무선청소기", rows)
    product = ProductFacts(
        name="클린에어 X1",
        features=["교체형 HEPA 필터", "분리 세척 가능한 먼지통"],
        evidence=["클린에어 X1 공식 제품 사양서"],
        disclosure="[브랜드 담당자 안내]",
        restricted_claims=["알레르기 치료 효과"],
    )

    draft = generate_disclosed_reply_draft("무선청소기", brief.issue_clusters[0], product)

    assert draft.disclosure in draft.reply
    assert "클린에어 X1" in draft.reply
    assert "공식 제품 사양서" in draft.reply
    assert "실제 사용해봤" not in draft.reply
    assert draft.claim_map.eligible
