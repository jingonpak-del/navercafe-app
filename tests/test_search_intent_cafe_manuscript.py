from naver_cafe_strategy.naver.cafe_manuscript_generator import generate_cafe_manuscript, manuscript_to_json_dict
from naver_cafe_strategy.naver.llm_cafe_manuscript_generator import (
    LLMGenerationConfig,
    build_llm_prompt_bundle,
    generate_cafe_manuscript_with_llm,
    parse_llm_manuscript_response,
)
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


def _brief():
    rows = [
        _row(1, "소음순수술 궁금한데", "소음순수술 알아보는데 회복 통증 붓기 비용 상담 기준이 궁금해요."),
        _row(2, "소음순수술 회복기간 정리", "회복기간 비용 방법 주의사항 기준을 정리합니다.", content_type="blog"),
    ]
    morph = analyze_crawled_morphology(rows, keyword="소음순수술")
    intent = infer_search_intent(rows, morph)
    seo = analyze_crawled_contents(rows, keyword="소음순수술")
    return build_manuscript_brief(keyword="소음순수술", morph=morph, intent=intent, seo=seo)


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
    brief = _brief()
    manuscript = generate_cafe_manuscript(brief)
    manuscript_json = manuscript_to_json_dict(manuscript)

    assert brief.keyword == "소음순수술"
    assert brief.selected_type_label in {"질문성", "후기성", "정보성"}
    assert brief.must_include_terms
    assert set(manuscript_json) == {"Title", "Content", "Comment"}
    assert "소음순수술" in manuscript_json["Title"] or "소음순수술" in manuscript_json["Content"]
    assert manuscript_json["Comment"]
    assert "\\t" in manuscript_json["Comment"]


def test_llm_prompt_bundle_is_schema_bound_and_uses_brief():
    brief = _brief()

    bundle = build_llm_prompt_bundle(brief)

    assert "JSON 객체만 출력" in bundle.system
    assert '"Title"' in bundle.user
    assert "소음순수술" in bundle.user
    assert "must_include_terms" in bundle.user
    assert bundle.response_schema["required"] == ["Title", "Content", "Comment"]


def test_parse_llm_response_accepts_code_fenced_json():
    brief = _brief()
    raw = '''```json
{"Title": "소음순수술 알아볼 때 궁금했던 점", "Content": "처음에는 회복이 제일 궁금했어요.\n\n개인차가 있다 보니 상담 기준도 같이 봤습니다.", "Comment": "계정1|저도 회복 봤어요 \\t작성자[답글]|감사합니다"}
```'''

    manuscript = parse_llm_manuscript_response(raw, brief)

    assert manuscript.Title.startswith("소음순수술")
    assert manuscript.manuscript_type == brief.selected_type_label
    assert manuscript.brief_keyword == "소음순수술"


def test_generate_with_llm_uses_injected_chat_caller():
    brief = _brief()

    def fake_chat_caller(bundle, config):
        assert config.model == "test-model"
        assert "소음순수술" in bundle.user
        return (
            '{"Title":"소음순수술 알아보면서 헷갈렸던 부분",'
            '"Content":"검색해보니 회복이랑 상담 기준이 계속 보이더라고요.\\n\\n개인차가 있을 것 같아서 조심스럽게 알아보고 있어요.",'
            '"Comment":"계정1|상담 때 기준 물어보세요 \\\\t작성자[답글]|네 참고할게요 \\\\t계정2|개인차도 꼭 보세요"}'
        )

    manuscript = generate_cafe_manuscript_with_llm(
        brief,
        config=LLMGenerationConfig(model="test-model", api_key="test-key"),
        chat_caller=fake_chat_caller,
    )

    assert manuscript.Title == "소음순수술 알아보면서 헷갈렸던 부분"
    assert "개인차" in manuscript.Content
    assert "\\t" in manuscript.Comment
