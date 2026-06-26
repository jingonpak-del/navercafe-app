# -*- coding: utf-8 -*-
"""Korean morpheme/POS analysis for Naver cafe/blog manuscript workflows."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from statistics import mean
from typing import Iterable

from kiwipiepy import Kiwi

from .search_content_crawler import CrawledContent
from .seo_content_analyzer import count_keyword

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？요다까죠함음네요]\s)|[\n]+")
_EOJEOL_RE = re.compile(r"\S+")
_SURFACE_ENDINGS = (
    "더라고요",
    "더라구요",
    "같아요",
    "싶어요",
    "궁금해요",
    "부탁드려요",
    "부탁드립니다",
    "할까요",
    "일까요",
    "있을까요",
    "될까요",
    "인가요",
    "나요",
    "까요",
    "어요",
    "아요",
    "예요",
    "이에요",
    "입니다",
    "합니다",
    "했습니다",
    "됩니다",
    "같습니다",
)

POS_GROUPS: dict[str, set[str]] = {
    "명사/체언": {"NNG", "NNP", "NNB", "NR", "NP", "XR", "SL", "SH", "SN"},
    "동사/보조동사": {"VV", "VX", "XSV"},
    "형용사": {"VA", "XSA"},
    "부사": {"MAG", "MAJ"},
    "관형사": {"MM"},
    "지정사/용언": {"VCP", "VCN"},
}

POS_GROUP_DESCRIPTIONS = {
    "명사/체언": "주제·대상·검색 의도 단어입니다.",
    "동사/보조동사": "행동·경험·진행 흐름을 만듭니다.",
    "형용사": "감정·상태·평가 뉘앙스를 만듭니다.",
    "부사": "강도·빈도·말투를 조절합니다.",
    "조사": "문장 연결과 관계 표시가 많은지 보여줍니다.",
    "어미": "문장 종결과 질문/후기/정보 톤을 보여줍니다.",
    "관형사": "수식 구조와 설명 밀도를 보여줍니다.",
    "지정사/용언": "정의·판단형 문장 비중을 보여줍니다.",
    "기타": "분류 밖 형태소입니다.",
}

_KIWI: Kiwi | None = None


@dataclass(slots=True)
class TokenCount:
    surface: str
    count: int
    pos: str = ""


@dataclass(slots=True)
class SentenceEndingCount:
    ending: str
    count: int
    interpretation: str = ""


@dataclass(slots=True)
class MorphDocumentAnalysis:
    rank: int
    content_type: str
    url: str
    title: str
    char_count_with_spaces: int
    char_count_without_spaces: int
    paragraph_count: int
    sentence_count: int
    eojeol_count: int
    avg_eojeol_per_sentence: float
    min_eojeol_per_sentence: int
    max_eojeol_per_sentence: int
    keyword_count: int
    pos_group_counts: dict[str, int]
    pos_detail_counts: dict[str, int]
    top_by_pos_group: dict[str, dict[str, int]]
    final_eojeol_counts: dict[str, int]
    final_ending_counts: dict[str, int]
    surface_ending_counts: dict[str, int]


@dataclass(slots=True)
class SearchMorphAnalysis:
    keyword: str
    document_count: int
    analyses: list[MorphDocumentAnalysis]
    by_content_type: dict[str, dict[str, object]]
    global_pos_group_counts: dict[str, int]
    global_top_by_pos_group: dict[str, dict[str, int]]
    common_terms_by_content_type: dict[str, dict[str, int]]


def _kiwi() -> Kiwi:
    global _KIWI
    if _KIWI is None:
        _KIWI = Kiwi()
    return _KIWI


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def compact_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def split_sentences(text: str) -> list[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines
    parts = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|(?<=요)\s+|(?<=다)\s+", text or "") if part.strip()]
    return parts or ([normalize_text(text)] if normalize_text(text) else [])


def _pos_group(tag: str) -> str:
    if tag.startswith("J"):
        return "조사"
    if tag.startswith("E"):
        return "어미"
    for group, tags in POS_GROUPS.items():
        if tag in tags:
            return group
    return "기타"


def _meaningful_surface(surface: str, tag: str) -> bool:
    if len(surface.strip()) == 0:
        return False
    if tag.startswith(("S", "W")) and tag not in {"SL", "SH", "SN"}:
        return False
    return True


def _final_eojeol(sentence: str) -> str:
    cleaned = re.sub(r"[\s\"'“”‘’()\[\]{}<>]+$", "", sentence.strip())
    cleaned = re.sub(r"[.!?,。！？…~ㅠㅎㅋ]+$", "", cleaned)
    tokens = _EOJEOL_RE.findall(cleaned)
    return tokens[-1] if tokens else ""


def _ending_interpretation(ending: str) -> str:
    if ending.endswith(("까요", "나요", "일까요", "있을까요", "할까요")):
        return "질문·조언 요청 느낌"
    if ending.endswith(("더라고요", "었어요", "았어요", "했어요")):
        return "경험/후기 느낌"
    if ending.endswith(("입니다", "합니다", "됩니다")):
        return "정보형·설명형 느낌"
    if ending.endswith(("같아요", "싶어요")):
        return "완곡하고 자연스러운 커뮤니티 느낌"
    return "일반 종결 표현"


def _surface_ending(sentence: str) -> str:
    final = _final_eojeol(sentence)
    for ending in _SURFACE_ENDINGS:
        if final.endswith(ending):
            return ending
    return final


def _tokenize(text: str):
    return _kiwi().tokenize(text or "")


def analyze_text_morphology(
    text: str,
    *,
    keyword: str = "",
    rank: int = 0,
    content_type: str = "manuscript",
    url: str = "",
    title: str = "",
    top_n: int = 30,
) -> MorphDocumentAnalysis:
    """Analyze one Korean manuscript/body with Kiwi and sentence-final patterns."""

    text = text or ""
    sentences = split_sentences(text)
    eojeol_lengths = [len(_EOJEOL_RE.findall(sentence)) for sentence in sentences if sentence.strip()]
    tokens = [token for token in _tokenize(text) if _meaningful_surface(token.form, token.tag)]

    pos_group_counts: Counter[str] = Counter()
    pos_detail_counts: Counter[str] = Counter()
    top_by_group: dict[str, Counter[str]] = {}
    for token in tokens:
        group = _pos_group(token.tag)
        pos_group_counts[group] += 1
        pos_detail_counts[token.tag] += 1
        top_by_group.setdefault(group, Counter()).update([token.form])

    final_eojeols = [_final_eojeol(sentence) for sentence in sentences]
    final_eojeol_counts = Counter(item for item in final_eojeols if item)
    final_ending_counts: Counter[str] = Counter()
    surface_ending_counts: Counter[str] = Counter()
    for sentence in sentences:
        sentence_tokens = _tokenize(sentence)
        for token in reversed(sentence_tokens):
            if token.tag == "EF" or token.tag.startswith("E"):
                final_ending_counts[token.form] += 1
                break
        surface = _surface_ending(sentence)
        if surface:
            surface_ending_counts[surface] += 1

    return MorphDocumentAnalysis(
        rank=rank,
        content_type=content_type,
        url=url,
        title=title,
        char_count_with_spaces=len(text),
        char_count_without_spaces=compact_char_count(text),
        paragraph_count=len([p for p in re.split(r"\n\s*\n+", text) if p.strip()]) or (1 if text.strip() else 0),
        sentence_count=len(sentences),
        eojeol_count=sum(eojeol_lengths),
        avg_eojeol_per_sentence=round(mean(eojeol_lengths), 2) if eojeol_lengths else 0.0,
        min_eojeol_per_sentence=min(eojeol_lengths) if eojeol_lengths else 0,
        max_eojeol_per_sentence=max(eojeol_lengths) if eojeol_lengths else 0,
        keyword_count=count_keyword(text, keyword) if keyword else 0,
        pos_group_counts=dict(pos_group_counts.most_common()),
        pos_detail_counts=dict(pos_detail_counts.most_common()),
        top_by_pos_group={group: dict(counter.most_common(top_n)) for group, counter in top_by_group.items()},
        final_eojeol_counts=dict(final_eojeol_counts.most_common(top_n)),
        final_ending_counts=dict(final_ending_counts.most_common(top_n)),
        surface_ending_counts=dict(surface_ending_counts.most_common(top_n)),
    )


def analyze_crawled_morphology(
    rows: Iterable[CrawledContent],
    *,
    keyword: str,
    top_n: int = 30,
) -> SearchMorphAnalysis:
    docs = [row for row in rows if row.ok and row.body]
    analyses = [
        analyze_text_morphology(
            row.body,
            keyword=keyword,
            rank=row.rank,
            content_type=row.content_type,
            url=row.url,
            title=row.title,
            top_n=top_n,
        )
        for row in docs
    ]

    global_group_counts: Counter[str] = Counter()
    global_top: dict[str, Counter[str]] = {}
    by_type_docs: dict[str, list[MorphDocumentAnalysis]] = {}
    for analysis in analyses:
        global_group_counts.update(analysis.pos_group_counts)
        by_type_docs.setdefault(analysis.content_type, []).append(analysis)
        for group, words in analysis.top_by_pos_group.items():
            global_top.setdefault(group, Counter()).update(words)

    by_content_type: dict[str, dict[str, object]] = {}
    common_terms_by_type: dict[str, dict[str, int]] = {}
    for ctype, items in by_type_docs.items():
        group_counts: Counter[str] = Counter()
        noun_counts: Counter[str] = Counter()
        verb_counts: Counter[str] = Counter()
        ending_counts: Counter[str] = Counter()
        for item in items:
            group_counts.update(item.pos_group_counts)
            noun_counts.update(item.top_by_pos_group.get("명사/체언", {}))
            verb_counts.update(item.top_by_pos_group.get("동사/보조동사", {}))
            ending_counts.update(item.surface_ending_counts)
        common_terms_by_type[ctype] = dict(noun_counts.most_common(top_n))
        by_content_type[ctype] = {
            "document_count": len(items),
            "pos_group_counts": dict(group_counts.most_common()),
            "top_nouns": dict(noun_counts.most_common(top_n)),
            "top_verbs": dict(verb_counts.most_common(top_n)),
            "surface_endings": dict(ending_counts.most_common(top_n)),
            "avg_char_count_without_spaces": round(mean([item.char_count_without_spaces for item in items]), 2),
            "avg_keyword_count": round(mean([item.keyword_count for item in items]), 2),
        }

    return SearchMorphAnalysis(
        keyword=keyword,
        document_count=len(analyses),
        analyses=analyses,
        by_content_type=by_content_type,
        global_pos_group_counts=dict(global_group_counts.most_common()),
        global_top_by_pos_group={group: dict(counter.most_common(top_n)) for group, counter in global_top.items()},
        common_terms_by_content_type=common_terms_by_type,
    )


def morph_analysis_to_dict(analysis: SearchMorphAnalysis | MorphDocumentAnalysis) -> dict:
    return asdict(analysis)


def sentence_ending_interpretations(analysis: MorphDocumentAnalysis) -> list[SentenceEndingCount]:
    return [
        SentenceEndingCount(ending=ending, count=count, interpretation=_ending_interpretation(ending))
        for ending, count in analysis.surface_ending_counts.items()
    ]
