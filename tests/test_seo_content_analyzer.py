from naver_cafe_strategy.naver.search_content_crawler import CrawledContent
from naver_cafe_strategy.naver.seo_content_analyzer import (
    analyze_crawled_contents,
    build_llm_compact_context,
    compact_char_count,
    count_keyword,
    repeated_word_counts,
    tokenize,
)


def _row(rank: int, title: str, body: str, content_type: str = "blog") -> CrawledContent:
    return CrawledContent(
        content_type=content_type,
        url=f"https://example.com/{rank}",
        title=title,
        body=body,
        rank=rank,
        ok=True,
    )


def test_compact_char_count_excludes_spaces():
    assert compact_char_count("창원 흥신소 후기") == 7


def test_count_keyword_ignores_spaces():
    assert count_keyword("창원흥신소를 찾다가 창원 흥신소 후기를 봤습니다", "창원 흥신소") == 2


def test_tokenize_excludes_keyword_terms_and_stopwords():
    tokens = tokenize("창원 흥신소 증거수집 증거수집 후기 후기 그리고 합니다", keyword="창원 흥신소")

    assert "창원" not in tokens
    assert "흥신소" not in tokens
    assert "창원흥신소" not in tokens
    assert "그리고" not in tokens
    assert tokens.count("증거수집") == 2
    assert tokens.count("후기") == 2


def test_repeated_word_counts_returns_repeated_words_only():
    counts = repeated_word_counts("상담 상담 비용 비용 비용 창원 흥신소", keyword="창원 흥신소")

    assert counts == {"비용": 3, "상담": 2}


def test_analyze_crawled_contents_title_and_body_metrics():
    rows = [
        _row(
            1,
            "창원 흥신소 증거수집 후기 후기",
            "창원 흥신소 상담 후기입니다. 증거수집 상담 비용 안내. 창원흥신소 비용 상담.",
        ),
        _row(
            2,
            "창원흥신소 탐정 상담 비용",
            "창원흥신소 탐정 상담 절차입니다. 증거수집 절차 비용, 상담 후기 정리.",
            content_type="cafe",
        ),
    ]

    analysis = analyze_crawled_contents(rows, keyword="창원 흥신소")

    assert analysis.document_count == 2
    assert analysis.title_analyses[0].char_count == len("창원흥신소증거수집후기후기")
    assert analysis.title_analyses[0].keyword_count == 1
    assert analysis.title_analyses[0].repeated_words == {"후기": 2}
    assert analysis.body_analyses[0].keyword_count == 2
    assert analysis.body_analyses[1].keyword_count == 1
    assert analysis.common_words["상담"] >= 3
    assert analysis.common_words["비용"] >= 3
    assert analysis.body_analyses[0].common_word_counts["상담"] == 3
    assert analysis.recommendation.suggested_title_must_include_keyword is True


def test_build_llm_compact_context_excludes_raw_body_text():
    rows = [
        _row(1, "창원 흥신소 후기", "창원 흥신소 본문 원문입니다. 상담 상담 비용 비용."),
        _row(2, "창원흥신소 비용", "창원흥신소 다른 본문 원문입니다. 상담 비용 증거수집."),
    ]
    analysis = analyze_crawled_contents(rows, keyword="창원 흥신소")
    compact = build_llm_compact_context(analysis, top_n_words=5)

    compact_text = str(compact)
    assert "본문 원문입니다" not in compact_text
    assert compact["keyword"] == "창원 흥신소"
    assert compact["document_count"] == 2
    assert "recommendation" in compact
