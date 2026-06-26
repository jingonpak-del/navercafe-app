from naver_cafe_strategy.naver.cafe_manuscript_generator import generate_cafe_manuscript, manuscript_to_json_dict
from naver_cafe_strategy.naver.manuscript_brief_builder import build_manuscript_brief
from naver_cafe_strategy.naver.morphological_analyzer import analyze_crawled_morphology
from naver_cafe_strategy.naver.search_content_crawler import CrawledContent
from naver_cafe_strategy.naver.search_intent_analyzer import infer_search_intent
from naver_cafe_strategy.naver.seo_content_analyzer import analyze_crawled_contents


def _row(rank: int, title: str, body: str, content_type: str = "cafe") -> CrawledContent:
    return CrawledContent(
        content_type=content_type,
        url=f"https://example.com/{rank}",
        title=title,
        body=body,
        rank=rank,
        ok=True,
    )


def test_infer_search_intent_prefers_cafe_question_type():
    rows = [
        _row(1, "요실금수술까지 해야 할까요", "요실금수술 알아보는데 비용이랑 회복이 궁금해요. 경험자 조언 부탁드려요."),
        _row(2, "요실금수술 비용 방법 총정리", "방법과 비용, 회복기간을 정리합니다.", content_type="blog"),
    ]
    morph = analyze_crawled_morphology(rows, keyword="요실금수술")

    profile = infer_search_intent(rows, morph)

    assert profile.selected_type == "question"
    assert profile.selected_type_label == "질문성"
    assert profile.cafe_type_counts["question"] == 1
    assert profile.question_score > 0


def test_build_brief_and_generate_manuscript_json_shape():
    rows = [
        _row(1, "소음순수술 궁금한데", "소음순수술 알아보는데 회복 통증 붓기 비용 상담 기준이 궁금해요."),
        _row(2, "소음순수술 회복기간 정리", "회복기간 비용 방법 주의사항 기준을 정리합니다.", content_type="blog"),
    ]
    morph = analyze_crawled_morphology(rows, keyword="소음순수술")
    intent = infer_search_intent(rows, morph)
    seo = analyze_crawled_contents(rows, keyword="소음순수술")

    brief = build_manuscript_brief(keyword="소음순수술", morph=morph, intent=intent, seo=seo)
    manuscript = generate_cafe_manuscript(brief)
    manuscript_json = manuscript_to_json_dict(manuscript)

    assert brief.keyword == "소음순수술"
    assert brief.selected_type_label in {"질문성", "후기성", "정보성"}
    assert brief.must_include_terms
    assert set(manuscript_json) == {"Title", "Content", "Comment"}
    assert "소음순수술" in manuscript_json["Title"] or "소음순수술" in manuscript_json["Content"]
    assert manuscript_json["Comment"]
    assert "\\t" in manuscript_json["Comment"]
