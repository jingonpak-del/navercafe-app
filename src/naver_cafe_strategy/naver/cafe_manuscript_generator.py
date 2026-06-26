# -*- coding: utf-8 -*-
"""Rule-based MVP Naver Cafe manuscript generator from a morphology/search-intent brief."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .manuscript_brief_builder import ManuscriptBrief


@dataclass(slots=True)
class GeneratedCafeManuscript:
    Title: str
    Content: str
    Comment: str
    manuscript_type: str
    brief_keyword: str


def _pick(items: list[str], default: str, limit: int = 4) -> list[str]:
    picked = [item for item in items if item][:limit]
    return picked or [default]


def _title_for(brief: ManuscriptBrief) -> str:
    keyword = brief.keyword
    terms = _pick(brief.must_include_terms, "기준", 3)
    if brief.selected_type == "review":
        return f"{keyword} 알아보고 나서 {terms[0]} 부분이 제일 궁금했어요"
    if brief.selected_type == "info":
        return f"{keyword} 알아볼 때 {terms[0]} 기준부터 봐야 할까요"
    return f"요즘 {keyword} 알아보는데 {terms[0]} 기준이 궁금해요"


def _question_content(brief: ManuscriptBrief) -> str:
    keyword = brief.keyword
    terms = _pick(brief.must_include_terms, "회복", 5)
    ref_terms = _pick(brief.blog_reference_terms, "방법", 3)
    return (
        f"요즘 {keyword} 때문에 검색을 좀 해보고 있는데 생각보다 봐야 할 게 많더라고요. "
        f"상위에 보이는 글들을 보면 {terms[0]}, {terms[1] if len(terms) > 1 else ref_terms[0]} 같은 얘기가 많이 나오고, "
        f"단순히 비용만 보고 판단하기는 어렵겠다는 생각이 들었어요.\n\n"
        f"블로그 쪽에서는 {ref_terms[0]} 관련 정보나 {ref_terms[1] if len(ref_terms) > 1 else terms[0]} 같은 내용이 정리돼 있긴 한데, "
        f"카페 글을 보면 실제로는 {terms[2] if len(terms) > 2 else '상담'}이나 {terms[3] if len(terms) > 3 else '관리'} 부분을 더 궁금해하는 것 같았어요. "
        f"저도 {keyword} 알아보는 입장이라 어떤 기준으로 먼저 비교해야 할지 헷갈립니다.\n\n"
        f"혹시 비슷하게 알아보셨던 분들은 {terms[0]}이나 {terms[-1]} 쪽을 어떻게 확인하셨나요? "
        f"광고 말고 실제로 체크해보면 좋을 부분 있으면 조언 부탁드려요."
    )


def _review_content(brief: ManuscriptBrief) -> str:
    keyword = brief.keyword
    terms = _pick(brief.must_include_terms, "회복", 5)
    ref_terms = _pick(brief.blog_reference_terms, "기준", 3)
    return (
        f"처음 {keyword} 알아볼 때는 정보가 너무 많아서 오히려 더 헷갈렸어요. "
        f"글들을 찾아보니 {terms[0]}이랑 {terms[1] if len(terms) > 1 else '비용'} 얘기가 반복해서 나오길래 저도 그 부분을 먼저 체크했습니다.\n\n"
        f"막상 알아보는 과정에서는 {ref_terms[0]} 관련 정리된 정보도 필요했지만, 카페 후기에서 보이는 실제 불편함이나 "
        f"{terms[2] if len(terms) > 2 else '회복'} 관련 얘기가 더 현실적으로 느껴지더라고요. 개인차는 있겠지만, "
        f"저는 결정 전에 상담 방식이랑 이후 관리 기준을 같이 보는 게 중요하다고 느꼈어요.\n\n"
        f"혹시 {keyword} 관련해서 경험 있으신 분들은 어떤 부분을 제일 먼저 확인하셨나요? "
        f"저처럼 고민하는 분들한테 도움 될 만한 기준이 있으면 같이 공유해주시면 좋겠어요."
    )


def _info_content(brief: ManuscriptBrief) -> str:
    keyword = brief.keyword
    terms = _pick(brief.must_include_terms, "기준", 5)
    ref_terms = _pick(brief.blog_reference_terms, "방법", 3)
    return (
        f"{keyword} 알아볼 때는 검색 결과마다 강조하는 부분이 조금씩 달라서 기준을 먼저 잡는 게 필요해 보였어요. "
        f"반복해서 나오는 표현을 보면 {terms[0]}, {terms[1] if len(terms) > 1 else '비용'}, {terms[2] if len(terms) > 2 else '상담'} 쪽을 많이 확인하는 것 같습니다.\n\n"
        f"블로그에서는 {ref_terms[0]} 관련 정보나 {ref_terms[1] if len(ref_terms) > 1 else '주의사항'} 같은 내용이 비교적 자세하고, "
        f"카페에서는 실제로 궁금했던 점이나 헷갈렸던 부분이 더 많이 보이더라고요. 그래서 {keyword} 관련해서는 정보만 보는 것보다 "
        f"내 상황에 맞는 기준을 따로 정리하는 게 좋을 것 같아요.\n\n"
        f"혹시 이 주제로 알아보신 분들은 어떤 기준을 먼저 보셨나요? {terms[-1]} 부분까지 같이 확인해야 하는지도 궁금합니다."
    )


def _comments_for(brief: ManuscriptBrief) -> str:
    terms = _pick(brief.must_include_terms, "기준", 4)
    if brief.selected_type == "review":
        return (
            f"계정1|저도 비슷하게 알아봤는데 {terms[0]} 부분은 사람마다 차이가 있더라고요. 너무 한쪽 후기만 보진 않는 게 좋았어요 \\t"
            f"작성자[답글]|맞아요 저도 그 부분이 제일 헷갈렸어요. 혹시 뭘 먼저 보셨어요? \\t"
            f"계정1[답글]|저는 {terms[1] if len(terms) > 1 else '상담'}이랑 이후 관리 기준을 같이 봤어요. 설명이 구체적인지 확인하는 게 도움 됐습니다 \\t"
        )
    return (
        f"계정1|처음 알아볼 때는 {terms[0]}만 보지 말고 여러 기준을 같이 보는 게 낫더라고요 \\t"
        f"작성자[답글]|혹시 어떤 기준을 먼저 보면 좋을까요? \\t"
        f"계정1[답글]|저는 {terms[1] if len(terms) > 1 else '상담'}이랑 {terms[2] if len(terms) > 2 else '후기'}를 같이 봤어요. 광고 느낌보다 실제 질문글을 참고하는 게 낫더라고요 \\t"
        f"계정2|댓글이나 후기에서 반복해서 나오는 불편한 점도 한번 체크해보세요. 생각보다 그런 부분이 현실적이에요 \\t"
    )


def generate_cafe_manuscript(brief: ManuscriptBrief) -> GeneratedCafeManuscript:
    if brief.selected_type == "review":
        content = _review_content(brief)
    elif brief.selected_type == "info":
        content = _info_content(brief)
    else:
        content = _question_content(brief)

    return GeneratedCafeManuscript(
        Title=_title_for(brief),
        Content=content,
        Comment=_comments_for(brief),
        manuscript_type=brief.selected_type_label,
        brief_keyword=brief.keyword,
    )


def manuscript_to_json_dict(manuscript: GeneratedCafeManuscript) -> dict[str, str]:
    # Keep downstream-compatible three-field JSON first; metadata can be stored in wrapper files.
    return {"Title": manuscript.Title, "Content": manuscript.Content, "Comment": manuscript.Comment}


def manuscript_to_json(manuscript: GeneratedCafeManuscript) -> str:
    return json.dumps(manuscript_to_json_dict(manuscript), ensure_ascii=False, indent=2)


def manuscript_with_metadata_to_dict(manuscript: GeneratedCafeManuscript) -> dict:
    return asdict(manuscript)
