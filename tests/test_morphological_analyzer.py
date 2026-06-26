from naver_cafe_strategy.naver.morphological_analyzer import analyze_text_morphology


def test_analyze_text_morphology_counts_pos_and_endings():
    text = "요즘 질성형 수술 알아보는데 회복이 궁금해요\n통증이나 붓기는 어느 정도일까요"

    analysis = analyze_text_morphology(text, keyword="질성형 수술", content_type="cafe", title="질문")

    assert analysis.keyword_count == 1
    assert analysis.sentence_count == 2
    assert analysis.eojeol_count > 0
    assert analysis.pos_group_counts["명사/체언"] >= 4
    assert "어미" in analysis.pos_group_counts
    assert any(ending in analysis.surface_ending_counts for ending in ["궁금해요", "일까요", "까요"])
    nouns = analysis.top_by_pos_group["명사/체언"]
    assert "회복" in nouns


def test_analyze_text_morphology_handles_empty_text():
    analysis = analyze_text_morphology("", keyword="테스트")

    assert analysis.char_count_without_spaces == 0
    assert analysis.sentence_count == 0
    assert analysis.eojeol_count == 0
    assert analysis.pos_group_counts == {}
